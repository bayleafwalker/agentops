"""Closed review grammar and real boolean defect; no Work/execution activity."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).parents[1] / "qualification/estate_maintenance_oracle.py"
spec = importlib.util.spec_from_file_location("acceptance_oracle", PATH)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)

SOURCE = b'''import math
def maintenance_fact(limit):
    if not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit <= 0:
        raise ValueError("invalid")
    return limit
'''
TESTS = b'''import unittest
class MaintenanceFacts(unittest.TestCase):
    def test_original(self):
        self.assertTrue(True)
'''
ADDED = b'''    def test_boolean_limits(self):
        for value in (True, False):
            data = report()
            data["max_age_hours"] = value
            self.assertEqual(estate.maintenance_fact(probe(data), "infra")["status"], "unknown")
'''


class ProtectedReview(unittest.TestCase):
    def review(self, expression, test=TESTS + ADDED):
        candidate = SOURCE.replace(b"not isinstance(limit, (int, float))", expression.encode())
        return oracle.review(SOURCE, candidate, TESTS, test)

    def test_common_pure_boolean_exclusions_preserve_other_validation(self):
        for expression in (
            "type(limit) not in (int, float)",
            "isinstance(limit, bool) or not isinstance(limit, (int, float))",
            "not isinstance(limit, (int, float)) or type(limit) is bool",
            "not (isinstance(limit, (int, float)) and not isinstance(limit, bool))",
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.review(expression)["type_partitions"], 8)

    def test_actual_boolean_bug_and_value_dependent_or_effectful_predicates_refuse(self):
        for expression in (
            "not isinstance(limit, (int, float))",
            "False", "True", "limit == 1", "type(limit) is float",
            "__import__('os').system('forbidden') or type(limit) not in (int, float)",
            "getattr(limit, '__class__') not in (int, float)",
        ):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.review(expression)

    def test_source_scope_and_original_tests_cannot_be_changed(self):
        fixed = SOURCE.replace(b"not isinstance(limit, (int, float))", b"type(limit) not in (int, float)")
        for source, tests in (
            (fixed.replace(b"return limit", b"return 123"), TESTS + ADDED),
            (fixed.replace(b"limit <= 0", b"limit < 0"), TESTS + ADDED),
            (fixed + b"\nprint('unrelated')\n", TESTS + ADDED),
            (fixed, (TESTS + ADDED).replace(b"self.assertTrue(True)", b"pass")),
            (fixed, TESTS),
        ):
            with self.subTest(source=source, tests=tests), self.assertRaises(ValueError):
                oracle.review(SOURCE, source, TESTS, tests)

    def test_regressions_cannot_introduce_imports_hooks_or_global_mutation(self):
        for body in (
            "import os", "estate.maintenance_fact = lambda *args: None",
            "self.__class__", "open('/tmp/forbidden', 'w')",
            "__import__('os')", "global estate", "while True: pass",
        ):
            extra = ADDED + ("        " + body + "\n").encode()
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.review("type(limit) not in (int, float)", TESTS + extra)

    def test_normal_host_entry_point_refuses(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(PATH), "review"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "estate-acceptance-refused:oracle-refused")

    def test_declared_codec_cannot_hide_executable_source_or_test_statements(self):
        fixed = SOURCE.replace(b"not isinstance(limit, (int, float))", b"type(limit) not in (int, float)")
        prefix = b"# coding: raw_unicode_escape\n# \\u000aUNREVIEWED_EXECUTABLE_ASSIGNMENT = 1\n"
        for source, tests in ((prefix + fixed, TESTS + ADDED), (fixed, prefix + TESTS + ADDED)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                oracle.review(SOURCE, source, TESTS, tests)
        # Ordinary UTF8 decoding loses the statement; the actual decoder sees it.
        import ast
        self.assertNotEqual(ast.dump(ast.parse((prefix + fixed).decode("utf-8"))),
                            ast.dump(ast.parse(prefix + fixed)))

    def test_every_binding_form_and_free_name_or_attribute_alias_is_closed(self):
        for body in (
            'report = exec\n        report("hidden")',
            'for report in (exec,):\n            report("hidden")',
            '[report("hidden") for report in (exec,)]',
            'with self.subTest() as report:\n            report("hidden")',
            'data = exec', 'data = __builtins__', 'data = estate.HOSTS',
            'data = copy.deepcopy', 'data = self', 'probe = report',
        ):
            extra = ADDED + ("        " + body + "\n").encode()
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.review("type(limit) not in (int, float)", TESTS + extra)

    def test_nested_scope_and_match_bindings_are_outside_closed_grammar(self):
        for body in (
            'data = [value for value in (1, 2)]',
            'data = {value for value in (1, 2)}',
            'data = {value: value for value in (1, 2)}',
            'data = (value for value in (1, 2))',
            'match True:\n            case value:\n                pass',
        ):
            extra = ADDED + ("        " + body + "\n").encode()
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.review("type(limit) not in (int, float)", TESTS + extra)

    def test_each_added_method_must_assertion_fail_baseline(self):
        class Controlled(unittest.TestCase):
            def test_assertion(self):
                self.assertEqual(1, 2)

            def test_vacuous(self):
                self.assertEqual(1, 1)

            def test_subtests(self):
                for value in (1, 2):
                    with self.subTest(value=value):
                        self.assertEqual(value, 0)

        self.assertEqual(oracle.run_regression_methods(Controlled, ["test_subtests"], "baseline"), 2)
        with self.assertRaisesRegex(ValueError, "regression-baseline-not-failed"):
            oracle.run_regression_methods(Controlled, ["test_assertion", "test_vacuous"], "baseline")
        with self.assertRaisesRegex(ValueError, "regression-candidate-failed"):
            oracle.run_regression_methods(Controlled, ["test_assertion"], "candidate")


if __name__ == "__main__":
    unittest.main()
