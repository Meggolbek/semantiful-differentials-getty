from os import chdir

import config
import time
from tools import ex, git, os, maven_adapter


def checkout_build(commit_hash):
    # TODO: change maven adapter to checkout_build_output_dir path
    bin_path = maven_adapter.get_bin_path(commit_hash)
    src_rel_path = maven_adapter.get_source_directory(commit_hash)
    test_src_rel_path = maven_adapter.get_test_source_directory(commit_hash)

    # print "current src path (relative): " + src_rel_path + "\n"
    # print "current test src path (relative): " + test_src_rel_path + "\n"

    maven_adapter.compile_tests(commit_hash)

    # TODO copy to go/commit_hash

    return bin_path, src_rel_path, test_src_rel_path


def visit(villa_path, pwd, proj_dir, go, prev_hash, post_hash, pkg_prefix="-"):
    print("\n****************************************************************");
    print("        Getty Villa: Semantiful Differential Analyzer             ");
    print("****************************************************************\n");
    
    # print "current working directory: " + pwd + "\n"
    start_diff = time.clock()
    diff_out = go + "text.diff"
    os.sys_call(" ".join(["git diff",
                          str(config.git_diff_extra_ops),
                          "{0} {1} > {2}"]).format(prev_hash, post_hash, diff_out))
    diff = time.clock() - start_diff
    '''
        1-st pass: checkout prev_commit as detached head, and get all sets and etc, in simple (bare) mode (-s)
            remember to clear after this pass
    '''
    start_checkout_build0 = time.clock()
    bin_path, src_rel_path, test_src_rel_path = checkout_build(prev_hash)
    checkout_build0 = time.clock() - start_checkout_build0
    run_villa = "java -jar {0} -s {1} {2} {3} {4} {5} {6} -o {7}".format(
        villa_path, diff_out, bin_path, test_src_rel_path, pkg_prefix, prev_hash, post_hash, go)
    run_villa_l4ms = "java -jar {0} -l {1} {2} {3} -o {4}".format(
        villa_path, src_rel_path, test_src_rel_path, prev_hash, go)
    # print "\n\nstart to run Villa ... \n\n" + run_villa + "\n  and  \n" + run_villa_l4ms
    start_chdir1 = time.clock()
    chdir(proj_dir)
    chdir1 = time.clock() - start_chdir1
    start_run_villa_1 = time.clock()
    os.sys_call(run_villa)
    run_villa_1 = time.clock() - start_run_villa_1
    start_run_villa14_1 = time.clock()
    os.sys_call(run_villa_l4ms)
    run_villa14_1 = time.clock() - start_run_villa14_1
    start_chdir2 = time.clock()
    chdir(pwd)
    chdir2 = time.clock() - start_chdir2

    start_read_str_from1 = time.clock()
    old_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_old_{0}_.ex".format(prev_hash))
    old_all_methods = ex.read_str_from(go + "_getty_allmtd_src_{0}_.ex".format(prev_hash))
    old_l2m = ex.read_str_from(go + "_getty_fl2m_{0}_.ex".format(prev_hash))
    old_m2l = ex.read_str_from(go + "_getty_fm2l_{0}_.ex".format(prev_hash))
    old_changed_tests = ex.read_str_from(go + "_getty_chgmtd_test_old_{0}_.ex".format(prev_hash))
    read_str_from1 = time.clock() - start_read_str_from1
    start_git_clear_tmp_checkout1 = time.clock()
    git.clear_temp_checkout(prev_hash)
    git_clear_tmp_checkout1 = time.clock() - start_git_clear_tmp_checkout1
    '''
        2-nd pass: checkout post_commit as detached head, and get all sets and etc, in complex mode (-c)
            remember to clear after this pass
    '''
    start_checkout_build1 = time.clock()
    bin_path, src_rel_path, test_src_rel_path = checkout_build(post_hash)
    checkout_build1 = time.clock() - start_checkout_build1

    run_villa = "java -jar {0} -c {1} {2} {3} {4} {5} {6} -o {7}".format(
        villa_path, diff_out, bin_path, test_src_rel_path, pkg_prefix, prev_hash, post_hash, go)
    run_villa_l4ms = "java -jar {0} -l {1} {2} {3} -o {4}".format(
        villa_path, src_rel_path, test_src_rel_path, post_hash, go)
    # print "\n\nstart to run Villa ... \n\n" + run_villa + "\n  and  \n" + run_villa_l4ms
    start_chdir3 = time.clock()
    chdir(proj_dir)
    chdir3 = time.clock() - start_chdir3
    start_run_villa_2 = time.clock()
    os.sys_call(run_villa)
    run_villa_2 = time.clock() - start_run_villa_2
    start_run_villa14_2 = time.clock()
    os.sys_call(run_villa_l4ms)
    run_villa14_2 = time.clock() - start_run_villa14_2
    start_chdir4 = time.clock()
    chdir(pwd)
    chdir4 = time.clock() - start_chdir4

    start_read_str_from2 = time.clock()
    new_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_new_{0}_.ex".format(post_hash))
    new_improved_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_{0}_{1}_.ex".format(prev_hash, post_hash))
    new_removed_changed_methods = ex.read_str_from(
        go + "_getty_chgmtd_src_gone_{0}_{1}_.ex".format(prev_hash, post_hash))
    # TODO or FIXME
    # new_all_ccc_related = ex.read_str_from(go + "_getty_cccmtd_{0}_.ex".format(post_hash))  # not needed for now
    # new_all_cccs = ex.read_str_from(go + "_getty_ccc_{0}_.ex".format(post_hash))  # not needed for now
    new_all_methods = ex.read_str_from(go + "_getty_allmtd_src_{0}_.ex".format(post_hash))
    new_l2m = ex.read_str_from(go + "_getty_fl2m_{0}_.ex".format(post_hash))
    new_m2l = ex.read_str_from(go + "_getty_fm2l_{0}_.ex".format(post_hash))
    new_changed_tests = ex.read_str_from(go + "_getty_chgmtd_test_new_{0}_.ex".format(post_hash))
    read_str_from2 = time.clock() - start_read_str_from2

    start_git_clear_tmp_checkout2 = time.clock()
    git.clear_temp_checkout(post_hash)
    git_clear_tmp_checkout2 = time.clock() - start_git_clear_tmp_checkout2

    '''
        3-rd pass: checkout prev_commit as detached head, and get all sets and etc, in recovery mode (-r)
            remember to clear after this pass
    '''
    start_checkout_build2 = time.clock()
    bin_path, src_rel_path, test_src_rel_path = checkout_build(prev_hash)
    checkout_build2 = time.clock() - start_checkout_build2

    run_villa = "java -jar {0} -r {1} {2} {3} {4} {5} {6} -o {7}".format(
        villa_path, diff_out, bin_path, test_src_rel_path, pkg_prefix, prev_hash, post_hash, go)
    # print "\n\nstart to run Villa ... \n\n" + run_villa
    start_chdir5 = time.clock()
    chdir(proj_dir)
    chdir5 = time.clock() - start_chdir5
    start_run_villa_3 = time.clock()
    os.sys_call(run_villa)
    run_villa_3 = time.clock() - start_run_villa_3
    start_chdir6 = time.clock()
    chdir(pwd)
    chdir6 = time.clock() - start_chdir6

    start_read_str_from3 = time.clock()
    old_improved_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_{1}_{0}_.ex".format(prev_hash, post_hash))
    old_added_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_gain_{0}_{1}_.ex".format(prev_hash, post_hash))
    read_str_from3 = time.clock() - start_read_str_from3
    # TODO or FIXME
    # old_all_ccc_related = ex.read_str_from(go + "_getty_cccmtd_{0}_.ex".format(prev_hash))  # not needed for now
    # old_all_cccs = ex.read_str_from(go + "_getty_ccc_{0}_.ex".format(prev_hash))  # not needed for now

    start_git_clear_tmp_checkout3 = time.clock()
    git.clear_temp_checkout(prev_hash)
    git_clear_tmp_checkout3 = time.clock() - start_git_clear_tmp_checkout3

    print 'get text diff', diff
    print 'checkout build 0', checkout_build0
    print 'chrdir 1', chdir1
    print 'run villa 1', run_villa_1
    print 'run villa 14ms 1', run_villa14_1
    print 'chrdir 2', chdir2
    print 'read str from 1', read_str_from1
    print 'git clear tmp checkout 1', git_clear_tmp_checkout1
    print 'checkout build 1', checkout_build1
    print 'chdir 3', chdir3
    print 'run villa 2', run_villa_2
    print 'run villa 14ms 2', run_villa14_2
    print 'chdir 4', chdir4
    print 'read str from 2', read_str_from2
    print 'git clear temp checkout 2', git_clear_tmp_checkout2
    print 'check out build 2', checkout_build2
    print 'chdir 5', chdir5
    print 'run villa 3', run_villa_3
    print 'chdir 6', chdir6
    print 'read str from 3', read_str_from3
    print 'git clear tmp checkout 3', git_clear_tmp_checkout3

    print 'Villa analysis is completed.'
    return old_changed_methods, old_improved_changed_methods, old_added_changed_methods, \
           old_all_methods, old_l2m, old_m2l, \
           new_changed_methods, new_improved_changed_methods, new_removed_changed_methods, \
           new_all_methods, new_l2m, new_m2l, \
           old_changed_tests, new_changed_tests
