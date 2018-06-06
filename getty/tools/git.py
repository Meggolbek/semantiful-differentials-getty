# git calls

import re
import time

from tools.os import from_sys_call, sys_call


def get_hash(hash_exp, short=True):
    arg_list = ["git", "rev-parse"]
    if short:
        arg_list.append("--short")
    arg_list.append(hash_exp)
    return from_sys_call(" ".join(arg_list)).strip()




# deprecated
# def get_hash_for(which, short=True):
#     if short:
#         return from_sys_call("git rev-parse --short " + which).strip()
#     else:
#         return from_sys_call("git rev-parse " + which).strip()




# deprecated
# def get_parent_hash():
#     two_hash_str = from_sys_call("git rev-list --max-count=2 --first-parent --topo-order HEAD").strip()
#     current, parent = two_hash_str.split("\n")
#     verify_parent = from_sys_call("git rev-parse HEAD^").strip()
#     if parent == verify_parent:
#         return parent
#     else:
#         raise ValueError(
#             "parent commit hash disagree, rev-list-first-parent-topo-order vs. HEAD^: {0} vs {1}".\
#             format(parent, verify_parent))




def get_head_ancestor(index, short=True):
    if short:
        return from_sys_call("git rev-parse --short HEAD~" + index).strip()
    else:
        return from_sys_call("git rev-parse HEAD~" + index).strip()




def get_ancestor_hash(ahash, index=None, short=True):
    arg_list = ["git", "rev-parse"]
    if short:
        arg_list.append("--short")
    the_hash = ahash
    if index is not None:
        the_hash = ahash + "~" + index
    arg_list.append(the_hash)
    return from_sys_call(" ".join(arg_list)).strip()




def get_remote_head():
    rbs = from_sys_call("git branch -r").strip()
    all_remote_branches = set()
    for rb in rbs.split("\n"):
        rb = rb.strip().split(" ")[0]
        all_remote_branches.add(rb)
    if "origin/HEAD" in all_remote_branches:
        return "origin/HEAD"
    elif "origin/master" in all_remote_branches:
        return "origin/master"
    elif "origin/trunk" in all_remote_branches:
        return "origin/trunk"
    else:
        raise ValueError("expecting remote branch(es) to contain HEAD, master, or trunk")




def get_current_head_branch():
    start = time.time()
    branches_str = from_sys_call("git branch --list").strip()
    print "GIITTTT get_crnt brnch: get branches str" + str(time.time() - start)
    start = time.time()
    branches_unpolished = branches_str.split("\n")
    print "GIITTTT get_crnt brnch: split branches str" + str(time.time() - start)
    for branch_unpolished in branches_unpolished:
        start = time.time()
        branch_raw = branch_unpolished.strip()
        print "GIITTTT get_crnt brnch: strip branch str" + str(time.time() - start)
        if branch_raw[0] == "*":
            start = time.time()
            m = re.compile("^\* \((detached from|HEAD detached at) ([a-z0-9]{5,})\)$").match(branch_raw)
            print "GIITTTT get_crnt brnch: first re compile" + str(time.time() - start)
            if m:
                return m.group(2)
            start = time.time()
            b = re.compile("^\* ([a-zA-Z0-9\-_]+)$").match(branch_raw)
            if b:
                print "GIITTTT get_crnt brnch: 2nd re compile" + str(time.time() - start)
                return b.group(1)
            raise ValueError("unhandled branch name: " + branch_raw[2:].strip())
    raise EnvironmentError("no current head branch is listed")




# use with restore_and_pop_last, with care
def backup_and_stash_first():
    start = time.time()
    sys_call("git reset HEAD .")
    print "GIITTTT back up and stash: sys_call git reset HEAD" + str(time.time() - start)
    start = time.time()
    resp = from_sys_call("git stash save --keep-index --include-untracked").strip()
    print "GIITTTT back up and stash: from_sys_call git stash save" + str(time.time() - start)
    if resp == "No local changes to save":
        return False
    else:
        return True




# use with backup_and_stash_first, with care
# should_further_recover is the return value of backup_and_stash_first
def restore_and_pop_last(head_branch, should_further_recover):
    time.time()
    sys_call("git checkout " + head_branch)
    print "GIITTTT restore and pop last: syscall git chekcout" + str(time.time() - start)
    if should_further_recover:
        time.time()
        sys_call("git stash pop", ignore_bad_exit=True)
        print "GIITTTT restore and pop last: syscall git stash pop" + str(time.time() - start)




def clear_temp_checkout(current_commit):
    time.time()
    sys_call("git reset --hard " + current_commit)
    print "GIITTTT clear temp checkout: git reset --hard" + str(time.time() - start)
    time.time()
    resp = from_sys_call("git stash save --keep-index --include-untracked").strip()
    print "GIITTTT clear temp checkout: syscall git stash save" + str(time.time() - start)
    if resp != "No local changes to save":
        sys_call("git stash drop")




def git_commit_msgs(from_commit, to_commit):
    gitlog = "git log --graph --abbrev-commit " + \
        "--format=format:'%h - (%ai) %s - %an%d' " + from_commit + ".." + to_commit
    return from_sys_call(gitlog)




http_regex = "^http(s?)://(www\.)?github.com/(.*)/(.*)\.git$"
git_regex = "^git@github.com:(.*)/(.*)\.git$"




# find the first key that matches github.com url
def get_remote_url_key():
    all_configs = from_sys_call("git config --list").strip().split("\n")
    matching_ln_regex = "^remote\.(.*)\.url=(.*)$"
    for c in all_configs:
        m = re.match(matching_ln_regex, c)
        if m and (re.match(http_regex, m.group(2)) or re.match(git_regex, m.group(2))):
            return m.group(1)
    return None




def github_info(prev_commit, post_commit):
    first_key = get_remote_url_key()
    if first_key is None:
        return None
    resp = from_sys_call("git config --get remote." + first_key + ".url").strip()
    m = re.match(http_regex, resp)
    if m:
        return m.group(0)[:-4] + "/compare/" + prev_commit + "..." + post_commit
    m = re.match(git_regex, resp)
    if m:
        return ("https://github.com/" + m.group(1) + "/" + m.group(2) +
                "/compare/" + prev_commit + "..." + post_commit)
    return None