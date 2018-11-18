# all Daikon's usage for invariant analysis

import re
import sys
import time
import json
import copy
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
                        raw_method_name = all_dots_mtdname[last_dot_index + 1:]
                        further_last_dot_index = all_dots_mtdname[:last_dot_index].rfind(".")
                        if all_dots_mtdname[further_last_dot_index + 1:last_dot_index] == raw_method_name:
                            raw_method_name = "<init>"
                        candidates.add(
                            all_dots_mtdname[:last_dot_index] + ":" + raw_method_name +
                            full_method[leftp_bound:rightp_bound + 1].replace(" ", ""))
    os.remove_file(exp_tmp)
    ex.save_list_to(go + config.expansion_tmp_files + "." + this_hash +
                    "." + str(index) + "." + str(int(time.time())),
                    candidates)


# v4. flexible to be run in parallel, in daikon-online mode
def seq_get_invs(target_set_index_pair, java_cmd, junit_torun, go, this_hash, consider_expansion, test_selection):
    start_function_total = time.clock()
    start_get_index_and_target_set = time.clock()
    index = target_set_index_pair[1]
    target_set = target_set_index_pair[0]
    get_index_and_target_set = time.clock() - start_get_index_and_target_set
    # if test selection remove class from target set
    start_remove_classes_from_target_set = time.clock()
    if test_selection:
        ttarget_set = set(target_set)
        for s in ttarget_set:
            if not s.__contains__(":"):
                target_set.remove(s)
    remove_classes_from_target_set = time.clock() - start_remove_classes_from_target_set
    #     select_pattern = daikon.select_full(target_set)
    start_get_select_pattern = time.clock()
    select_pattern = daikon.dfformat_full_ordered(target_set, test_selection)
    get_select_pattern = time.clock() - start_get_select_pattern
    if SHOW_DEBUG_INFO:
        print "\n=== select pattern ===\n" + select_pattern + "\n"

    inv_gz = go + "_getty_inv_" + this_hash + "_." + index
    if config.compress_inv:
        inv_gz += ".inv.gz"
    else:
        inv_gz += ".inv"
    start_prep_for_daikon_call = time.clock()
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
    prep_for_daikon_call = time.clock() - start_prep_for_daikon_call
    # run Chicory + Daikon (online) for invariants without trace I/O
    run_chicory_daikon = \
        " ".join([java_cmd, "daikon.Chicory --daikon-online --exception-handling",
                  "--daikon-args=\"" + daikon_display_args,
                  "-o", inv_gz + "\"",
                  "--ppt-select-pattern=\"" + select_pattern + "\"",
                  junit_torun])
    if SHOW_DEBUG_INFO:
        print "\n=== Daikon:Chicory+Daikon(online) command to run: \n" + run_chicory_daikon
    start_daikon_call = time.clock()
    os.sys_call(run_chicory_daikon, ignore_bad_exit=True, cwd=ProjectUtils.get_version_path(this_hash))
    daikon_call = time.clock() - start_daikon_call

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

    start_get_classes_to_consider = time.clock()
    classes_to_consider = set()
    for tgt in all_to_consider:
        class_ref = tgt.split(':')[0]
        classes_to_consider.add(class_ref)
    get_classes_to_consider = time.clock() - start_get_classes_to_consider
    if SHOW_DEBUG_INFO:
        print "==== classes to consider: ", classes_to_consider, " hash: " + this_hash
    start_print_inv_for_each_class = time.clock()
    for tgt in classes_to_consider:
        # print "============ target is: " + tgt + ", pattern is: "+ daikon.dpformat_with_sigs(tgt) +" ==============="
        target_ff = daikon.fsformat_with_sigs(tgt)
        out_file = go + "_getty_inv__" + target_ff + "__" + this_hash + "_.inv.out"

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
                      "--ppt-select-pattern=\'" + daikon.dpformat_with_sigs(tgt)[:-1] + "[.:]" + "\'",
                      "--output", out_file, inv_gz])
        if SHOW_DEBUG_INFO:
            current_count += 1
            if config.show_regex_debug:
                print "\n\tthe regex for: " + tgt + "\n\t\t" + daikon.dpformat_with_sigs(tgt) + "\n"
            os.print_progress(current_count, total_count,
                              prefix='Progress(' + index + '):',
                              suffix='(' + str(current_count) + '/' + str(total_count) + ': ' + tgt + ')' + ' ' * 20,
                              bar_length=50)
        elif SHOW_MORE_DEBUG_INFO:
            print "\n=== Daikon:PrintInvs command to run: \n" + run_printinv
        os.sys_call(run_printinv, ignore_bad_exit=True, cwd=ProjectUtils.get_version_path(this_hash))
        sort_txt_inv(out_file)

        result = create_inv_out_file_per_method(out_file, all_to_consider, this_hash, go)
        if result is False:
            print "create_inv_out_file_per_method returned False"
    print_inv = time.clock() - start_print_inv_for_each_class
    start_remove_file = time.clock()
    os.remove_file(inv_gz)
    remove_file = time.clock() - start_remove_file
    function_total = time.clock() - start_function_total
    print "%%%%%%%%%%%% seq get invs %%%%%%%%%%%%%%%%%"
    print "function total: ", function_total
    print "get index and target set: ", get_index_and_target_set
    print "remove classes from target set: ", remove_classes_from_target_set
    print "get select pattern: ", get_select_pattern
    print "prep for daikon call: ", prep_for_daikon_call
    print "daikon call: ", start_daikon_call
    print "get classes to consider: ", get_classes_to_consider
    print "print inv for all classes: ", print_inv
    print "remove file: ", remove_file
    print "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%"


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
        changed_methods, changed_tests, json_filepath):
    start_maven_adapter_calls = time.clock()
    bin_path = maven_adapter.get_bin_path(this_hash)
    test_bin_path = maven_adapter.get_test_bin_path(this_hash)
    cp = maven_adapter.get_full_class_path(this_hash, junit_path, sys_classpath, bin_path, test_bin_path)
    maven_adapter_calls = time.clock() - start_maven_adapter_calls
    if SHOW_DEBUG_INFO:
        print "\n===full classpath===\n" + cp + "\n"

    # print "\ncopying all code to specific directory ...\n"
    start_maven_adapter_calls_for_directories = time.clock()
    all_code_dirs = [maven_adapter.get_source_directory(this_hash),
                     maven_adapter.get_test_source_directory(this_hash)]
    maven_adapter_calls_for_directories = time.clock() - start_maven_adapter_calls_for_directories
    start_copy_all_code = time.clock()
    getty_code_store = go + '_getty_allcode_' + this_hash + '_/'
    # print 'copy to ' + getty_code_store + '\n'
    makedirs(getty_code_store)
    for adir in all_code_dirs:
        os.sys_call(" ".join(["cp -r", adir + "/*", getty_code_store]), ignore_bad_exit=True)
    if config.use_special_junit_for_dyn:
        info_junit_path = os.rreplace(junit_path, config.default_junit_version, config.special_junit_version, 1)
        infocp = maven_adapter.get_full_class_path(this_hash, info_junit_path, sys_classpath, bin_path, test_bin_path)
    else:
        infocp = cp
    copy_all_code = time.clock() - start_copy_all_code
    start_maven_compile_tests = time.clock()
    maven_adapter.compile_tests(this_hash)
    maven_compile_tests = time.clock() - start_maven_compile_tests
    start_maven_junit_torun = time.clock()
    junit_torun = maven_adapter.get_junit_torun(cust_mvn_repo, this_hash)
    maven_junit_torun = time.clock() - start_maven_junit_torun
    if SHOW_DEBUG_INFO:
        print "\n===junit torun===\n" + junit_torun + "\n"

    #### dynamic run one round for all information
    start_daikon_common_prefixes = time.clock()
    prefixes = daikon.common_prefixes(target_set)
    daikon_common_prefixes = time.clock() - start_daikon_common_prefixes
    start_get_common_package = time.clock()
    common_package = ''
    if len(prefixes) == 1:
        last_period_index = prefixes[0].rindex('.')
        if last_period_index > 0:
            # the common package should be at least one period away from the rest
            common_package = prefixes[0][:last_period_index]
    get_common_package = time.clock() - start_get_common_package
    start_get_instrumentation_pattern = time.clock()
    prefix_regexes = []
    for p in prefixes:
        prefix_regexes.append(p + "*")
    instrument_regex = "|".join(prefix_regexes)
    get_instrumentation_pattern = time.clock() - start_get_instrumentation_pattern
    if SHOW_DEBUG_INFO:
        print "\n===instrumentation pattern===\n" + instrument_regex + "\n"

    if not path.exists(dyng_go):
        makedirs(dyng_go)
    start_run_instrumented_tests = time.clock()
    full_info_exfile = java.run_instrumented_tests(this_hash, go, infocp, agent_path, instrument_regex, junit_torun)
    run_instrumented_tests = time.clock() - start_run_instrumented_tests
    start_get_full_method_info_map = time.clock()
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
    get_full_method_info_map = time.clock() - start_get_full_method_info_map
    # print "dyng_go=", dyng_go, " go=", go
    start_merge_dyn_files = time.clock()
    os.merge_dyn_files(dyng_go, go, "_getty_dyncg_-hash-_.ex", this_hash)
    os.merge_dyn_files(dyng_go, go, "_getty_dynfg_-hash-_.ex", this_hash)
    merge_dyn_files = time.clock() - start_merge_dyn_files
    start_agency_caller_callee_and_pred_succ = time.clock()
    caller_of, callee_of = agency.caller_callee(go, this_hash)
    pred_of, succ_of = agency.pred_succ(go, this_hash)
    agency_caller_callee_and_pred_succ = time.clock() - start_agency_caller_callee_and_pred_succ
    start_get_target_set = time.clock()
    if json_filepath != "":
        junit_torun, target_set, test_set = get_tests_and_target_set(go, json_filepath, junit_torun, this_hash)
        get_target_set = time.clock() - start_get_target_set
    else:
        test_set = agency.get_test_set_dyn(callee_of, junit_torun)
        get_target_set = time.clock() - start_get_target_set

    # test_set is correct
    # reset target set here
    start_agency_refine_targets = time.clock()
    refined_target_set, changed_methods, changed_tests = \
        agency.refine_targets(full_method_info_map, target_set, test_set,
                              caller_of, callee_of, pred_of, succ_of,
                              changed_methods, changed_tests, json_filepath)
    agency_refine_targets = time.clock() - start_agency_refine_targets
    start_profiler_log_csv = time.clock()
    profiler.log_csv(["method_count", "test_count", "refined_target_count"],
                     [[len(target_set), len(test_set), len(refined_target_set)]],
                     go + "_getty_y_method_count_" + this_hash + "_.profile.readable")
    profiler_log_csv = time.clock() - start_profiler_log_csv
    start_git_clear_temp_checkout = time.clock()
    git.clear_temp_checkout(this_hash)
    git_clear_temp_checkout = time.clock() - start_git_clear_temp_checkout
    print "---------In Center Info Pass------"
    print "maven adapter calls: ", maven_adapter_calls
    print "maven adapter calls for directories: ", maven_adapter_calls_for_directories
    print "copy all code: ", copy_all_code
    print "maven compile tests: ", maven_compile_tests
    print "maven junit to run: ", maven_junit_torun
    print "daikon common prefixes: ", daikon_common_prefixes
    print "get common package: ", get_common_package
    print "get instrumentation pattern: ", get_instrumentation_pattern
    print "run instrumented tests: ", run_instrumented_tests
    print "get full method info map: ", get_full_method_info_map
    print "merge dynamic files: ", merge_dyn_files
    print "agency caller callee and pred succ: ", agency_caller_callee_and_pred_succ
    print "get target set: ", get_target_set
    print "agency refine targets: ", agency_refine_targets
    print "profiler log csv: ", profiler_log_csv
    print "git clear tmp checkout: ", git_clear_temp_checkout
    print "---------------------------------------"
    return common_package, test_set, refined_target_set, changed_methods, changed_tests, \
           cp, junit_torun, full_method_info_map


