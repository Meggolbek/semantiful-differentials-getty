# all Daikon's usage for invariant analysis

import re
import sys
import time
import json
from functools import partial
from multiprocessing import Pool
from os import path, makedirs
import os as py_os

import agency
import config
from tools.project_utils import ProjectUtils
from tools import java, daikon, ex, git, html, os, profiler, maven_adapter, git_adapter


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
def all_methods_expansion(candidates, go, this_hash, index, java_cmd, inv_gz):
    exp_tmp = go + "expansion_temp." + this_hash + "." + str(index) + ".allinvs"
    run_print_allinvs = " ".join([java_cmd, "daikon.PrintInvariants", "--output", exp_tmp, inv_gz])
    os.sys_call(run_print_allinvs, ignore_bad_exit=True, cwd=ProjectUtils.get_version_path(this_hash))
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
def seq_get_invs(target_set_index_pair, java_cmd, junit_torun, go, this_hash, consider_expansion, test_selection):
    
    index = target_set_index_pair[1]
    target_set = target_set_index_pair[0]
    #if test selection remove class from target set
    if test_selection:
        ttarget_set = set(target_set)
        for s in ttarget_set:
            if not s.__contains__(":"):
                target_set.remove(s)
#     select_pattern = daikon.select_full(target_set)
    select_pattern = daikon.dfformat_full_ordered(target_set, test_selection)
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
        # print "\n=== Daikon:Chicory+Daikon(online) command to run: \n" + run_chicory_daikon
    os.sys_call(run_chicory_daikon, ignore_bad_exit=True, cwd=ProjectUtils.get_version_path(this_hash))
    
    expansion = set()
    if consider_expansion and config.class_level_expansion:
        try:
            all_methods_expansion(expansion, go, this_hash, index, java_cmd, inv_gz)
        except:
            pass
    
    if SHOW_DEBUG_INFO:
        current_count = 0
        total_count = len(target_set)

    all_to_consider = set(target_set)
    if config.class_level_expansion:
        all_to_consider = (all_to_consider | expansion)

    classes_to_consider = set()
    for tgt in all_to_consider:
        class_ref = tgt.split(':')[0]
        classes_to_consider.add(class_ref)

    print "==== classes to consider: ", classes_to_consider, " hash: " + this_hash
    for tgt in classes_to_consider:
        # print "============ target is: " + tgt + ", pattern is: "+ daikon.dpformat_with_sigs(tgt) +" ==============="
        target_ff = daikon.fsformat_with_sigs(tgt)
        out_file = go+"_getty_inv__"+target_ff+"__"+this_hash+"_.inv.out"

        # TODO: For some reason adding this optimization leads to different results
        # if py_os.path.isfile(out_file):
        #     f = open(out_file, "r")
        #     f_invs = f.read()
        #     f.close()
        #     if  f_invs == "<NO INVARIANTS INFERRED>\n":
        #         print "no invariants found, running daikon.PrintInvariants again for class", tgt
        #     else:
        #         # don't run daikon.PrintInvariants twice for the same class
        #         print "not running daikon.PrintInvariants again for class", tgt, f_invs
        #         continue

        run_printinv = \
            " ".join([java_cmd, "daikon.PrintInvariants",
                      "--format", config.output_inv_format,
                      "--ppt-select-pattern=\'"+daikon.dpformat_with_sigs(tgt)[:-1]+"[.:]"+"\'",
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
        os.sys_call(run_printinv, ignore_bad_exit=True, cwd=ProjectUtils.get_version_path(this_hash))
        sort_txt_inv(out_file)

        result = create_inv_out_file_per_method(out_file, all_to_consider, this_hash, go)
        if result is False:
            print "create_inv_out_file_per_method returned False"

    os.remove_file(inv_gz)


def create_inv_out_file_per_method(out_file, methods_to_consider, this_hash, go):
    f = open(out_file, "r")

    if f.mode != 'r':
        print "WARN: file not opened in read mode"
        return False

    invariants = f.read()
    f.close()

    inv_array = invariants.split("\n================\n")

    for tgt in methods_to_consider:
        regex = daikon.dpformat_with_sigs(tgt)[1:]
        target_ff = daikon.fsformat_with_sigs(tgt)
        out_file = go + "_getty_inv__" + target_ff + "__" + this_hash + "_.inv.out"

        # TODO: this is to prevent invariants being added to the same file multiple times. This shouldn't happen in the first place.
        # I could figure out what is happening, but not exactly why and how to prevent it.
        # It's happening because, for the GStack test project:
        # For GStack, methods_to_consider will contain both isEmpty() and isEmpty()-56,56 so that's 2 times.
        # For GStackTest, methods_to_consider will also contain GStack:isEmpty() and GStack:isEmpty()-56,56, that's another 2 times.
        #    However, it will look for them in the GStackTests inv output file and of course cannot find anything there so it will print <NO INVARIANTS FOUND>
        # So in total we look 4 times for invariants for GStack:isEmtpy and 2 times we find none because we're looking in the wrong inv file.
        #    The first 2 times always find <NO INVARIANTS FOUND> and the last 2 times are duplicates
        # Solution for now: only keep the output of the last time as this was the original behavior before my changes.
        file_invs = []
        if py_os.path.isfile(out_file):
            f = open(out_file, "r")
            file_invs = f.read().split("\n================\n")
            f.close()
            if file_invs[0] == "<NO INVARIANTS INFERRED>\n":
                py_os.remove(out_file)
                file_invs = []

        file_created = len(file_invs) > 0
        for inv in inv_array:
            if inv in file_invs:
                continue

            if re.search(regex, inv):

                # print "=== writing: " + out_file
                f = open(out_file, "a+")
                file_created = True

                f.write("\n================\n")
                f.write(inv)
                f.close()

        if file_created is False:
            f = open(out_file, "a+")
            f.write("<NO INVARIANTS INFERRED>\n")
            f.close()

    return True


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

    bin_path = maven_adapter.get_bin_path(this_hash)
    test_bin_path = maven_adapter.get_test_bin_path(this_hash)
    cp = maven_adapter.get_full_class_path(this_hash, junit_path, sys_classpath, bin_path, test_bin_path)
    if SHOW_DEBUG_INFO:
        print "\n===full classpath===\n" + cp + "\n"

    # print "\ncopying all code to specific directory ...\n"
    all_code_dirs = [maven_adapter.get_source_directory(this_hash),
                     maven_adapter.get_test_source_directory(this_hash)]
    getty_code_store = go + '_getty_allcode_' + this_hash + '_/'
    print 'copy to ' + getty_code_store + '\n'
    makedirs(getty_code_store)
    for adir in all_code_dirs:
        os.sys_call(" ".join(["cp -r", adir + "/*", getty_code_store]), ignore_bad_exit=True)
    if config.use_special_junit_for_dyn:
        info_junit_path = os.rreplace(junit_path, config.default_junit_version, config.special_junit_version, 1)
        # infocp = mvn.full_classpath(info_junit_path, sys_classpath, bin_path, test_bin_path)
        infocp = maven_adapter.get_full_class_path(this_hash, info_junit_path, sys_classpath, bin_path, test_bin_path)
    else:
        infocp = cp

    # os.sys_call("mvn test -DskipTests", ignore_bad_exit=True)
    maven_adapter.compile_tests(this_hash)

    junit_torun = maven_adapter.get_junit_torun(cust_mvn_repo, this_hash)
    if SHOW_DEBUG_INFO:
        print "\n===junit torun===\n" + junit_torun + "\n"

    #### dynamic run one round for all information    
    prefixes = daikon.common_prefixes(target_set)
    common_package = ''
    if len(prefixes) == 1:
        last_period_index = prefixes[0].rindex('.')
        if last_period_index > 0:
            # the common package should be at least one period away from the rest
            common_package = prefixes[0][:last_period_index]
    prefix_regexes = []
    for p in prefixes:
        prefix_regexes.append(p + "*")
    instrument_regex = "|".join(prefix_regexes)
    if SHOW_DEBUG_INFO:
        print "\n===instrumentation pattern===\n" + instrument_regex + "\n"

    if not path.exists(dyng_go):
        makedirs(dyng_go)

    full_info_exfile = java.run_instrumented_tests(this_hash, go, infocp, agent_path, instrument_regex, junit_torun)

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

    # print "dyng_go=", dyng_go, " go=", go

    os.merge_dyn_files(dyng_go, go, "_getty_dyncg_-hash-_.ex", this_hash)
    os.merge_dyn_files(dyng_go, go, "_getty_dynfg_-hash-_.ex", this_hash)
    caller_of, callee_of = agency.caller_callee(go, this_hash)
    pred_of, succ_of = agency.pred_succ(go, this_hash)
    if json_filepath != "":
        junit_torun, target_set, test_set = get_tests_and_target_set(go, json_filepath, junit_torun, this_hash)
    else:
        test_set = agency.get_test_set_dyn(callee_of, junit_torun)

    #test_set is correct
    # reset target set here
    refined_target_set, changed_methods, changed_tests = \
        agency.refine_targets(full_method_info_map, target_set, test_set,
                              caller_of, callee_of, pred_of, succ_of,
                              changed_methods, changed_tests,
                              inner_dataflow_methods, outer_dataflow_methods, json_filepath)

    profiler.log_csv(["method_count", "test_count", "refined_target_count"],
                     [[len(target_set), len(test_set), len(refined_target_set)]],
                     go + "_getty_y_method_count_" + this_hash + "_.profile.readable")

    git.clear_temp_checkout(this_hash)

    return common_package, test_set, refined_target_set, changed_methods, changed_tests, \
           cp, junit_torun, full_method_info_map


def get_tests_and_target_set(go, json_filepath, junit_torun, this_hash):
    #have to add junit runner to junit_to_run in order to get invariants
    junits_to_run = junit_torun.split(" ")
    junit_to_run = junits_to_run[0]
    ######getting method -> tests
    fname = go + "_getty_dyncg_" + this_hash + "_.ex"
    methods_to_tests, nontest_method_calls = create_methods_to_tests(fname, junit_torun)
    # get types_to_methods
    types_to_methods = read_in_types_to_methods(go, this_hash)
    #get priority list from json file
    with open(json_filepath) as f:
        priorities = json.load(f)
    test_set = set()
    target_set = set()
    methods_to_check = set()
    for priority in priorities["priorityList"]:
        package = priority.split(":")
        # check if package name is a test suite. if so then it is a test.
        testSuites = junit_torun.split(" ")
        if package[0] in testSuites:
            priority = priority + "("
            for method in methods_to_tests.keys():
                for test in methods_to_tests[method]:
                    if priority == test[:len(priority)]:
                        method = method[:method.find("(")]
                        target_set, test_set, methods_to_check = add_to_targetset(methods_to_check, methods_to_tests, method, target_set, test_set, types_to_methods)
        # else priority is not a test
        else:
            target_set, test_set, methods_to_check = add_to_targetset(methods_to_check, methods_to_tests, priority, target_set, test_set, types_to_methods)
    seen_methods = set([])
    #(methods_to_check = target set 1st iteration)
    #for each method in target set check if it calls another method
    #if so add that method to methods to check and target set
    #run until no more methods to check or all methods have been seen
    while methods_to_check:
        to_check = set(methods_to_check)
        for m in to_check:
            if not m in seen_methods:
                seen_methods.add(m)
                if m in nontest_method_calls.keys():
                    for callee in nontest_method_calls[m]:
                        methods_to_check.add(callee)
                        callee_name = callee[:(callee.rfind("("))]
                        target_set, test_set, methods_to_check = add_to_targetset(methods_to_check, methods_to_tests,
                                                                                  callee_name,target_set, test_set,
                                                                                      types_to_methods)

            methods_to_check.remove(m)
    #add each corresponding junit suite to junit to run
    tests_for_junit = set()
    for test in test_set:
        i = test.rfind(":")
        temp = test[:i]
        tests_for_junit.add(temp)
    for temp in tests_for_junit:
        junit_to_run = junit_to_run + " " + temp
    junit_torun = junit_to_run
    return junit_torun, target_set, test_set


def add_to_targetset(methods_to_check, methods_to_tests, target, target_set, test_set, types_to_methods):
    s = target + "("
    method = ""
    # check to see if method is eventually called by a test
    for m in methods_to_tests:
        if m[:len(s)] == s:
            method = m
            break

    # if eventually called by a test then add to target set
    # add tests that call it to test set
    if method:
        methodNumber = method[(method.rfind("-")):]
        target_set.add(target + methodNumber)
        for test in methods_to_tests[method]:
            test_set.add(test)
            # methodNumber = test[(test.rfind("-")):]
            # target_set.add(target + methodNumber)
            # methods_to_check.add(test)
        # methods to check are for checking if there are called methods within target
        methods_to_check.add(method)
    # else it must be a method that belongs to a type. Get methods that implement it
    # or are in a subclass of it
    else:
        index = target.find(":")
        type = target[:index]
        method_name = target[index:]
        method_name = method_name.strip()
        # check to see if type is a valid type
        if type in types_to_methods:
            # for each method in the type get corresponding subtype method
            for m in types_to_methods[type]:
                m = m.strip()
                i = m.rfind(":")
                if m[i:] == method_name:
                    for key in methods_to_tests:
                        # add corresponding subtype method to target set and
                        # tests that call it to test set
                        if key[:len(m)] == m:
                            methodNumber = key[(key.rfind("-")):]
                            target_set.add(m + methodNumber)
                            for test in methods_to_tests[key]:
                                test_set.add(test)
                            methods_to_check.add(key)
    return target_set, test_set, methods_to_check


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
    #read in line to get method calls
    for line in content:
        line = line.strip("[()]")
        pairs = line.split("), (")
        total_pairs = total_pairs + pairs
    for pair in total_pairs:
        invocation = pair.split("\", ")
        #invocation[0] is caller invocation[1] is callee and invocation[2] is number of times called
        #invocation [2] is not needed for this analysis, can throw away.
        for i in range(0, 2):
            invocation[i] = (invocation[i]).replace("\"", "")
        isATest = False
        #junit_torun is one string, split by space to get each test suite name
        testSuites = junit_torun.split(" ")
        #get package name from invocation, package name is package[0]
        package = invocation[0].split(":")
        #check if package name is a test suite. if so then it is a test.
        if package[0] in testSuites:
            isATest = True
        #if it is a test store in methods to tests
        if isATest:
            if invocation[1] in methods_to_tests.keys():
                methods_to_tests[invocation[1]].add(invocation[0])
            else:
                methods_to_tests[invocation[1]] = set([invocation[0]])
        #if not a test then it is a method calling another method
        else:
            if invocation[0] in nonTestMethodCalls.keys():
                for k in nonTestMethodCalls[invocation[0]]:
                    if k in nonTestMethodCalls:
                        nonTestMethodCalls[invocation[0]].union(nonTestMethodCalls[k])
            else:
                nonTestMethodCalls[invocation[0]] = set([invocation[1]])
        #for each caller that calls another method call, add tests for caller to callee
        for caller in nonTestMethodCalls:
            for callee in nonTestMethodCalls[caller]:
                if callee in methods_to_tests and caller in methods_to_tests:
                    methods_to_tests[callee].union(methods_to_tests[caller])
                elif caller in methods_to_tests:
                    methods_to_tests[callee] = methods_to_tests[caller]
    return methods_to_tests, nonTestMethodCalls


# one pass template
def one_inv_pass(go, cp, junit_torun, this_hash, refined_target_set, test_selection, analysis_only=False):

    if not analysis_only:
        git_adapter.checkout(this_hash)

    # maven_adapter.maven_clean()

    if SHOW_DEBUG_INFO:
        print "\n===full classpath===\n" + cp + "\n"

    java_cmd = " ".join(["java", "-cp", cp,
                         #                          "-Xms"+config.min_heap,
                         "-Xmx"+config.max_heap,
                         "-XX:+UseConcMarkSweepGC",
                         #                          "-XX:-UseGCOverheadLimit",
                         #"-XX:-UseSplitVerifier",  # FIXME: JDK 8- only!
                         ])

    # os.sys_call("mvn test -DskipTests", ignore_bad_exit=True)
    maven_adapter.compile_tests(this_hash)

    if SHOW_DEBUG_INFO:
        print "\n===junit torun===\n" + junit_torun + "\n"

    # v3.2, v4 execute with 4 core
    num_primary_workers = config.num_master_workers
    auto_parallel_targets = config.auto_fork
    slave_load = config.classes_per_fork
    target_map = daikon.target_s2m(refined_target_set)
    all_classes = target_map.keys()

    consider_expansion = (not analysis_only)

    if len(refined_target_set) <= num_primary_workers or (num_primary_workers == 1 and not auto_parallel_targets):
        single_set_tuple = (refined_target_set, "0")
        seq_get_invs(single_set_tuple, java_cmd, junit_torun, go, this_hash, consider_expansion, test_selection)
    elif num_primary_workers > 1:  # FIXME: this distributation is buggy
        target_set_inputs = []
        all_target_set_list = list(refined_target_set)
        each_bulk_size = int(len(refined_target_set) / num_primary_workers)

        seq_func = partial(seq_get_invs,
                           java_cmd=java_cmd, junit_torun=junit_torun, go=go, this_hash=this_hash,
                           consider_expansion=consider_expansion, test_selection=test_selection)
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
                           consider_expansion=consider_expansion, test_selection= test_selection)

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

    if config.compress_inv:
        os.remove_many_files(go, "*.inv.gz")
    else:
        os.remove_many_files(go, "*.inv")

    # include coverage report for compare
    if config.analyze_test_coverage and not analysis_only:
        try:
            maven_adapter.generate_test_report(go, this_hash)
        except:
            pass

    if not analysis_only:
        git.clear_temp_checkout(this_hash)


    if config.class_level_expansion:
        extra_expansion = get_expansion_set(go)
        os.remove_many_files(go, config.expansion_tmp_files + "*")
    else:
        extra_expansion = None

    return all_classes, extra_expansion


def mixed_passes(go, prev_hash, post_hash, refined_expansion_set,
                 refined_target_set, new_cp, old_junit_torun, new_junit_torun, test_selection):
    if config.class_level_expansion:
        impact_set = refined_target_set | refined_expansion_set
    else:
        impact_set = refined_target_set
    # checkout old commit, then checkout new tests
    git_adapter.checkout(prev_hash)
    new_test_path = maven_adapter.get_test_source_directory(prev_hash)
    os.sys_call(" ".join(["git", "checkout", post_hash, new_test_path]))
#     # may need to check whether it is compilable, return code?
#     os.sys_call("mvn clean test-compile")
    one_inv_pass(go, new_cp, new_junit_torun,
                 prev_hash + "_" + post_hash,
                 impact_set, test_selection, analysis_only=True)
    git.clear_temp_checkout(prev_hash)
    
    # checkout old commit, then checkout new src
    git_adapter.checkout(prev_hash)
    new_src_path = maven_adapter.get_source_directory(prev_hash)
    os.sys_call(" ".join(["git", "checkout", post_hash, new_src_path]))
#     # may need to check whether it is compilable, return code?
#     os.sys_call("mvn clean test-compile")

    one_inv_pass(go, new_cp, old_junit_torun,
                 post_hash + "_" + prev_hash,
                 impact_set, test_selection, analysis_only=True)
    git.clear_temp_checkout(prev_hash)


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
    old_mtd2ln = __build_target2ln(old_mtd_info_map)
    old_rts_purified = __purify_targets(old_rts)
    old_keyset = set(old_mtd2ln.keys())
    new_mtd2ln = __build_target2ln(new_mtd_info_map)
    new_rts_purified = __purify_targets(new_rts)
    new_keyset = set(new_mtd2ln.keys())
    for old_and_new in (old_rts_purified & new_rts_purified):
        mtd_full_info = old_and_new + "-" + old_mtd2ln[old_and_new] + "," + new_mtd2ln[old_and_new]
        result.add(mtd_full_info)
    for old_but_new in (old_rts_purified - new_rts_purified):
        if old_but_new in new_keyset:
            mtd_full_info = old_but_new + "-" + old_mtd2ln[old_but_new] + "," + new_mtd2ln[old_but_new]
        else:
            mtd_full_info = old_but_new + "-" + old_mtd2ln[old_but_new] + ",0"
        result.add(mtd_full_info)
    for new_but_old in (new_rts_purified - old_rts_purified):
        if new_but_old in old_keyset:
            mtd_full_info = new_but_old + "-" + old_mtd2ln[new_but_old] + "," + new_mtd2ln[new_but_old]
        else:
            mtd_full_info = new_but_old + "-0," + new_mtd2ln[new_but_old]
        result.add(mtd_full_info)
    return result


def _append_class_ln(class_set):
    result = set()
    for c in class_set:
        result.add(c + "-0,0")
    return result


def _common_specific_expansion(expansion, old_method_info_map, new_method_info_map):
    old_m2l = __build_method2line(old_method_info_map)
    new_m2l = __build_method2line(new_method_info_map)
    common_keys = set(old_m2l.keys()) & set(new_m2l.keys())
    result = set()
    for candidate in expansion:
        if candidate in common_keys:
            complete_info_name = candidate + "-" + old_m2l[candidate] + "," + new_m2l[candidate]
            result.add(complete_info_name)
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
    (old_common_package, old_test_set, old_refined_target_set,
     old_changed_methods, old_changed_tests, old_cp, old_junit_torun, old_method_info_map) = \
        one_info_pass(
            junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, prev_hash, targets,
            old_changed_methods, old_changed_tests, old_inner_dataflow_methods, old_outer_dataflow_methods, json_filepath)
    
    '''
        2-nd pass: checkout post_commit as detached head, and get new interested targets
    '''
    (new_common_package, new_test_set, new_refined_target_set,
     new_changed_methods, new_changed_tests, new_cp, new_junit_torun, new_method_info_map) = \
        one_info_pass(
            junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, post_hash, targets,
            new_changed_methods, new_changed_tests, new_inner_dataflow_methods, new_outer_dataflow_methods, json_filepath)


    '''
        middle pass: set common interests
    '''
    common_package = ''
    if old_common_package != '' and new_common_package != '':
        if (len(old_common_package) < len(new_common_package) and 
                (new_common_package+'.').find(old_common_package+'.') == 0):
            common_package = old_common_package
        elif (len(old_common_package) >= len(new_common_package) and 
                (old_common_package+'.').find(new_common_package+'.') == 0):
            common_package = old_common_package
    config.the_common_package.append(common_package)
#     refined_target_set = old_refined_target_set | new_refined_target_set
    refined_target_set, all_changed_methods, all_changed_tests = \
        _merge_target_sets(
            old_refined_target_set, new_refined_target_set, old_method_info_map, new_method_info_map), \
        _merge_target_sets(
            old_changed_methods, new_changed_methods, old_method_info_map, new_method_info_map), \
        _merge_target_sets(
            old_changed_tests, new_changed_tests, old_method_info_map, new_method_info_map)

    if json_filepath != "":
        test_selection = True
    else:
        test_selection = False
    '''
        3-rd pass: checkout prev_commit as detached head, and get invariants for all interesting targets
    '''
    old_all_classes, old_expansion = one_inv_pass(go,
        old_cp, old_junit_torun, prev_hash, refined_target_set, test_selection)
    
    '''
        4-th pass: checkout post_commit as detached head, and get invariants for all interesting targets
    '''
    new_all_classes, new_expansion = one_inv_pass(go,
        new_cp, new_junit_torun, post_hash, refined_target_set, test_selection)
    
    common_expansion = set()
    refined_expansion_set = set()
    if config.class_level_expansion:
        common_expansion = old_expansion & new_expansion
        refined_expansion_set = _common_specific_expansion(
            common_expansion, old_method_info_map, new_method_info_map)
    '''
        more passes: checkout mixed commits as detached head, and get invariants for all interesting targets
    '''
    if iso:
        mixed_passes(go, prev_hash, post_hash, refined_expansion_set,
                     refined_target_set, new_cp, old_junit_torun, new_junit_torun, test_selection)
    
    '''
        last pass: set common interests
    '''
    html.src_to_html_ln_anchor(refined_target_set, go, prev_hash, for_old=True)
    html.src_to_html_ln_anchor(refined_target_set, go, post_hash)
    
    # should not need line number information anymore from this point on
    
    '''
        prepare to return
    '''
    all_classes_set = set(old_all_classes + new_all_classes)
    all_classes_set = _append_class_ln(all_classes_set)
    
    print 'Center analysis is completed.'
    return common_package, all_classes_set, refined_target_set, \
        old_test_set, old_refined_target_set, new_test_set, new_refined_target_set, \
        old_changed_methods, new_changed_methods, old_changed_tests, new_changed_tests, \
        all_changed_methods, all_changed_tests

