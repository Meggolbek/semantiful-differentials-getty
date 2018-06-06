# all Daikon's usage for invariant analysis

import re
import sys
import time
import json
from functools import partial
from multiprocessing import Pool
from os import path, makedirs

import agency
import config
from tools import daikon, ex, git, html, mvn, os, profiler


SHOW_DEBUG_INFO = config.show_debug_info
SHOW_MORE_DEBUG_INFO = config.show_debug_details


# relative path of getty output path (go), when pwd is root dir of project
def rel_go(go):
    if go.endswith("/"):
        go = go[:-1]
    lsi = go.rfind("/")
    return ".." + go[lsi:] + "/"


# sort invariants in the output invariant text file
def sort_txt_inv(out_file):
    inv_map = {}
    current_key = None
    with open(out_file, 'r+') as f:
        lines = f.read().strip().split("\n")
        if lines != ['']:
            for line in lines:
                line = line.strip()
                if line.startswith("================"):
                    current_key = None
                elif re.match(".*:::(ENTER|EXIT|CLASS|OBJECT|THROW).*", line):
                    current_key = line
                    inv_map[current_key] = []
                else:
                    inv_map[current_key].append(line)
        f.seek(0)
        f.truncate()
        if lines != [''] and len(inv_map):
            for title in sorted(inv_map):
                f.write("\n================\n")
                if title.endswith(":::EXIT"):
                    f.write(os.rreplace(title, ":::EXIT", ":::EXITSCOMBINED", 1) + "\n")
                else:
                    f.write(title + "\n")
                for inv in sorted(inv_map[title]):
                    f.write(inv + "\n")
        else:
            f.write('<NO INVARIANTS INFERRED>')


# get class-level expanded target set
def all_methods_expansion(candidates, target_set, go, this_hash, index, java_cmd, inv_gz):
    exp_tmp = go + "expansion_temp." + this_hash + "." + str(index) + ".allinvs"
    run_print_allinvs = " ".join([java_cmd, "daikon.PrintInvariants", "--output", exp_tmp, inv_gz])
    os.sys_call(run_print_allinvs, ignore_bad_exit=True)
    regex_header = "(.*):::(ENTER|EXIT|CLASS|OBJECT|THROW).*"
    with open(exp_tmp, 'r') as rf:
        alllines = rf.read().split("\n")
        for line in alllines:
            m = re.match(regex_header, line.strip())
            if m:
                full_method = m.group(1)
                leftp_bound = full_method.find("(")
                rightp_bound = full_method.find(")")
                if leftp_bound != -1:
                    all_dots_mtdname = full_method[:leftp_bound]
                    last_dot_index = all_dots_mtdname.rfind(".")
                    if last_dot_index != -1:
                        raw_method_name = all_dots_mtdname[last_dot_index+1:]
                        further_last_dot_index = all_dots_mtdname[:last_dot_index].rfind(".")
                        if all_dots_mtdname[further_last_dot_index+1:last_dot_index] == raw_method_name:
                            raw_method_name = "<init>"
                        candidates.add(
                            all_dots_mtdname[:last_dot_index] + ":" + raw_method_name +
                            full_method[leftp_bound:rightp_bound+1].replace(" ", ""))
    os.remove_file(exp_tmp)
    ex.save_list_to(go + config.expansion_tmp_files + "." + this_hash +
                        "." + str(index) + "." + str(int(time.time())),
                    candidates)


# v4. flexible to be run in parallel, in daikon-online mode
def seq_get_invs(target_set_index_pair, java_cmd, junit_torun, go, this_hash, consider_expansion):
    start_of_func = time.time()
    index = target_set_index_pair[1]
    target_set = target_set_index_pair[0]
    