def get_tests_and_target_set(go, json_filepath, junit_torun, this_hash):
    # have to add junit runner to junit_to_run in order to get invariants
    junits_to_run = junit_torun.split(" ")
    junit_to_run = junits_to_run[0]
    #getting method -> tests
    fname = go + "_getty_dyncg_" + this_hash + "_.ex"
    methods_to_tests, nontest_method_calls = create_methods_to_tests(fname, junit_torun)
    # get types_to_methods
    types_to_methods = read_in_types_to_methods(go, this_hash)
    # get priority list from json file
    with open(json_filepath) as f:
        priorities = json.load(f)
    test_set = set()
    target_set = set()
    nontest_method_calls, methods_to_tests = refine_method_to_tests(priorities, nontest_method_calls, methods_to_tests)
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
                        target_set, test_set= add_to_targetset(methods_to_tests, method, target_set, test_set,
                                                                                  types_to_methods)
        # else priority is not a test
        else:
            target_set, test_set= add_to_targetset(methods_to_tests, priority, target_set, test_set, types_to_methods)
    # for each method in target set check if it calls another method
    # if so add that method to methods to check and target set
    check_target_set = copy.deepcopy(target_set)
    for target in check_target_set:
        method_name = target.split("-")[0] + "("
        for method in nontest_method_calls.keys():
            if method[:len(method_name)] == method_name:
                for callee in nontest_method_calls[method]:
                    callee_name = callee[:(callee.rfind("("))]
                    target_set, test_set = add_to_targetset(methods_to_tests, callee_name, target_set, test_set,
                                                           types_to_methods)
    # add each corresponding junit suite to junit to run
    tests_for_junit = set()
    for test in test_set:
        i = test.rfind(":")
        temp = test[:i]
        tests_for_junit.add(temp)
    for temp in tests_for_junit:
        junit_to_run = junit_to_run + " " + temp
    junit_torun = junit_to_run
    return junit_torun, target_set, test_set


