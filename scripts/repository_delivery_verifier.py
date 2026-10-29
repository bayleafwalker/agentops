"""Trusted offline verifier: inspect candidate data without importing its code."""
import ast
from pathlib import Path
import sys


def main(candidate):
    root = Path(candidate)
    program = ast.parse((root / "delivery.py").read_text())
    assert len(program.body) == 1
    assignment = program.body[0]
    assert isinstance(assignment, ast.Assign) and len(assignment.targets) == 1
    assert isinstance(assignment.targets[0], ast.Name) and assignment.targets[0].id == "VALUE"
    assert isinstance(assignment.value, ast.Constant) and assignment.value.value == "delivered"
    assert (root / "test_delivery.py").read_text() == (
        'import unittest\nfrom delivery import VALUE\nclass DeliveryTest(unittest.TestCase):\n'
        "    def test_value(self): self.assertEqual(VALUE, 'delivered')\n")
    print("trusted fixture verified candidate contents")


if __name__ == "__main__":
    main(sys.argv[1])