#     select_pattern = daikon.select_full(target_set)
    select_pattern = daikon.dfformat_full_ordered(target_set)
    print "\n=== select pattern ===\n" + select_pattern + "\n"
    
    inv_gz = go + "_getty_inv_" + this_hash + "_." + index
    if config.compress_inv:
        inv_gz += ".inv.gz"
    else:
        inv_gz += ".inv"
    
    daikon_control_opt_list = []
    if SHOW_MORE_DEBUG_INFO:
        daikon_control_opt_list.append("--show_progress --no_text_output")
    elif SHOW_DEBUG_INFO:
        daikon_control_opt_list.append("--no_show_progress --no_text_output")
    else:
        daikon_control_opt_list.append("--no_text_output")
    if config.disable_known_invs:
        daikon_control_opt_list.append("--disable-all-invariants")
    if config.omit_redundant_invs:
        daikon_control_opt_list.append("--omit_from_output 0r")
    if config.daikon_format_only:
        daikon_control_opt_list.append("--format Daikon")
    daikon_control_opt_list.append(config.blocked_daikon_invs_exp)
    daikon_display_args = " ".join(daikon_control_opt_list)
    # run Chicory + Daikon (online) for invariants without trace I/O
    run_chicory_daikon = \
        " ".join([java_cmd, "daikon.Chicory --daikon-online --exception-handling",
                  "--daikon-args=\""+daikon_display_args,
                  "-o", inv_gz+"\"",
                  "--ppt-select-pattern=\""+select_pattern+"\"",
                  junit_torun])
    if SHOW_DEBUG_INFO:
        print "\n=== Daikon:Chicory+Daikon(online) command to run: \n" + run_chicory_daikon
    start = time.time()
    os.sys_call(run_chicory_daikon, ignore_bad_exit=True)
    print "center run_chickory_daikon"+ str((time.time() - start))
    
    expansion = set()
    if consider_expansion and config.class_level_expansion:
        try:
            all_methods_expansion(expansion, target_set, go, this_hash, index, java_cmd, inv_gz)
        except:
            pass
    
    if SHOW_DEBUG_INFO:
        current_count = 0
        total_count = len(target_set)
    
    all_to_consider = set(target_set)
    if config.class_level_expansion:
        all_to_consider = (all_to_consider | expansion)
    
    for tgt in all_to_consider:
        target_ff = daikon.fsformat_with_sigs(tgt)
        out_file = go+"_getty_inv__"+target_ff+"__"+this_hash+"_.inv.out"
        run_printinv = \
            " ".join([java_cmd, "daikon.PrintInvariants",
                      "--format", config.output_inv_format,
                      "--ppt-select-pattern=\'"+daikon.dpformat_with_sigs(tgt)+"\'",
                      "--output", out_file, inv_gz])
        if SHOW_DEBUG_INFO:
            current_count += 1
            if config.show_regex_debug:
                print "\n\tthe regex for: " + tgt + "\n\t\t" + daikon.dpformat_with_sigs(tgt) + "\n"
            os.print_progress(current_count, total_count, 
                              prefix='Progress('+index+'):', 
                              suffix='('+str(current_count)+'/'+str(total_count)+': '+tgt+')'+' '*20, 
                              bar_length=50)
        elif SHOW_MORE_DEBUG_INFO:
            print "\n=== Daikon:PrintInvs command to run: \n" + run_printinv
        #start = time.time()
        os.sys_call(run_printinv, ignore_bad_exit=True)
        #print "center run_printinv" + str((time.time() - start))
        sort_txt_inv(out_file)
    os.remove_file(inv_gz)


def get_expansion_set(go):
    expansion = set([])
    try:
        files = os.from_sys_call(
            " ".join(["ls", go, "|", "grep", config.expansion_tmp_files])).strip().split("\n")
        for fl in files:
            fl = fl.strip()
            ep = set([])
            try:
                ep = ep | set(ex.read_str_from(go + fl))
            except:
                pass
            expansion = expansion | ep
        return expansion
    except:
        return expansion