def add_to_targetset(methods_to_tests, target, target_set, test_set, types_to_methods):
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
    return target_set, test_set


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
    # read in line to get method calls
    for line in content:
        line = line.strip("[()]")
        pairs = line.split("), (")
        total_pairs = total_pairs + pairs
    for pair in total_pairs:
        invocation = pair.split("\", ")
        # invocation[0] is caller invocation[1] is callee and invocation[2] is number of times called
        # invocation [2] is not needed for this analysis, can throw away.
        for i in range(0, 2):
            invocation[i] = (invocation[i]).replace("\"", "")
        isATest = False
        # junit_torun is one string, split by space to get each test suite name
        testSuites = junit_torun.split(" ")
        # get package name from invocation, package name is package[0]
        package = invocation[0].split(":")
        # check if package name is a test suite. if so then it is a test.
        if package[0] in testSuites:
            isATest = True
        # if it is a test store in methods to tests
        if isATest:
            if invocation[1] in methods_to_tests.keys():
                methods_to_tests[invocation[1]].add(invocation[0])
            else:
                methods_to_tests[invocation[1]] = set([invocation[0]])
        # if not a test then it is a method calling another method
        else:
            if invocation[0] in nonTestMethodCalls.keys():
                nonTestMethodCalls[invocation[0]].add(invocation[1])
            else:
                nonTestMethodCalls[invocation[0]] = set([invocation[1]])
    return methods_to_tests, nonTestMethodCalls


