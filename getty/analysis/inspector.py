# CSI inspection page section


from analysis.solver import is_different
from tools.daikon import fsformat


def getty_csi_init(html_file):
    html_string = ""
    with open(html_file, 'r') as rf:
        html_string = rf.read()
    html_string = html_string.replace(
        "<a href='#' id='getty-advice-title' onclick='return false;'>{{{__getty_advice__}}}</a>",
        "{{{__getty_continuous_semantic_inspection__}}}" + \
        "<div id='csi-output-targets'></div>\n" + \
        "<div id='csi-output-neighbors' " + \
        "style='border:4px double gray; padding: 4px 4px 4px 4px; margin: 8px 0 0 0;'>" + \
        "Choose a target to show its affected neighbors</div>\n" + \
        "<div id='csi-output-invcomp' " + \
        "style='border:4px double gray; padding: 4px 4px 4px 4px; margin: 8px 0 0 0;'>" + \
        "Choose a neighbor target to show its invariant change</div>")
    with open(html_file, 'w') as wf:
        wf.write(html_string)


def __set_all_with_tests(new_all, map_of_map):
    for mtd in map_of_map:
        new_all.add(mtd)
        for m in map_of_map[mtd]:
            new_all.add(m)


def __link_to_show_neighbors(t):
    aid = "target-link-" + fsformat(t)
    cls = "target-linkstyle"
    js_cmd = "return activateNeighbors(\"" + t + "\");"
    return "<a href='#' id='" + aid + "' class='" + cls + "' onclick='" + js_cmd + "'>" + t + "</a>"


def __append_script_l2s(html_string, lst, for_whom):
    the_script = \
        for_whom + " = list_to_set([" + \
        ", ".join(["\"" + t + "\"" for t in lst]) + \
        "]);"
    place_holder = "</script>\n</body>"
    to_replace = "    " + the_script + "\n" + place_holder
    return html_string.replace(place_holder, to_replace)


def __append_script_mm2d(html_string, mm, for_whom):
    serialized = []
    for mtd in mm:
        serialized.append("\"" + mtd + "\"")
        value_entry = []
        for m in mm[mtd]:
            value_entry.append(m)
            value_entry.append(str(mm[mtd][m]))
        serialized.append(str(value_entry))
    the_script = \
        for_whom + " = list_list_to_dict_dict([" + \
        ", ".join(serialized) + "]);"
    place_holder = "</script>\n</body>"
    to_replace = "    " + the_script + "\n" + place_holder
    return html_string.replace(place_holder, to_replace)


def _getty_csi_setvars(html_string, go, prev_hash, post_hash, \
                       all_changed_tests, old_changed_tests, new_changed_tests, \
                       new_modified_src, new_all_src, \
                       new_caller_of, new_callee_of, new_pred_of, new_succ_of):
    html_string = __append_script_l2s(html_string, all_changed_tests, "all_changed_tests")
    html_string = __append_script_l2s(html_string, old_changed_tests, "old_changed_tests")
    html_string = __append_script_l2s(html_string, new_changed_tests, "new_changed_tests")
    
    new_all = set()
    __set_all_with_tests(new_all, new_caller_of)
    __set_all_with_tests(new_all, new_callee_of)
    __set_all_with_tests(new_all, new_pred_of)
    __set_all_with_tests(new_all, new_succ_of)
    html_string = __append_script_l2s(html_string, new_all, "all_project_methods")
    
    html_string = __append_script_l2s(html_string, new_modified_src, "all_modified_targets")

    new_all_test_and_else = new_all - set(new_all_src)
    html_string = __append_script_l2s(html_string, new_all_test_and_else, "all_test_and_else")
    
    all_whose_inv_changed = set()
    for mtd in new_all_src:
        if is_different(mtd, go, prev_hash, post_hash):
            all_whose_inv_changed.add(mtd);
    html_string = __append_script_l2s(html_string, all_whose_inv_changed, "all_whose_inv_changed")
    
#     # DEBUG ONLY
#     print new_caller_of
#     print new_callee_of
#     print new_pred_of
#     print new_succ_of
    
    html_string = __append_script_mm2d(html_string, new_caller_of, "post_affected_caller_of")
    html_string = __append_script_mm2d(html_string, new_callee_of, "post_affected_callee_of")
    html_string = __append_script_mm2d(html_string, new_pred_of, "post_affected_pred_of")
    html_string = __append_script_mm2d(html_string, new_succ_of, "post_affected_succ_of")
    
    return html_string
    

def getty_csi_targets_prep(html_file, go, prev_hash, post_hash, \
                           all_changed_tests, old_changed_tests, new_changed_tests, \
                           new_modified_src, new_all_src, \
                           new_caller_of, new_callee_of, new_pred_of, new_succ_of):
    html_string = ""
    with open(html_file, 'r') as rf:
        html_string = rf.read()
    targets_place_holder = "<div id='csi-output-targets'></div>"
    replace_header = \
        "<div id='csi-output-targets' " + \
        "style='border:4px ridge gray; padding: 4px 4px 4px 4px; margin: 8px 0 0 0;'>" + \
        "<h4 style='margin: 4px 0 8px 0'>Updated Method Targets:</h4>"
    replace_footer = "</div>"
    if new_modified_src:
        replacement = " ,  ".join([__link_to_show_neighbors(t) for t in new_modified_src])
    else:
        replacement = "<span>None</span>"
    embed_test_update = \
        "<br><br><h4 style='margin: 4px 0 8px 0'>Updated Tests:</h4>"
    if all_changed_tests:
        tests_replacement = " ,  ".join([__link_to_show_neighbors(t) for t in all_changed_tests])
    else:
        tests_replacement = "<span>None</span>"
    html_string = html_string.replace(targets_place_holder, \
                                      replace_header + replacement + \
                                      embed_test_update + tests_replacement + replace_footer)

    html_string = _getty_csi_setvars(html_string, go, prev_hash, post_hash, \
                                     all_changed_tests, old_changed_tests, new_changed_tests, \
                                     new_modified_src, new_all_src, \
                                     new_caller_of, new_callee_of, new_pred_of, new_succ_of)
    
    with open(html_file, 'w') as wf:
        wf.write(html_string)