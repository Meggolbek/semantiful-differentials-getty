from os import chdir

import config
from tools import ex, git, os, maven_adapter


def checkout_build(commit_hash):
    # TODO: change maven adapter to checkout_build_output_dir path
    bin_path = maven_adapter.get_bin_path(commit_hash)
    src_rel_path = maven_adapter.get_source_directory(commit_hash)
    test_src_rel_path = maven_adapter.get_test_source_directory(commit_hash)

    print "current src path (relative): " + src_rel_path + "\n"
    print "current test src path (relative): " + test_src_rel_path + "\n"

    maven_adapter.compile_tests(commit_hash)

    # TODO copy to go/commit_hash

    return bin_path, src_rel_path, test_src_rel_path


def visit(villa_path, pwd, proj_dir, go, prev_hash, post_hash, pkg_prefix="-"):
    print("\n****************************************************************");
    print("        Getty Villa: Semantiful Differential Analyzer             ");
    print("****************************************************************\n");

    print "current working directory: " + pwd + "\n"

    diff_out = go + "text.diff"
    os.sys_call(" ".join(["git diff",
                          str(config.git_diff_extra_ops),
                          "{0} {1} > {2}"]).format(prev_hash, post_hash, diff_out))

    '''
        1-st pass: checkout prev_commit as detached head, and get all sets and etc, in simple (bare) mode (-s)
            remember to clear after this pass
    '''
    bin_path, src_rel_path, test_src_rel_path = checkout_build(prev_hash)
    run_villa = "java -jar {0} -s {1} {2} {3} {4} {5} {6} -o {7}".format(
        villa_path, diff_out, bin_path, test_src_rel_path, pkg_prefix, prev_hash, post_hash, go)
    run_villa_l4ms = "java -jar {0} -l {1} {2} {3} -o {4}".format(
        villa_path, src_rel_path, test_src_rel_path, prev_hash, go)
    print "\n\nstart to run Villa ... \n\n" + run_villa + "\n  and  \n" + run_villa_l4ms
    chdir(proj_dir)
    os.sys_call(run_villa)
    os.sys_call(run_villa_l4ms)
    chdir(pwd)

    old_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_old_{0}_.ex".format(prev_hash))
    old_all_methods = ex.read_str_from(go + "_getty_allmtd_src_{0}_.ex".format(prev_hash))
    old_l2m = ex.read_str_from(go + "_getty_fl2m_{0}_.ex".format(prev_hash))
    old_m2l = ex.read_str_from(go + "_getty_fm2l_{0}_.ex".format(prev_hash))
    old_changed_tests = ex.read_str_from(go + "_getty_chgmtd_test_old_{0}_.ex".format(prev_hash))

    git.clear_temp_checkout(prev_hash)

    '''
        2-nd pass: checkout post_commit as detached head, and get all sets and etc, in complex mode (-c)
            remember to clear after this pass
    '''
    bin_path, src_rel_path, test_src_rel_path = checkout_build(post_hash)

    run_villa = "java -jar {0} -c {1} {2} {3} {4} {5} {6} -o {7}".format(
        villa_path, diff_out, bin_path, test_src_rel_path, pkg_prefix, prev_hash, post_hash, go)
    run_villa_l4ms = "java -jar {0} -l {1} {2} {3} -o {4}".format(
        villa_path, src_rel_path, test_src_rel_path, post_hash, go)
    print "\n\nstart to run Villa ... \n\n" + run_villa + "\n  and  \n" + run_villa_l4ms
    chdir(proj_dir)
    os.sys_call(run_villa)
    os.sys_call(run_villa_l4ms)
    chdir(pwd)

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

    git.clear_temp_checkout(post_hash)

    '''
        3-rd pass: checkout prev_commit as detached head, and get all sets and etc, in recovery mode (-r)
            remember to clear after this pass
    '''
    bin_path, src_rel_path, test_src_rel_path = checkout_build(prev_hash)

    run_villa = "java -jar {0} -r {1} {2} {3} {4} {5} {6} -o {7}".format(
        villa_path, diff_out, bin_path, test_src_rel_path, pkg_prefix, prev_hash, post_hash, go)
    print "\n\nstart to run Villa ... \n\n" + run_villa
    chdir(proj_dir)
    os.sys_call(run_villa)
    chdir(pwd)

    old_improved_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_{1}_{0}_.ex".format(prev_hash, post_hash))
    old_added_changed_methods = ex.read_str_from(go + "_getty_chgmtd_src_gain_{0}_{1}_.ex".format(prev_hash, post_hash))
    # TODO or FIXME
    # old_all_ccc_related = ex.read_str_from(go + "_getty_cccmtd_{0}_.ex".format(prev_hash))  # not needed for now
    # old_all_cccs = ex.read_str_from(go + "_getty_ccc_{0}_.ex".format(prev_hash))  # not needed for now

    git.clear_temp_checkout(prev_hash)

    print 'Villa analysis is completed.'
    return old_changed_methods, old_improved_changed_methods, old_added_changed_methods, \
           old_all_methods, old_l2m, old_m2l, \
           new_changed_methods, new_improved_changed_methods, new_removed_changed_methods, \
           new_all_methods, new_l2m, new_m2l, \
           old_changed_tests, new_changed_tests