def refine_method_to_tests(priorities, nonTestMethodCalls, methods_to_tests):
    # only do this for methods connected to priority methods
    # get mapping from methods to methods that are called in that method
    # example: a calls b and b calls c, a maps to b and c (goes all the way down to leaf nodes)
    methodsToConsider = set(priorities)
    mergeable = set()
    methodCalls = copy.deepcopy(nonTestMethodCalls)
    while methodsToConsider:
        callers = methodsToConsider
        nonMergeable = set()
        for caller in callers:
            mCalls = copy.deepcopy(methodCalls)
            if caller in methodCalls:
                for callee in methodCalls[caller]:
                    if callee in mCalls.keys():
                        if caller in mCalls[callee]:
                            for callee2 in nonTestMethodCalls[callee]:
                                if callee2 not in nonTestMethodCalls[caller] and caller != callee2:
                                    mCalls[caller].add(callee2)
                            nonTestMethodCalls[caller].update(nonTestMethodCalls[callee])
                            nonTestMethodCalls[caller].remove(caller)
                            mCalls[caller].remove(callee)
                            for callee2 in nonTestMethodCalls[caller]:
                                if callee2 not in nonTestMethodCalls[callee] and callee != callee2:
                                    mCalls[callee].add(callee2)
                            nonTestMethodCalls[callee].update(nonTestMethodCalls[caller])
                            nonTestMethodCalls[callee].remove(callee)
                            mCalls[callee].remove(caller)
                        else:
                            nonMergeable.add(caller)
                            if callee not in methodsToConsider:
                                nonMergeable.add(callee)
                    if callee in mergeable:
                        nonTestMethodCalls[caller].update(nonTestMethodCalls[callee])
                        mCalls[caller].remove(callee)
            methodCalls = mCalls
            if caller not in nonMergeable and caller in nonTestMethodCalls.keys():
                mergeable.add(caller)
        methodsToConsider = nonMergeable
    # update methods to tests with non test method calls
    for method in methods_to_tests.keys():
        if method in nonTestMethodCalls.keys():
            for callee in nonTestMethodCalls[method]:
                if callee in methods_to_tests.keys():
                    methods_to_tests[callee].update(methods_to_tests[method])
                else:
                    methods_to_tests[callee] = methods_to_tests[method]
    return nonTestMethodCalls, methods_to_tests

