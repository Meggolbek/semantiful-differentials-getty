class MethodCallHandler(object):
    def __init__(self):
        self.seen = set()

    def find_sub_calls(self, caller, method_calls):
        """

        :param caller:
        :param callee:
        :param method_calls: Dictionary of method name to set of called sub_methods. Ex) c: (m1, m2, m3)
        :return:
        """
        # if part of graph is seen just return, no need to recompute
        if caller in self.seen:
            return method_calls
        else:
            # if not seen we need to add caller to seen set
            self.seen.add(caller)

        # check if caller has callees
        does_not_have_callees = True
        caller = caller + "("
        print "caller: ", caller
        for m in method_calls.keys():
            print "m: ", m[:len(caller)]
            if m[:len(caller)] == caller:
                caller = m
                does_not_have_callees = False
        # if caller does not have callees just return
        if does_not_have_callees:
            print "jere"
            return method_calls
        print "method calls [caller]: ", method_calls[caller]
        for sub_method in method_calls[caller]:
            # call find_sub_calls on callee
            recursive_result = self.find_sub_calls(sub_method, method_calls)

            # if the sub_method has callees then union the callees of caller and callees of callees
            if sub_method in recursive_result.keys():
                method_calls[caller] = method_calls[caller].union(recursive_result[sub_method])
        return method_calls

    def flip_method_calls(self, method_calls):
        result = {}
        for caller in method_calls.keys():
            for callee in method_calls[caller]:
                if callee in result.keys():
                    result[callee].add(caller)
                else:
                    result[callee] = set({caller})
        return result

    def extract_tests(self, test_suites, method_calls_callee_to_caller):
        # junit_torun is one string, split by space to get each test suite name
        methods_to_tests = {}
        for callee in method_calls_callee_to_caller.keys():
            # get package name from caller, package name is m.split(":")[0]
            methods_to_tests[callee] = {m for m in method_calls_callee_to_caller[callee] if
                                        m.split(":")[0] in test_suites}
        return methods_to_tests