# one pass template
def one_info_pass(
        junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, this_hash, target_set,
        changed_methods, changed_tests, inner_dataflow_methods, outer_dataflow_methods, json_filepath):
    start = time.time()
    os.sys_call("git checkout " + this_hash)
    print "center info:: git checkout " + str((time.time() - start))
    start = time.time()
    os.sys_call("mvn clean")
    print "center info:: mvn clean: " + str((time.time() - start))

    start1 = time.time()
    bin_path = mvn.path_from_mvn_call("outputDirectory")
    print "center info:: path from mvn call: " + str((time.time() - start1))
    start1 = time.time()
    test_bin_path = mvn.path_from_mvn_call("testOutputDirectory")
    print "center info:: path form mvn call " + str((time.time() - start1))
    start1 = time.time()
    cp = mvn.full_classpath(junit_path, sys_classpath, bin_path, test_bin_path)
    print "center info:: full class path " + str((time.time() - start1))
    if SHOW_DEBUG_INFO:
        print "\n===full classpath===\n" + cp + "\n"
    start = time.time()
    print "\ncopying all code to specific directory ...\n"

    all_code_dirs = [mvn.path_from_mvn_call("sourceDirectory"),
                     # mvn.path_from_mvn_call("scriptSourceDirectory"),
                     mvn.path_from_mvn_call("testSourceDirectory")]
    getty_code_store = go + '_getty_allcode_' + this_hash + '_/'
    print 'copy to ' + getty_code_store + '\n'
    makedirs(getty_code_store)
    for adir in all_code_dirs:
        os.sys_call(" ".join(["cp -r", adir + "/*", getty_code_store]), ignore_bad_exit=True)

    if config.use_special_junit_for_dyn:
        info_junit_path = os.rreplace(junit_path, config.default_junit_version, config.special_junit_version, 1)
        infocp = mvn.full_classpath(info_junit_path, sys_classpath, bin_path, test_bin_path)
    else:
        infocp = cp
    java_cmd = " ".join(["java", "-cp", infocp,
                         #                         "-Xms"+config.min_heap,
                         "-Xmx"+config.max_heap,
                         "-XX:+UseConcMarkSweepGC",
                         #                          "-XX:-UseGCOverheadLimit",
                         "-XX:-UseSplitVerifier",  # FIXME: JDK 8- only! 
                         ])
    print "center info:: copy code to dir: " + str((time.time() - start))
    # os.sys_call("mvn test -DskipTests", ignore_bad_exit=True)
    start = time.time()
    os.sys_call("mvn test-compile")
    print "center info:: compile tests: " + str((time.time() - start))

    start = time.time()
    junit_torun = mvn.junit_torun_str(cust_mvn_repo)
    print "center info:: junit_to_run_str " + str((time.time() - start))
    start1 = time.time()
    junit_tests = junit_torun.split(" ")
    print "center info:: junit_to_run.split "+ str((time.time() - start1))
    start1= time.time()
    junit_to_run = junit_tests[0]
    print "center info:: junit_tests[0] "+ str((time.time() - start1))
    if SHOW_DEBUG_INFO:
        print "\n===junit torun===\n" + junit_torun + "\n"
    print "center info:: junit to run str " + str((time.time() - start))
    #### dynamic run one round for all information
    start = time.time()
    prefixes = daikon.common_prefixes(target_set)
    print "center info:: daikon common prefixes " + str((time.time() - start))
    common_package = ''
    if len(prefixes) == 1:
        start = time.time()
        last_period_index = prefixes[0].rindex('.')
        if last_period_index > 0:
            # the common package should be at least one period away from the rest
            common_package = prefixes[0][:last_period_index]
        print "center info:: if len prefixes ==1 set common package " + str((time.time() - start))
    prefix_regexes = []
    start = time.time()
    for p in prefixes:
        prefix_regexes.append(p + "*")
    instrument_regex = "|".join(prefix_regexes)
    print "center info:: get instrument regex " + str((time.time() - start))
    if SHOW_DEBUG_INFO:
        print "\n===instrumentation pattern===\n" + instrument_regex + "\n"
    # run tests with instrumentation
    start = time.time()
    run_instrumented_tests = \
        " ".join([java_cmd, "-ea",
                  "-javaagent:" + agent_path + "=\"" + instrument_regex + "\"",
                  junit_torun])
    if SHOW_DEBUG_INFO:
        print "\n=== Instrumented testing command to run: \n" + run_instrumented_tests

    if not path.exists(dyng_go):
        makedirs(dyng_go)

    full_info_exfile = go + "_getty_binary_info_" + this_hash + "_.ex"
    os.sys_call(run_instrumented_tests +
                " > " + full_info_exfile +
                ("" if config.show_stack_trace_info else " 2> /dev/null"),
                ignore_bad_exit=True)
    print "center info::instrument tests and run: " + str((time.time() - start))

    start = time.time()

    full_method_info_map = {}
    ext_start_index = len(config.method_info_line_prefix)
    with open(full_info_exfile, 'r') as f:
        contents = f.read().split("\n")
        for line in contents:
            line = line.strip()
            if line.startswith(config.method_info_line_prefix):
                rawdata = line[ext_start_index:]
                k, v = rawdata.split(" : ")
                full_method_info_map[k.strip()] = v.strip()
    print "center info:: get full method info map: " + str((time.time() - start))
    start = time.time()
    os.merge_dyn_files(dyng_go, go, "_getty_dyncg_-hash-_.ex", this_hash)
    print "center info:: merge dyn files cg: " + str((time.time() - start))
    start = time.time()
    os.merge_dyn_files(dyng_go, go, "_getty_dynfg_-hash-_.ex", this_hash)
    #print "center info:: merge dyn files" + str((time.time() - start))
    print "center info:: merge dyn files fg: " + str((time.time() - start))
    start_if = time.time()
    if json_filepath != "":
        ######getting method -> tests info
        fname =  go + "_getty_dyncg_" + this_hash + "_.ex"
        start = time.time()
        methods_to_tests = create_methods_to_tests(fname, junit_torun)
        print "center info:: create_methods_to_tests " + str((time.time() - start))

        #get types_to_methods
        start = time.time()
        types_to_methods = read_in_types_to_methods(go, this_hash)
        print "center info:: read in types to methods " + str((time.time() - start))

        types_to_tests = {}
        #f = open(go + "_types_to_tests_" + this_hash + "_.ex", "w+")
        start = time.time()
        for key in types_to_methods.keys():
            for method in types_to_methods.get(key):
                method = method.strip("\n")
                method = method + "("
                for m in methods_to_tests.keys():
                    method_name = m[:(len(method))]
                    if method_name == method:
                        for test in methods_to_tests[m]:
                            if key in types_to_tests.keys():
                                types_to_tests[key].add(test)
                            else:
                                types_to_tests[key] = set([test])
        print "center info:: get types to tests " + str((time.time() - start))
        #For debugging
        # for key in types_to_tests.keys():
        #    for test in types_to_tests[key]:
        #        f.write(key + "," + test + "\n")
        # f.close()
        start = time.time()
        with open(json_filepath) as f:
            priorities = json.load(f)
        tests_to_run = set()
        types = set()
        target_set = set()
        for s in priorities["priorityList"]:
            for type in types_to_tests.keys():
                temp = type + ":"
                if s[:len(temp)] == temp:
                    for method in types_to_methods[type]:
                        for m in methods_to_tests:
                            temp = method.strip("\n") + "("
                            if m[:len(temp)] == temp:
                                methodNumber = m.split("-")
                                target_set.add((method.strip("\n")) + "-" + methodNumber[1])
                    for test in types_to_tests[type]:
                        tests_to_run.add(test)
                        types.add(type)
                        # print "s: " + s + "type: " + type + " test " + test

        print "center info:: get tests to run and target set " + str((time.time() - start))
        ###########
        start = time.time()
        tests_for_junit = set()
        for test in tests_to_run:
            i = test.rfind(":")
            temp = test[:i]
            tests_for_junit.add(temp)
        for temp in tests_for_junit:
            junit_to_run = junit_to_run + " " + temp
        junit_torun = junit_to_run
        print "center info:: get new junit_torun " + str((time.time() - start))
    print "center info:: if json "  + str((time.time() - start_if))

    start = time.time()
    caller_of, callee_of = agency.caller_callee(go, this_hash)
    print "center info:: agency.caller_callee "  + str((time.time() - start))
    start = time.time()
    pred_of, succ_of = agency.pred_succ(go, this_hash)
    print "center info:: agency.pred_succ "  + str((time.time() - start))

    # add test methods into target set
    start = time.time()
    test_set = agency.get_test_set_dyn(target_set, callee_of, junit_torun)
    print "center info:: agency get test set dyn: " + str((time.time() - start))
    #test_set is correct
    # reset target set here
    start = time.time()
    refined_target_set, changed_methods, changed_tests = \
        agency.refine_targets(full_method_info_map, target_set, test_set,
                              caller_of, callee_of, pred_of, succ_of,
                              changed_methods, changed_tests,
                              inner_dataflow_methods, outer_dataflow_methods, json_filepath)
    print "center info:: agency refine targets: " + str((time.time() - start))
    start = time.time()
    profiler.log_csv(["method_count", "test_count", "refined_target_count"],
                     [[len(target_set), len(test_set), len(refined_target_set)]],
                     go + "_getty_y_method_count_" + this_hash + "_.profile.readable")
    print "center info:: profiler.log_csv " + str((time.time() - start))
    start = time.time()
    git.clear_temp_checkout(this_hash)
    print "center info:: clear temp checkout: " + str((time.time() - start))

    return common_package, test_set, refined_target_set, changed_methods, changed_tests, \
           cp, junit_torun, full_method_info_map