# one pass template
def one_inv_pass(go, cp, junit_torun, this_hash, refined_target_set, test_selection, analysis_only=False):
    start_git_adapter_checkout = time.clock()
    if not analysis_only:
        git_adapter.checkout(this_hash)
    git_adapter_checkout = time.clock() - start_git_adapter_checkout

    if SHOW_DEBUG_INFO:
        print "\n===full classpath===\n" + cp + "\n"

    java_cmd = " ".join(["java", "-cp", cp,
                         #                          "-Xms"+config.min_heap,
                         "-Xmx" + config.max_heap,
                         "-XX:+UseConcMarkSweepGC",
                         #                          "-XX:-UseGCOverheadLimit",
                         # "-XX:-UseSplitVerifier",  # FIXME: JDK 8- only!
                         ])
    start_maven_adapter_compile_tests = time.clock()
    maven_adapter.compile_tests(this_hash)
    maven_adapter_compile_tests = time.clock() - start_maven_adapter_compile_tests

    if SHOW_DEBUG_INFO:
        print "\n===junit torun===\n" + junit_torun + "\n"

    # v3.2, v4 execute with 4 core
    start_set_up_for_seq_get_invs = time.clock()
    num_primary_workers = config.num_master_workers
    auto_parallel_targets = config.auto_fork
    slave_load = config.classes_per_fork
    target_map = daikon.target_s2m(refined_target_set)
    all_classes = target_map.keys()

    consider_expansion = (not analysis_only)
    set_up_for_seq_get_invs = time.clock() - start_set_up_for_seq_get_invs
    inside_parallelization = 0
    start_seq_get_invs = time.clock()

    if len(refined_target_set) <= num_primary_workers or (num_primary_workers == 1 and not auto_parallel_targets):
        start_inside_parallelization = time.clock()
        single_set_tuple = (refined_target_set, "0")
        seq_get_invs(single_set_tuple, java_cmd, junit_torun, go, this_hash, consider_expansion, test_selection)
        inside_parallelization = time.clock() - start_inside_parallelization
        print "here 1"
    elif num_primary_workers > 1:  # FIXME: this distributation is buggy
        start_inside_parallelization = time.clock()
        target_set_inputs = []
        all_target_set_list = list(refined_target_set)
        each_bulk_size = int(len(refined_target_set) / num_primary_workers)

        seq_func = partial(seq_get_invs,
                           java_cmd=java_cmd, junit_torun=junit_torun, go=go, this_hash=this_hash,
                           consider_expansion=consider_expansion, test_selection=test_selection)
        for i in range(num_primary_workers):
            if not (i == num_primary_workers - 1):
                sub_list_tuple = (all_target_set_list[each_bulk_size * i:each_bulk_size * (i + 1)], str(i))
                target_set_inputs.append(sub_list_tuple)
            else:
                sub_list_tuple = (all_target_set_list[each_bulk_size * i:], str(i))
                target_set_inputs.append(sub_list_tuple)
        input_pool = Pool(num_primary_workers)
        input_pool.map(seq_func, target_set_inputs)
        input_pool.close()
        input_pool.join()
        inside_parallelization = time.clock() - start_inside_parallelization
        print "here 2"
    elif num_primary_workers == 1 and auto_parallel_targets and slave_load >= 1:
        # elastic automatic processing
        start_inside_parallelization = time.clock()
        target_set_inputs = []
        num_processes = 0

        # target_map has been calculated already
        # target_map = daikon.target_s2m(refined_target_set)
        # all_classes = target_map.keys()
        num_keys = len(all_classes)
        seq_func = partial(seq_get_invs,
                           java_cmd=java_cmd, junit_torun=junit_torun, go=go, this_hash=this_hash,
                           consider_expansion=consider_expansion, test_selection=test_selection)
        start_for_loop = time.clock()
        for i in range(0, num_keys, slave_load):
            # (inclusive) lower bound is i
            # (exclusive) upper bound:
            j = min(i + slave_load, num_keys)
            sublist = []
            for k in range(i, j):
                the_key = all_classes[k]
                sublist.append(the_key)  # so it won't miss class/object invariants
                sublist += target_map[the_key]
            sublist_tuple = (sublist, str(num_processes))
            target_set_inputs.append(sublist_tuple)
            num_processes += 1
        for_loop = time.clock() - start_for_loop
        max_parallel_processes = config.num_slave_workers
        start_profiler_log = time.clock()
        if not analysis_only:
            profiler.log_csv(["class_count", "process_count", "max_parallel_processes", "slave_load"],
                             [[num_keys, num_processes, max_parallel_processes, slave_load]],
                             go + "_getty_y_elastic_count_" + this_hash + "_.profile.readable")
        profiler_log = time.clock() - start_profiler_log
        start_create_pool = time.clock()
        input_pool = Pool(max_parallel_processes)
        create_pool = time.clock() - start_create_pool
        start_map = time.clock()
        input_pool.map(seq_func, target_set_inputs)
        map_time = time.clock() - start_map
        start_close = time.clock()
        input_pool.close()
        close = time.clock() - start_close
        start_join = time.clock()
        input_pool.join()
        join = time.clock() - start_join
        inside_parallelization = time.clock() - start_inside_parallelization
        print "here 3"
        print "create pool: ", create_pool
        print "map time: ", map_time
        print "close: ", close
        print "join: ", join
        print "---------___----------"
    else:
        print "\nIncorrect option for one center pass:"
        print "\tnum_primary_workers:", str(num_primary_workers)
        print "\tauto_parallel_targets:", str(auto_parallel_targets)
        print "\tslave_load", str(slave_load)
        sys.exit(1)
    seq_get_invs_time = time.clock() - start_seq_get_invs
    start_remove_files = time.clock()
    if config.compress_inv:
        os.remove_many_files(go, "*.inv.gz")
    else:
        os.remove_many_files(go, "*.inv")
    remove_files = time.clock() - start_remove_files

    # include coverage report for compare
    if config.analyze_test_coverage and not analysis_only:
        try:
            maven_adapter.generate_test_report(go, this_hash)
        except:
            pass
    start_git_clear_tmp_checkout = time.clock()
    if not analysis_only:
        git.clear_temp_checkout(this_hash)
    git_clear_tmp_checkout = time.clock() - start_git_clear_tmp_checkout

    if config.class_level_expansion:
        extra_expansion = get_expansion_set(go)
        os.remove_many_files(go, config.expansion_tmp_files + "*")
    else:
        extra_expansion = None
    print "*************** one inv pass *****************"
    print "git adapter checkout: ", git_adapter_checkout
    print "maven adapter compile tests: ", maven_adapter_compile_tests
    print "set up for seq get invs: ", set_up_for_seq_get_invs
    print "seq get invs: ", seq_get_invs_time
    print "inside parallelization: ", inside_parallelization
    print "remove files: ", remove_files
    print "git clear tmp checkout: ", git_clear_tmp_checkout
    print "**********************************************"

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
        result[fullinfo[:last_dash]] = fullinfo[last_dash + 1:]
    return result


