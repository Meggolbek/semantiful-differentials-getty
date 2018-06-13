import mvn, os, git_adapter

def maven_clean():
    os.sys_call("mvn clean")

def get_bin_path(hash):
    return mvn.path_from_mvn_call("outputDirectory")

def get_test_bin_path(hash):
    return mvn.path_from_mvn_call("testOutputDirectory")

def get_source_directory(hash):
    return mvn.path_from_mvn_call("sourceDirectory")

def get_test_source_directory(hash):
    return mvn.path_from_mvn_call("testSourceDirectory")

def get_all_source_directories(hash):
    git_adapter.checkout(hash)
    maven_clean()
    return get_source_directory(hash), get_test_source_directory(hash)

def get_full_class_path(hash, junit_path, sys_classpath):
    git_adapter.checkout(hash)
    maven_clean()
    bin_path = get_bin_path(hash)
    test_bin_path = get_test_bin_path(hash)
    return mvn.full_classpath(junit_path, sys_classpath, bin_path, test_bin_path)

def prep_for_run_villa(hash):
    git_adapter.checkout(hash)
    maven_clean()
    bin_path = get_bin_path(hash)
    src_rel_path, test_src_rel_path = get_all_source_directories(hash)
    compile_tests(hash)
    return bin_path, src_rel_path, test_src_rel_path

def compile_tests(hash):
    # git_adapter.checkout(hash)
    # maven_clean()
    os.sys_call("mvn test-compile")

def get_junit_torun(cust_mvn_repo, hash):
    git_adapter.checkout(hash)
    maven_clean()
    compile_tests(hash)
    return mvn.junit_torun_str(cust_mvn_repo)

def generate_test_report(go, hash):
    git_adapter.checkout(hash)
    maven_clean()
    mvn.generate_coverage_report(go, hash)