def read_in_types_to_methods(go, this_hash):
    types_to_methods = {}
    with open(go + "_types_to_methods_" + this_hash + "_.ex") as f:
        content = f.readlines()
    for line in content:
        pair = line.split(",")
        if pair[0] in types_to_methods.keys():
            types_to_methods[pair[0]].add(pair[1])
        else:
            types_to_methods[pair[0]] = set([pair[1]])
    return types_to_methods


def create_methods_to_tests(fname, junit_torun):
    methods_to_tests = {}
    with open(fname) as f:
        content = f.readlines()
    total_pairs = []
    nonTestMethodCalls = {}
    for line in content:
        line.strip("[()]")
        pairs = line.split("), (")
        total_pairs = total_pairs + pairs
    for pair in total_pairs:
        invocation = pair.split("\", ")
        for i in range(0, 2):
            invocation[i] = (invocation[i]).replace("\"", "")
        isATest = False
        testSuites = junit_torun.split(" ")
        for prefix in testSuites:
            prefix = prefix + ":"
            package = invocation[0][:(len(prefix))]
            if prefix == package:
                isATest = True
        if isATest:
            if invocation[1] in methods_to_tests.keys():
                methods_to_tests[invocation[1]].add(invocation[0])
            else:
                methods_to_tests[invocation[1]] = set([invocation[0]])
        else:
            if invocation[0] in nonTestMethodCalls.keys():
                for k in nonTestMethodCalls[invocation[0]]:
                    if k in nonTestMethodCalls:
                        nonTestMethodCalls[invocation[0]].union(nonTestMethodCalls[k])
            else:
                nonTestMethodCalls[invocation[0]] = set([invocation[1]])
        for caller in nonTestMethodCalls:
            for callee in nonTestMethodCalls[caller]:
                if callee in methods_to_tests and caller in methods_to_tests:
                    methods_to_tests[callee].union(methods_to_tests[caller])
                elif caller in methods_to_tests:
                    methods_to_tests[callee] = methods_to_tests[caller]
    return methods_to_tests


