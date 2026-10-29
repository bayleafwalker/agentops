"""Trusted offline verifier: inspect exact committed data without importing it."""
import argparse
import ast
import hashlib
import os
import stat
import sys


def read_regular(dir_fd, name, expected_sha256):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("candidate file is not regular")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError("candidate bytes differ from Git blob")
        return data.decode("utf-8")
    finally:
        os.close(fd)


def main(candidate, delivery_hash, test_hash):
    directory = os.open(candidate, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        delivery = read_regular(directory, "delivery.py", delivery_hash)
        tests = read_regular(directory, "test_delivery.py", test_hash)
    finally:
        os.close(directory)
    program = ast.parse(delivery)
    assert len(program.body) == 1
    assignment = program.body[0]
    assert isinstance(assignment, ast.Assign) and len(assignment.targets) == 1
    assert isinstance(assignment.targets[0], ast.Name) and assignment.targets[0].id == "VALUE"
    assert isinstance(assignment.value, ast.Constant) and assignment.value.value == "delivered"
    assert tests == (
        'import unittest\nfrom delivery import VALUE\nclass DeliveryTest(unittest.TestCase):\n'
        "    def test_value(self): self.assertEqual(VALUE, 'delivered')\n")
    print("trusted fixture verified candidate contents")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate")
    parser.add_argument("delivery_hash")
    parser.add_argument("test_hash")
    arguments = parser.parse_args()
    main(arguments.candidate, arguments.delivery_hash, arguments.test_hash)