def __build_method2line(method_info_map):
    result = {}
    for k in method_info_map:
        full_method = method_info_map[k]
        last_dash = full_method.rfind("-")
        if last_dash != -1:
            result[full_method[:last_dash]] = full_method[last_dash + 1:]
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
          old_changed_methods, old_changed_tests, new_changed_methods, new_changed_tests, json_filepath):
    dyng_go = separate_go[0]
    go = separate_go[1]

    print("\n****************************************************************");
    print("        Getty Center: Semantiful Differential Analyzer            ");
    print("****************************************************************\n");

    '''
        1-st pass: checkout prev_commit as detached head, and get new interested targets
    '''
    start_first_one_info = time.clock()
    (old_common_package, old_test_set, old_refined_target_set,
     old_changed_methods, old_changed_tests, old_cp, old_junit_torun, old_method_info_map) = \
        one_info_pass(
            junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, prev_hash, targets,
            old_changed_methods, old_changed_tests, json_filepath)
    first_one_info = time.clock() - start_first_one_info
    '''
        2-nd pass: checkout post_commit as detached head, and get new interested targets
    '''
    start_second_one_info = time.clock()
    (new_common_package, new_test_set, new_refined_target_set,
     new_changed_methods, new_changed_tests, new_cp, new_junit_torun, new_method_info_map) = \
        one_info_pass(
            junit_path, sys_classpath, agent_path, cust_mvn_repo, dyng_go, go, post_hash, targets,
            new_changed_methods, new_changed_tests, json_filepath)
    second_one_info = time.clock() - start_second_one_info

    '''
        middle pass: set common interests
    '''
    start_get_common_packages = time.clock()
    common_package = ''
    if old_common_package != '' and new_common_package != '':
        if (len(old_common_package) < len(new_common_package) and
                (new_common_package + '.').find(old_common_package + '.') == 0):
            common_package = old_common_package
        elif (len(old_common_package) >= len(new_common_package) and
              (old_common_package + '.').find(new_common_package + '.') == 0):
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

    get_common_packages = time.clock() - start_get_common_packages
    if json_filepath != "":
        test_selection = True
    else:
        test_selection = False
    '''
        3-rd pass: checkout prev_commit as detached head, and get invariants for all interesting targets
    '''
    start_first_one_inv = time.clock()
    old_all_classes, old_expansion = one_inv_pass(go,
                                                  old_cp, old_junit_torun, prev_hash, refined_target_set,
                                                  test_selection)
    first_one_inv = time.clock() - start_first_one_inv
    '''
        4-th pass: checkout post_commit as detached head, and get invariants for all interesting targets
    '''
    start_second_one_inv = time.clock()
    new_all_classes, new_expansion = one_inv_pass(go,
                                                  new_cp, new_junit_torun, post_hash, refined_target_set,
                                                  test_selection)
    second_one_inv = time.clock() - start_second_one_inv
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
    start_set_common_interesets = time.clock()
    html.src_to_html_ln_anchor(refined_target_set, go, prev_hash, for_old=True)
    html.src_to_html_ln_anchor(refined_target_set, go, post_hash)
    set_common_interesets = time.clock() - start_set_common_interesets
    # should not need line number information anymore from this point on

    '''
        prepare to return
    '''
    start_get_all_classes = time.clock()
    all_classes_set = set(old_all_classes + new_all_classes)
    all_classes_set = _append_class_ln(all_classes_set)
    get_all_classes = time.clock() - start_get_all_classes

    print "first one info: ", first_one_info
    print "second one info: ", second_one_info
    print "common packages: ", get_common_packages
    print "one inv pass: ", first_one_inv
    print "second inv pass: ", second_one_inv
    print "set common interests: ", set_common_interesets
    print "get all classes: ", get_all_classes
    print 'Center analysis is completed.'
    return common_package, all_classes_set, refined_target_set, \
           old_test_set, old_refined_target_set, new_test_set, new_refined_target_set, \
           old_changed_methods, new_changed_methods, old_changed_tests, new_changed_tests, \
           all_changed_methods, all_changed_tests