# one pass template
def one_inv_pass(go, cp, junit_torun, this_hash, refined_target_set, analysis_only=False):
    
    if not analysis_only:
        start = time.time()
        os.sys_call("git checkout " + this_hash)
        print "center one_inv_psss: syscall git checkout " + str((time.time() - start))
    start = time.time()
    os.sys_call("mvn clean")
    print "center one_inv_psss: syscall mvn clean " + str((time.time() - start))
    
    if SHOW_DEBUG_INFO:
        print "\n===full classpath===\n" + cp + "\n"
    
    java_cmd = " ".join(["java", "-cp", cp, 
#                          "-Xms"+config.min_heap, 
                         "-Xmx"+config.max_heap, 
                         "-XX:+UseConcMarkSweepGC", 
#                          "-XX:-UseGCOverheadLimit",
                         "-XX:-UseSplitVerifier",  # FIXME: JDK 8- only! 
                         ])
    
    # os.sys_call("mvn test -DskipTests", ignore_bad_exit=True)
    start = time.time()
    os.sys_call("mvn test-compile")
    print "center one_inv_psss: syscall mvn test-compile " + str((time.time() - start))

    if SHOW_DEBUG_INFO:
        print "\n===junit torun===\n" + junit_torun + "\n"
    
    # v3.2, v4 execute with 4 core
    num_primary_workers = config.num_master_workers
    auto_parallel_targets = config.auto_fork
    slave_load = config.classes_per_fork
    start = time.time()
    target_map = daikon.target_s2m(refined_target_set)
    print "center one_inv_pass: daikon get target map: " + str((time.time() - start))
    all_classes = target_map.keys()
    
    consider_expansion = (not analysis_only)

    start = time.time()
    if len(refined_target_set) <= num_primary_workers or (num_primary_workers == 1 and not auto_parallel_targets):
        single_set_tuple = (refined_target_set, "0")
        seq_get_invs(single_set_tuple, java_cmd, junit_torun, go, this_hash, consider_expansion)
    elif num_primary_workers > 1:  # FIXME: this distributation is buggy
        target_set_inputs = []
        all_target_set_list = list(refined_target_set)
        each_bulk_size = int(len(refined_target_set) / num_primary_workers)
        seq_func = partial(seq_get_invs, 
                           java_cmd=java_cmd, junit_torun=junit_torun, go=go, this_hash=this_hash,
                           consider_expansion=consider_expansion)
        for i in range(num_primary_workers):
            if not(i == num_primary_workers - 1):
                sub_list_tuple = (all_target_set_list[each_bulk_size*i:each_bulk_size*(i+1)], str(i))                
                target_set_inputs.append(sub_list_tuple)
            else:
                sub_list_tuple = (all_target_set_list[each_bulk_size*i:], str(i))
                target_set_inputs.append(sub_list_tuple)
        input_pool = Pool(num_primary_workers)
        input_pool.map(seq_func, target_set_inputs)
        input_pool.close()
        input_pool.join()
    elif num_primary_workers == 1 and auto_parallel_targets and slave_load >= 1:
        # elastic automatic processing
        target_set_inputs = []
        num_processes = 0
        
        # target_map has been calculated already
        # target_map = daikon.target_s2m(refined_target_set)
        # all_classes = target_map.keys()
        num_keys = len(all_classes)
        seq_func = partial(seq_get_invs, 
                           java_cmd=java_cmd, junit_torun=junit_torun, go=go, this_hash=this_hash,
                           consider_expansion=consider_expansion)
        
        for i in range(0, num_keys, slave_load):
            # (inclusive) lower bound is i
            # (exclusive) upper bound:
            j = min(i+slave_load, num_keys)
            sublist = []
            for k in range(i, j):
                the_key = all_classes[k]
                sublist.append(the_key)  # so it won't miss class/object invariants
                sublist += target_map[the_key]
            sublist_tuple = (sublist, str(num_processes))
            target_set_inputs.append(sublist_tuple)
            num_processes += 1
        
        max_parallel_processes = config.num_slave_workers
        if not analysis_only:
            profiler.log_csv(["class_count", "process_count", "max_parallel_processes", "slave_load"],
                             [[num_keys, num_processes, max_parallel_processes, slave_load]],
                             go + "_getty_y_elastic_count_" + this_hash + "_.profile.readable")
        
        input_pool = Pool(max_parallel_processes)
        input_pool.map(seq_func, target_set_inputs)
        input_pool.close()
        input_pool.join()
        
    else:
        print "\nIncorrect option for one center pass:"
        print "\tnum_primary_workers:", str(num_primary_workers)
        print "\tauto_parallel_targets:", str(auto_parallel_targets)
        print "\tslave_load", str(slave_load)
        sys.exit(1)
    print "center inv_pass seq get invs " + str((time.time() - start))
    start = time.time()
    if config.compress_inv:
        os.remove_many_files(go, "*.inv.gz")
    else:
        os.remove_many_files(go, "*.inv")
    print "center one_inv_pass: remove inv files " + str((time.time() - start))
    # include coverage report for compare
    if config.analyze_test_coverage and not analysis_only:
        try:
            start = time.time()
            mvn.generate_coverage_report(go, this_hash)
            print "center inv_pass: mvn.generate coverage report " + str((time.time() - start))
        except:
            pass
    
    if not analysis_only:
        start = time.time()
        git.clear_temp_checkout(this_hash)
        print "center inv_pass: clear temp checkout" + str((time.time() - start))
    
    if config.class_level_expansion:
        start = time.time()
        extra_expansion = get_expansion_set(go)
        os.remove_many_files(go, config.expansion_tmp_files + "*")
        print "center inv_pass: remove expansion tmp files " + str((time.time() - start))
    else:
        extra_expansion = None
    
    return all_classes, extra_expansion


