# maven calls

import re, subprocess
import time

import config
from tools.os import sys_call, from_sys_call_enforce


# FIXME: support multi-module project
def path_from_mvn_call(env):
    start = time.time()
    if env not in ["sourceDirectory", "scriptSourceDirectory", "testSourceDirectory", 
                   "outputDirectory", "testOutputDirectory", "directory"]:
        raise ValueError("incorrect env var: " + env)
    mvn_cmd = "mvn help:evaluate -Dexpression=project.build." + env + " | grep ^/"
    print "mvn path_from_mvn_call:: mvn cmd" + str((time.time() - start))
    return subprocess.check_output(mvn_cmd, shell=True).strip()


# IMPROVE: supported multi-module project, but make it module-specific when needed
def classpath_from_mvn_call():
    mvn_cmd = "mvn dependency:build-classpath | grep ^\/"
    start = time.time()
    output = subprocess.check_output(mvn_cmd, shell=True).strip()
    print "mvn classpath_from_mvn_call:: check_output" + str((time.time() - start))
    start = time.time()
    all_paths = set()
    classpaths = output.split("\n")
    for classpath in classpaths:
        classpath = classpath.strip()
        for one_path in classpath.split(":"):
            if one_path not in all_paths:
                all_paths.add(one_path)
    print "mvn classpath_from_mvn_call:: all paths" + str((time.time() - start))
    start = time.time()
    merged = "."
    for path in all_paths:
        merged += (":" + path)
    print "mvn classpath_from_mvn_call:: merged" + str((time.time() - start))
    return merged


# without considering target folders
def full_env_classpath():
    return classpath_from_mvn_call() + ":$CLASSPATH"


# include target folders
def full_classpath(junit_path, sys_classpath, bin_output, test_output):
    return ":".join([junit_path, classpath_from_mvn_call(), sys_classpath, bin_output, test_output])


def junit_torun_str(cust_mvn_repo):
    if config.no_mvn_customization:
        start = time.time()
        extract_cmd = "mvn test -q | grep ^Running\ *"
        print '\nRunning tests to get all test & test cases ...'
        cmd_output = from_sys_call_enforce(extract_cmd).strip()
        print "mvn junit_torun_str:: from sys call enforce" + str((time.time() - start))
        start = time.time()
        filtered = []
        matching = "Running (.*)"
        for candidate in cmd_output.split('\n'):
            m = re.match(matching, candidate.strip())
            if m and len(m.groups()) > 0:
                filtered.append(m.group(1).strip().split(' ')[0])
        print "mvn junit_torun_str:: get filtered" + str((time.time() - start))
        return " ".join(["org.junit.runner.JUnitCore"] + filtered)
    else:
        #start = time.time()
        local_repo = ""
        if config.effortless_mvn_setup:
            local_repo = "-Dmaven.repo.local=" + cust_mvn_repo
        mvn_cmd = "mvn " + local_repo + \
            " org.apache.maven.plugins:maven-surefire-plugin:2.19.2-SNAPSHOT:test" + \
            " | " + "grep __for__getty__\ __junit"
        output_raw = subprocess.check_output(mvn_cmd, shell=True).strip()
        start_index = output_raw.index("__for__getty__ __junit")
        if start_index == -1:
            raise
        elif start_index == 0:
            print "\nNormal customized surefire output starting at index 0"
            output = output_raw.split("\n")
        elif start_index == 10:
            print "\nCustomized surefire output starting at index 10, possibly with WARNING:"
            print output_raw
            output = output_raw[start_index:].split("\n")
        elif start_index > 10:
            print "\nCustomized surefire output starting at an abnormal index: " + str(start_index)
            print output_raw
            output = output_raw[start_index:].split("\n")
        else:
            raise
        #print "mvn junit_torun_str:: in else series of if statments" + str((time.time() - start))
        #start.time.time()
        merged_run = {}
        for junit_torun in output:
            junit_torun = junit_torun.strip()
            # vsn = junit_torun[17:23]
            to_run_list = junit_torun[26:].split(" ")
            runner = to_run_list[0]
            test_classes = set(to_run_list[1:])
            if runner in merged_run:
                merged_run[runner] = (test_classes | merged_run[runner])
            else:
                merged_run[runner] = test_classes
        #print "mvn junit_torun_str:: in else for statement" + str((time.time() - start))
        #start = time.time()
        if len(merged_run) < 1:
            raise NotImplementedError("this project is not using junit")
        elif len(merged_run) == 1:
            junit_runner = merged_run.keys()[0]
         #   print "mvn junit_torun_str:: in else before return" + str((time.time() - start))
            return " ".join([junit_runner] + list(merged_run[junit_runner]))
        else:
            raise NotImplementedError("multiple junit versions are used in this project")


# include coverage report for compare
def generate_coverage_report(go, curr_hash):
    sys_call("mvn emma:emma", ignore_bad_exit=True)
    emma_dir = path_from_mvn_call("directory") + "/site/emma"
    target_dir = go + "_getty_emma_" + curr_hash + "_"
    sys_call(" ".join(["mv", emma_dir, target_dir]), ignore_bad_exit=True)
