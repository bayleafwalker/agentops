"""Every committed packet, and every generated one, against the packet schema.

The schema at ``templates/dispatch/hybrid/task-packet.schema.json`` is
``additionalProperties: false`` and carries a ``task_id`` pattern -- but there
is no ``jsonschema`` on the host, so ``hybrid_dispatch`` holds the invariants by
hand and nothing ever compared a packet against the schema file itself. It
drifted, exactly as an unchecked document does:

* the ``task_id`` pattern ``^[A-Z0-9]+-`` rejected ``v5.2-release-unit``, which
  is the id every release-unit packet has;
* ``gate_set`` and ``stop_conditions`` -- the two fields that make a
  release-unit packet a release-unit packet -- were undeclared, so a strict
  reading of the schema rejected them as additional properties.

Both were found by an oracle author reading the schema while writing L-5's
oracle, not by anything that runs. This file is the thing that runs: a small
checker for the subset of JSON Schema the file actually uses, pointed at every
packet in ``docs/evidence/packets/`` and at a freshly generated release unit.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCHEMA_PATH = ROOT / "templates/dispatch/hybrid/task-packet.schema.json"
PACKET_DIR = ROOT / "docs/evidence/packets"
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


release_unit = _load("release_unit_packet_subject", SCRIPTS / "release_unit_packet.py")

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def validate(instance, schema, path="$"):
    """Return a list of human-readable violations.

    Covers only the constructs this schema actually uses: type, required,
    properties, additionalProperties, items, enum, const, pattern, minLength,
    minimum and uniqueItems. Anything else in the schema is ignored rather than
    silently passed off as checked -- a checker that quietly skips a keyword is
    worse than no checker, so keep this list honest as the schema grows.
    """
    errors = []
    expected = schema.get("type")
    if expected:
        wanted = _TYPES[expected]
        # bool is an int in Python; the schema means them separately.
        if expected == "integer" and isinstance(instance, bool):
            errors.append(f"{path}: expected integer, got boolean")
            return errors
        if not isinstance(instance, wanted):
            errors.append(
                f"{path}: expected {expected}, got {type(instance).__name__}")
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, instance):
            errors.append(f"{path}: {instance!r} does not match {pattern}")
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            errors.append(f"{path}: shorter than minLength {min_length}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: {instance} below minimum {minimum}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key!r} is not allowed")
    if isinstance(instance, list):
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                errors.extend(validate(item, item_schema, f"{path}[{index}]"))
        if schema.get("uniqueItems"):
            hashable = [json.dumps(i, sort_keys=True) for i in instance]
            if len(set(hashable)) != len(hashable):
                errors.append(f"{path}: items are not unique")
    return errors


SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

#: A release unit built the way an orchestrator builds one. This is the packet
#: whose id and two extra fields the schema used to reject outright.
RELEASE_UNIT = release_unit.release_unit_packet(
    "v5.2",
    "agentops",
    {"ref": "agentops#2254", "claim_id": 1, "claim_actor": "workstation-vuoro"},
    ["templates/dispatch/scripts/**"],
    "vuoro-shared as a migration exercise",
)


class CommittedPacketsTests(unittest.TestCase):
    """Every packet the repo carries must satisfy the schema it declares."""

    def test_there_are_packets_to_check(self):
        # Guards against the whole suite passing vacuously if the directory
        # moves or the glob stops matching.
        self.assertGreater(len(list(PACKET_DIR.glob("*.json"))), 5)

    def test_every_committed_packet_validates(self):
        for packet_path in sorted(PACKET_DIR.glob("*.json")):
            with self.subTest(packet=packet_path.name):
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    validate(packet, SCHEMA), [],
                    f"{packet_path.name} does not satisfy task-packet.schema.json")


class ReleaseUnitPacketTests(unittest.TestCase):
    """The packet shape that exposed the drift."""

    def test_a_generated_release_unit_validates(self):
        self.assertEqual(
            validate(RELEASE_UNIT, SCHEMA), [],
            "a generated release-unit packet does not satisfy the schema; this is "
            "the drift L-5 found -- task_id pattern and the two undeclared fields")

    def test_the_release_unit_task_id_is_admitted(self):
        pattern = SCHEMA["properties"]["task_id"]["pattern"]
        self.assertRegex(RELEASE_UNIT["task_id"], pattern)
        self.assertEqual(RELEASE_UNIT["task_id"], "v5.2-release-unit")

    def test_gate_set_and_stop_conditions_are_declared(self):
        for field in ("gate_set", "stop_conditions"):
            self.assertIn(
                field, SCHEMA["properties"],
                f"{field} is undeclared, so additionalProperties:false rejects it")


class TaskIdPatternTests(unittest.TestCase):
    """The pattern must admit real ids and still refuse unsafe ones.

    A task id becomes a git branch component and a directory name under
    docs/evidence/receipts/, so the refusals matter as much as the admissions.
    """

    def setUp(self):
        self.pattern = SCHEMA["properties"]["task_id"]["pattern"]

    def test_it_admits_the_ids_actually_in_use(self):
        for task_id in ("V5-T10-money-names", "V5-P1a-cost-hook-fields",
                        "v5.2-release-unit", "v5.9-release-unit"):
            with self.subTest(task_id=task_id):
                self.assertRegex(task_id, self.pattern)

    def test_it_refuses_ids_that_are_unsafe_as_a_path_segment(self):
        for task_id in ("has space", "a/b", "../escape", "-leading",
                        ".leading", "nohyphen", ""):
            with self.subTest(task_id=task_id):
                self.assertNotRegex(task_id, self.pattern)


class CheckerDiscriminationTests(unittest.TestCase):
    """A checker that passes everything would make this file decoration."""

    def _mutated(self, **changes):
        packet = json.loads(json.dumps(RELEASE_UNIT))
        packet.update(changes)
        return packet

    def test_an_unknown_top_level_key_is_rejected(self):
        self.assertTrue(validate(self._mutated(surprise="hello"), SCHEMA))

    def test_a_bad_task_id_is_rejected(self):
        self.assertTrue(validate(self._mutated(task_id="not a valid id"), SCHEMA))

    def test_a_missing_required_key_is_rejected(self):
        packet = json.loads(json.dumps(RELEASE_UNIT))
        del packet["purpose"]
        self.assertTrue(validate(packet, SCHEMA))

    def test_a_wrong_type_is_rejected(self):
        self.assertTrue(validate(self._mutated(writable_patch_paths="not a list"), SCHEMA))

    def test_a_bad_enum_value_is_rejected(self):
        self.assertTrue(validate(self._mutated(network_policy="enabled"), SCHEMA))

    def test_a_malformed_gate_set_entry_is_rejected(self):
        self.assertTrue(validate(
            self._mutated(gate_set=[{"order": 1}]), SCHEMA), "gate is required")
        self.assertTrue(validate(
            self._mutated(gate_set=[{"order": "first", "gate": "x"}]), SCHEMA),
            "order must be an integer")
        self.assertTrue(validate(
            self._mutated(gate_set=[{"order": 1, "gate": "x", "extra": 1}]), SCHEMA),
            "gate_set entries take no additional properties")

    def test_a_boolean_is_not_an_integer(self):
        self.assertTrue(validate(
            self._mutated(gate_set=[{"order": True, "gate": "x"}]), SCHEMA))


if __name__ == "__main__":
    unittest.main()