def mixed_passes(go, prev_hash, post_hash, refined_expansion_set,
                 refined_target_set, old_refined_target_set, new_refined_target_set,
                 old_cp, new_cp, old_junit_torun, new_junit_torun):

    if config.class_level_expansion:
        impact_set = refined_target_set | refined_expansion_set
    else:
        impact_set = refined_target_set
    print "center mixed_passes: get refined target set" + str((time.time() - start))
    # checkout old commit, then checkout new tests
    start = time.time()
    os.sys_call("git checkout " + prev_hash)
    print "center mixed_passes: git checkout prev haash" + str((time.time() - start))
    start = time.time()
    new_test_path = mvn.path_from_mvn_call("testSourceDirectory")
    print "center mixed_passes: path form mvn call to get new test path" + str((time.time() - start))
    start = time.time()
    os.sys_call(" ".join(["git", "checkout", post_hash, new_test_path]))
    print "center mixed_passes: git checkout post hash new test path" + str((time.time() - start))
    #     # may need to check whether it is compilable, return code?
    #     os.sys_call("mvn clean test-compile")
    start = time.time()
    one_inv_pass(go, new_cp, new_junit_torun,
                 prev_hash + "_" + post_hash,
                 impact_set, analysis_only=True)
    print "center mixed_passes: one inv pass" + str((time.time() - start))
    start = time.time()
    git.clear_temp_checkout(prev_hash)
    print "center mixed_passes: git clear temp checkout prev hash" + str((time.time() - start))
    # checkout old commit, then checkout new src
    start = time.time()
    os.sys_call("git checkout " + prev_hash)
    print "center mixed_passes: git check out prev" + str((time.time() - start))
    start = time.time()
    new_src_path = mvn.path_from_mvn_call("sourceDirectory")
    print "center mixed_passes: get new src path path form mvn call" + str((time.time() - start))
    start = time.time()
    os.sys_call(" ".join(["git", "checkout", post_hash, new_src_path]))
    print "center mixed_passes: git checkout post hash new src path" + str((time.time() - start))
    #     # may need to check whether it is compilable, return code?
    #     os.sys_call("mvn clean test-compile")
    start = time.time()
    one_inv_pass(go, new_cp, old_junit_torun,
                 post_hash + "_" + prev_hash,
                 impact_set, analysis_only=True)
    print "center mixed_passes: one inv pass" + str((time.time() - start))
    start = time.time()
    git.clear_temp_checkout(prev_hash)
    print "center mixed_passes: git clear temp checkout prev hash" + str((time.time() - start))


