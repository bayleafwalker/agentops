#!/usr/bin/env python3
"""Protected semantic oracles for Work2873; execute candidates only in its VM.

The baseline and VM/interpreter are installed trusted inputs. This file neither
accepts Work nor qualifies a host. The production entry point refuses a normal
host; direct functions exist for controlled source qualification only.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import socket
import sys
import unittest

BASE = "dcb137a42c5bd135415515c8d750ec8c5b1b1660"
SOURCE = "scripts/estate_status.py"
TEST = "scripts/tests/test_estate_maintenance.py"
OBSERVED = "2026-10-31T12:00:10Z"
CHECKED = "2026-10-31T12:00:00Z"
FAILURE_CODES = frozenset({
    "source-size", "type-predicate", "regression-signature", "regression-executable-scope",
    "nested-regression", "regression-private-access", "regression-call-scope",
    "regression-mutation-scope", "baseline-guard", "candidate-guard", "boolean-type-partition",
    "unrelated-source-change", "test-class", "regression-required", "duplicate-regression",
    "original-tests-changed", "boolean-regression-required", "invalid-limit-accepted",
    "valid-limit-refused", "incident-lost", "invalid-report-accepted", "baseline-regression-failed",
    "guest-private-boundary", "guest-device-boundary", "guest-network-boundary",
    "regression-candidate-failed", "regression-baseline-not-failed", "oracle-refused",
    "regression-name-scope", "regression-attribute-scope", "regression-binding-scope",
})


def need(value, code):
    if not value:
        raise ValueError(code)


def tree(raw):
    need(isinstance(raw, bytes) and len(raw) <= 2 * 1024 * 1024, "source-size")
    # Use the same PEP263 decoder as Python's source loader. Decoding as UTF8
    # first would let another declared codec hide executable text in comments.
    return ast.parse(raw)


def same(left, right):
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def invalid_type(node, value):
    """Interpret a closed type predicate, never eval candidate expressions.

    Predicates may inspect only the JSON value's type. Consequently one value
    per JSON type is a complete partition, rather than sampled numeric behavior.
    """
    types = {"int": int, "float": float, "bool": bool, "str": str,
             "dict": dict, "list": list, "NoneType": type(None)}
    if isinstance(node, ast.Name) and node.id in types:
        return types[node.id]
    if isinstance(node, ast.Tuple):
        return tuple(invalid_type(item, value) for item in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not invalid_type(node.operand, value)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        operands = [invalid_type(item, value) for item in node.values]
        need(all(type(item) is bool for item in operands), "type-predicate")
        return all(operands) if isinstance(node.op, ast.And) else any(operands)
    if isinstance(node, ast.Call) and not node.keywords and isinstance(node.func, ast.Name):
        if (node.func.id == "type" and len(node.args) == 1
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "limit"):
            return type(value)
        if (node.func.id == "isinstance" and len(node.args) == 2
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "limit"):
            kinds = invalid_type(node.args[1], value)
            need(isinstance(kinds, (type, tuple)), "type-predicate")
            return isinstance(value, kinds)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left, right = invalid_type(node.left, value), invalid_type(node.comparators[0], value)
        need(isinstance(left, type) and (isinstance(right, type) or isinstance(right, tuple)), "type-predicate")
        op = node.ops[0]
        if isinstance(op, ast.In): return left in right
        if isinstance(op, ast.NotIn): return left not in right
        if isinstance(op, (ast.Is, ast.Eq)): return left is right
        if isinstance(op, (ast.IsNot, ast.NotEq)): return left is not right
    raise ValueError("type-predicate")


def regression(node):
    """New tests cannot add imports, hooks, external calls or global mutation."""
    need(len(node.args.args) == 1 and node.args.args[0].arg == "self"
         and node.args.args[0].annotation is None and node.returns is None
         and not node.args.defaults and not node.args.kwonlyargs
         and not node.args.posonlyargs and not getattr(node, "type_params", [])
         and node.args.vararg is None and node.args.kwarg is None, "regression-signature")
    forbidden = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.Delete,
                 ast.Lambda, ast.ClassDef, ast.AsyncFunctionDef, ast.Await,
                 ast.Yield, ast.YieldFrom, ast.While, ast.Raise, ast.Try,
                 ast.AugAssign, ast.NamedExpr, ast.Match, ast.ListComp,
                 ast.SetComp, ast.DictComp, ast.GeneratorExp)
    calls = {"report", "probe", "float", "int", "str", "len", "copy.deepcopy",
             "estate.maintenance_fact", "estate.maintenance_check", "self.subTest",
             "self.assertEqual", "self.assertTrue", "self.assertFalse",
             "self.assertIn", "self.assertNotIn", "self.assertIs"}
    reserved = {"self", "estate", "copy", "NOW", "math", *(name for name in calls if "." not in name)}
    nodes = list(ast.walk(node))
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    # All admitted bindings share the method scope. Comprehensions and match
    # captures are excluded rather than conflated with method-local names.
    # Callable/module roots are immutable; arbitrary objects cannot enter data.
    bound = {item.id for item in nodes if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)}
    need(not bound & reserved and all(not name.startswith("_") for name in bound), "regression-binding-scope")
    for item in nodes:
        need(not isinstance(item, forbidden), "regression-executable-scope")
        if isinstance(item, ast.FunctionDef): need(item is node, "nested-regression")
        if isinstance(item, ast.Attribute):
            parent = parents[item]
            need(isinstance(parent, ast.Call) and parent.func is item
                 and ast.unparse(item) in calls, "regression-attribute-scope")
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load):
            parent = parents[item]
            call_root = (isinstance(parent, ast.Call) and parent.func is item
                         or isinstance(parent, ast.Attribute) and isinstance(parents[parent], ast.Call)
                         and parents[parent].func is parent)
            need(call_root or item.id in bound | {"NOW"}, "regression-name-scope")
        if isinstance(item, ast.Call): need(ast.unparse(item.func) in calls, "regression-call-scope")
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            for target in targets:
                while isinstance(target, ast.Subscript): target = target.value
                need(isinstance(target, ast.Name) and target.id not in {"self", "estate", "copy"}, "regression-mutation-scope")


def review_source(baseline_source, candidate_source):
    original, selected = tree(baseline_source), tree(candidate_source)
    expected = ast.parse("not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit <= 0", mode="eval").body
    old = [node for node in ast.walk(original) if isinstance(node, ast.If) and same(node.test, expected)]
    need(len(old) == 1, "baseline-guard")
    # Keep every statement, name, finite/positive guard and branch unchanged.
    # Only a side-effect-free type predicate can differ.
    candidates = [node for node in ast.walk(selected) if isinstance(node, ast.If)
                  and isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.Or)
                  and len(node.test.values) >= 3
                  and all(same(a, b) for a, b in zip(node.test.values[-2:], expected.values[-2:]))]
    need(len(candidates) == 1, "candidate-guard")
    guard = candidates[0]
    first = guard.test.values[:-2]
    predicate = first[0] if len(first) == 1 else ast.BoolOp(op=ast.Or(), values=first)
    for value in (True, False, 1, .5, None, "1", {}, []):
        result = invalid_type(predicate, value)
        need(type(result) is bool and result == (type(value) not in (int, float)), "boolean-type-partition")
    guard.test = copy.deepcopy(expected)
    need(same(original, selected), "unrelated-source-change")
    return {"type_partitions": 8}


def review(baseline_source, candidate_source, baseline_test, candidate_test):
    result = review_source(baseline_source, candidate_source)
    old_tests, new_tests = tree(baseline_test), tree(candidate_test)
    classes = [node for node in new_tests.body if isinstance(node, ast.ClassDef) and node.name == "MaintenanceFacts"]
    old_classes = [node for node in old_tests.body if isinstance(node, ast.ClassDef) and node.name == "MaintenanceFacts"]
    need(len(classes) == len(old_classes) == 1, "test-class")
    names = {node.name for node in old_classes[0].body if isinstance(node, ast.FunctionDef)}
    additions = [node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name not in names]
    need(1 <= len(additions) <= 20 and all(node.name.startswith("test_") and not node.decorator_list for node in additions), "regression-required")
    need(len({node.name for node in additions}) == len(additions), "duplicate-regression")
    for node in additions: regression(node)
    for node in additions: classes[0].body.remove(node)
    need(same(old_tests, new_tests), "original-tests-changed")
    text = "\n".join(ast.unparse(node) for node in additions)
    need(all(term in text for term in ("max_age_hours", "True", "False", "unknown")), "boolean-regression-required")
    return {**result, "added_regressions": len(additions)}


def report(limit=36):
    return {"schema_version": "maintenance-health/v1", "host": "infra", "checked_at": CHECKED,
        "status": "healthy", "probe_error": None, "jobs": {"talos-etcd-backup.service": {
            "status": "healthy", "problems": [], "last_success_at": "2026-10-31T11:59:50Z",
            "last_success_age_seconds": 10, "max_age_hours": limit, "last_attempt": {"result": "success"}}}}


def check(root, baseline):
    # Candidate code shares the behavioral interpreter. Admit only the exact
    # pure type-guard change before importing it, so it cannot replace the
    # harness, alter its output, or introduce executable initialization.
    review_source((baseline/SOURCE).read_bytes(), (root/SOURCE).read_bytes())
    spec = importlib.util.spec_from_file_location("protected_estate_subject", root / SOURCE)
    subject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subject)
    def fact(value):
        return subject.maintenance_fact({"ok": True, "stdout": json.dumps(value),
            "observed_at": OBSERVED, "evidence": "public-synthetic-work2873"}, "infra")
    cases = 0
    for limit in (True, False, 0, -1, "1", None, math.inf, -math.inf, math.nan):
        need(fact(report(limit))["status"] == "unknown", "invalid-limit-accepted")
        cases += 1
    for limit in (1, 36, 36.0, .5):
        result = fact(report(limit))
        need(result["status"] == "known" and subject.maintenance_check(result)[0] is True, "valid-limit-refused")
        cases += 1
    incident = report(); incident["status"] = "degraded"
    incident["jobs"]["talos-etcd-backup.service"].update(status="degraded", problems=["last-run-failed"])
    result = fact(incident)
    need(result["status"] == "known" and subject.maintenance_check(result)[0] is False, "incident-lost")
    for field, value in (("checked_at", "2026-10-31T10:00:00Z"), ("host", "foreign"), ("jobs", {})):
        invalid = report(); invalid[field] = value
        need(fact(invalid)["status"] == "unknown", "invalid-report-accepted")
    # The VM stages the original baseline tests here, not candidate test bodies.
    suite = unittest.TestLoader().discover(str(root / "scripts/tests"), pattern="test_estate*.py")
    with open(os.devnull, "w") as sink:
        result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
    need(result.testsRun >= 50 and result.wasSuccessful() and not result.skipped, "baseline-regression-failed")
    return {"cases": cases + 4, "baseline_tests": result.testsRun}


def guest_boundary():
    # Every positive control contains synthetic data created by the trusted
    # supervisor. Missing files do not count as denied access.
    for name, flags in (("/run/acceptance-parent-private", os.O_RDONLY),
                        ("/proc/1/environ", os.O_RDONLY),
                        ("/proc/1/fd/1", os.O_WRONLY | os.O_NONBLOCK),
                        ("/dev/console", os.O_WRONLY | os.O_NONBLOCK),
                        ("/dev/ttyS0", os.O_WRONLY | os.O_NONBLOCK)):
        try: descriptor = os.open(name, flags)
        except PermissionError: continue
        else:
            os.close(descriptor)
            raise ValueError("guest-private-boundary")
    need(set(os.listdir("/sys/class/net")) == {"lo"} and not os.listdir("/sys/block"), "guest-device-boundary")
    with socket.socket() as connection:
        connection.settimeout(.2)
        try: connection.connect(("198.51.100.1", 5432))
        except OSError as error:
            need(error.errno in {101, 113}, "guest-network-boundary")
        else: raise ValueError("guest-network-boundary")


def run_regression_methods(test_class, names, kind):
    code = "regression-candidate-failed" if kind == "candidate" else "regression-baseline-not-failed"
    failures = 0
    # Evaluate the differential contract per method. A failing subtest in one
    # method must not mask a different method that also passes the baseline.
    for name in names:
        with open(os.devnull, "w") as sink:
            result = unittest.TextTestRunner(stream=sink, verbosity=0).run(
                unittest.TestSuite([test_class(name)]))
        need(result.testsRun == 1 and not result.errors and not result.skipped, code)
        need(result.wasSuccessful() if kind == "candidate" else bool(result.failures), code)
        failures += len(result.failures)
    return failures


def review_regressions(baseline_test, candidate_test):
    old_class = next(node for node in tree(baseline_test).body if isinstance(node, ast.ClassDef) and node.name == "MaintenanceFacts")
    new_class = next(node for node in tree(candidate_test).body if isinstance(node, ast.ClassDef) and node.name == "MaintenanceFacts")
    old_names = {node.name for node in old_class.body if isinstance(node, ast.FunctionDef)}
    names = [node.name for node in new_class.body if isinstance(node, ast.FunctionDef) and node.name not in old_names]
    failures = 0
    for kind in ("candidate", "baseline"):
        path = Path("/work/regression-" + kind) / TEST
        spec = importlib.util.spec_from_file_location("protected_regression_" + kind, path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        count = run_regression_methods(module.MaintenanceFacts, names, kind)
        if kind == "baseline": failures = count
    return {"regression_tests": len(names), "baseline_failures": failures}


def main():
    need(len(sys.argv) == 2 and sys.argv[1] in {"check", "review"}, "fixed-mode")
    sentinel = Path("/run/agentops-acceptance-guest.json")
    info = sentinel.lstat()
    need(os.geteuid() == 1000 and stat.S_ISREG(info.st_mode) and info.st_uid == 0
         and stat.S_IMODE(info.st_mode) == 0o444, "isolated-guest-required")
    config = json.loads(sentinel.read_bytes())
    need(config == {"schema_version": "agentops-estate-acceptance-guest/v1", "base": BASE}, "guest-basis")
    guest_boundary()
    root, baseline = Path("/work/repository"), Path("/baseline")
    if sys.argv[1] == "check": result = check(root, baseline)
    else:
        old_test, new_test = (baseline/TEST).read_bytes(), Path("/input/candidate-test.py").read_bytes()
        result = review((baseline/SOURCE).read_bytes(), (root/SOURCE).read_bytes(), old_test, new_test)
        result.update(review_regressions(old_test, new_test))
    print(json.dumps({"schema_version": "agentops-estate-acceptance-oracle/v1",
        "mode": sys.argv[1], "complete": True, "boundary_probed": True, **result}, sort_keys=True))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) and str(error) in FAILURE_CODES else "oracle-refused"
        print("estate-acceptance-refused:" + code, file=sys.stderr)
        raise SystemExit(1) from None