def __build_target2ln(infomap):
    result = {}
    for k in infomap:
        fullinfo = infomap[k]
        last_dash = fullinfo.rfind("-")
        result[fullinfo[:last_dash]] = fullinfo[last_dash+1:]
    return result


def __build_method2line(method_info_map):
    result = {}
    for k in method_info_map:
        full_method = method_info_map[k]
        last_dash = full_method.rfind("-")
        if last_dash != -1:
            result[full_method[:last_dash]] = full_method[last_dash+1:]
    return result


def __purify_targets(targets):
    result = set()
    for t in targets:
        last_dash_pos = t.rfind("-")
        if last_dash_pos == -1:
            result.add(t)
        else:
            result.add(t[:last_dash_pos])
    return result


def _merge_target_sets(old_rts, new_rts, old_mtd_info_map, new_mtd_info_map):
    result = set()
    start = time.time()
    old_mtd2ln = __build_target2ln(old_mtd_info_map)
    print "center merge target sets:: build_target2ln old" + str((time.time() - start))
    start = time.time()
    old_rts_purified = __purify_targets(old_rts)
    print "center merge target sets:: purify targets old" + str((time.time() - start))
    start = time.time()
    old_keyset = set(old_mtd2ln.keys())
    print "center merge target sets:: get key set old" + str((time.time() - start))
    start = time.time()
    new_mtd2ln = __build_target2ln(new_mtd_info_map)
    print "center merge target sets:: build target2ln new" + str((time.time() - start))
    start = time.time()
    new_rts_purified = __purify_targets(new_rts)
    print "center merge target sets:: purify targets new" + str((time.time() - start))
    start = time.time()
    new_keyset = set(new_mtd2ln.keys())
    print "center merge target sets:: purify targets new" + str((time.time() - start))
    start = time.time()
    for old_and_new in (old_rts_purified & new_rts_purified):
        mtd_full_info = old_and_new + "-" + old_mtd2ln[old_and_new] + "," + new_mtd2ln[old_and_new]
        result.add(mtd_full_info)
    print "center merge target sets:: old and new add result" + str((time.time() - start))
    start = time.time()
    for old_but_new in (old_rts_purified - new_rts_purified):
        if old_but_new in new_keyset:
            mtd_full_info = old_but_new + "-" + old_mtd2ln[old_but_new] + "," + new_mtd2ln[old_but_new]
        else:
            mtd_full_info = old_but_new + "-" + old_mtd2ln[old_but_new] + ",0"
        result.add(mtd_full_info)
    print "center merge target sets:: just old add result" + str((time.time() - start))
    start = time.time()
    for new_but_old in (new_rts_purified - old_rts_purified):
        if new_but_old in old_keyset:
            mtd_full_info = new_but_old + "-" + old_mtd2ln[new_but_old] + "," + new_mtd2ln[new_but_old]
        else:
            mtd_full_info = new_but_old + "-0," + new_mtd2ln[new_but_old]
        result.add(mtd_full_info)
    print "center merge target sets:: just new add result" + str((time.time() - start))
    return result


def _append_class_ln(class_set):
    result = set()
    start = time.time()
    for c in class_set:
        result.add(c + "-0,0")
    print "center append class ln:: for each c append -0,0" + str((time.time() - start))
    return result


def _common_specific_expansion(expansion, old_method_info_map, new_method_info_map):
    start = time.time()
    old_m2l = __build_method2line(old_method_info_map)
    print "center common specific expansion:: build method 2line old" + str((time.time() - start))
    start = time.time()
    new_m2l = __build_method2line(new_method_info_map)
    print "center common specific expansion:: build method 2line new" + str((time.time() - start))
    common_keys = set(old_m2l.keys()) & set(new_m2l.keys())
    result = set()
    start = time.time()
    for candidate in expansion:
        if candidate in common_keys:
            complete_info_name = candidate + "-" + old_m2l[candidate] + "," + new_m2l[candidate]
            result.add(complete_info_name)
    print "center common specific expansion:: get candidates in expansion" + str((time.time() - start))
    return result


# the main entrance
def visit(junit_path, sys_classpath, agent_path, cust_mvn_repo, separate_go, prev_hash, post_hash, targets, iso,
          old_changed_methods, old_changed_tests, old_inner_dataflow_methods, old_outer_dataflow_methods,
          new_changed_methods, new_changed_tests, new_inner_dataflow_methods, new_outer_dataflow_methods, json_filepath):

    dyng_go = separate_go[0]
    go = separate_go[1]

    print("\n****************************************************************");
    print("        Getty Center: Semantiful Differential Analyzer            ");
    print("****************************************************************\n");

    '''
        1-st pass: checkout prev_commit as detached head, and get new interested targets
    '''
    start = time.time()
    (old_common_package, old_test_set, old_refined_target_set,
     old_changed_methods, old_changed_tests, old_cp, old_junit_torun, old_method_info_map) = \
        one_info_pass(
            junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, prev_hash, targets,
            old_changed_methods, old_changed_tests, old_inner_dataflow_methods, old_outer_dataflow_methods, json_filepath)
    print "center first one info pass: " + str((time.time() - start))
    '''
        2-nd pass: checkout post_commit as detached head, and get new interested targets
    '''
    start = time.time()
    (new_common_package, new_test_set, new_refined_target_set,
     new_changed_methods, new_changed_tests, new_cp, new_junit_torun, new_method_info_map) = \
        one_info_pass(
            junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, post_hash, targets,
            new_changed_methods, new_changed_tests, new_inner_dataflow_methods, new_outer_dataflow_methods, json_filepath)
    print "center second one info pass: " + str((time.time() - start))

    '''
        middle pass: set common interests
    '''
    start = time.time()
    common_package = ''
    if old_common_package != '' and new_common_package != '':
        if (len(old_common_package) < len(new_common_package) and
                (new_common_package+'.').find(old_common_package+'.') == 0):
            common_package = old_common_package
        elif (len(old_common_package) >= len(new_common_package) and
              (old_common_package+'.').find(new_common_package+'.') == 0):
            common_package = old_common_package
    config.the_common_package.append(common_package)
    print "center config.common package: " + str((time.time() - start))
    #     refined_target_set = old_refined_target_set | new_refined_target_set
    start = time.time()
    refined_target_set, all_changed_methods, all_changed_tests = \
        _merge_target_sets(
            old_refined_target_set, new_refined_target_set, old_method_info_map, new_method_info_map), \
        _merge_target_sets(
            old_changed_methods, new_changed_methods, old_method_info_map, new_method_info_map), \
        _merge_target_sets(
            old_changed_tests, new_changed_tests, old_method_info_map, new_method_info_map)
    print "center merge targets: " + str((time.time() - start))
    '''
        3-rd pass: checkout prev_commit as detached head, and get invariants for all interesting targets
    '''
    start = time.time()
    old_all_classes, old_expansion = one_inv_pass(go,
                                                  old_cp, old_junit_torun, prev_hash, refined_target_set)
    print "center first one inv pass: " + str((time.time() - start))
    '''
        4-th pass: checkout post_commit as detached head, and get invariants for all interesting targets
    '''
    start = time.time()
    new_all_classes, new_expansion = one_inv_pass(go,
                                                  new_cp, new_junit_torun, post_hash, refined_target_set)
    print "center second one inv pass: " + str((time.time() - start))

    common_expansion = set()
    refined_expansion_set = set()
    if config.class_level_expansion:
        start = time.time()
        common_expansion = old_expansion & new_expansion
        refined_expansion_set = _common_specific_expansion(
            common_expansion, old_method_info_map, new_method_info_map)
        print "center common specific expansion: " + str((time.time() - start))
    #print "center get common expansion: " + str((time.time() - start))
    '''
        more passes: checkout mixed commits as detached head, and get invariants for all interesting targets
    '''
    if iso:
        start = time.time()
        mixed_passes(go, prev_hash, post_hash, refined_expansion_set,
                     refined_target_set, old_refined_target_set, new_refined_target_set,
                     old_cp, new_cp, old_junit_torun, new_junit_torun)
        print "center common mixed passes: " + str((time.time() - start))
    '''
        last pass: set common interests
    '''
    start = time.time()
    html.src_to_html_ln_anchor(refined_target_set, go, prev_hash, for_old=True)
    html.src_to_html_ln_anchor(refined_target_set, go, post_hash)
    print "center src to html ln anchor: " + str((time.time() - start))
    # should not need line number information anymore from this point on

    '''
        prepare to return
    '''
    start = time.time()
    all_classes_set = set(old_all_classes + new_all_classes)
    print "center append set: " + str((time.time() - start))
    start = time.time()
    all_classes_set = _append_class_ln(all_classes_set)
    print "center append class ln: " + str((time.time() - start))

    print 'Center analysis is completed.'
    return common_package, all_classes_set, refined_target_set, \
           old_test_set, old_refined_target_set, new_test_set, new_refined_target_set, \
           old_changed_methods, new_changed_methods, old_changed_tests, new_changed_tests, \
           all_changed_methods, all_changed_tests

