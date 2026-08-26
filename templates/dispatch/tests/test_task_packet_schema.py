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
oracle, not by anything that runs. This file is the thing that runs, pointed at every packet in
``docs/evidence/packets/`` and at a freshly generated release unit.

The checker itself now lives in ``scripts/packet_schema.py``. It was defined
here, which meant the dispatch path never used it: ``hybrid_dispatch.py``
reported ``packet-schema-valid`` among its satisfied pre-gates and compared the
packet with nothing, and V6-K was dispatched twice with ``debt`` as a string.
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

packet_schema = _load("packet_schema_subject", SCRIPTS / "packet_schema.py")

#: One checker, two callers. It used to be defined here, which is why the
#: dispatch path could report ``packet-schema-valid`` while comparing the packet
#: against nothing.
validate = packet_schema.validate

SCHEMA = packet_schema.load_schema(SCHEMA_PATH)

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


class CheckerCoverageTests(unittest.TestCase):
    """The checker must refuse to be quietly incomplete.

    Before this guard existed the checker ignored nine keyword sites in the
    committed schema -- ``minItems`` five times, ``maximum`` three times, and
    the root ``allOf``. That last one carries the whole v1/v2/v3 discrimination,
    including v3's ``required: [action_class]`` and the two acceptance-property
    shapes behind ``$ref``. All of it was declared in the schema and enforced by
    nothing that reads the schema, and every packet was reported valid against
    constraints that were never applied.
    """

    def test_the_committed_schema_uses_no_unimplemented_keyword(self):
        self.assertEqual([], packet_schema.unsupported_keywords(SCHEMA))

    def test_an_unimplemented_keyword_is_refused_rather_than_ignored(self):
        with self.assertRaises(packet_schema.SchemaCoverageError):
            packet_schema.check_schema_is_supported(
                {"type": "object", "properties": {"x": {"multipleOf": 3}}})

    def test_the_version_conditionals_are_actually_applied(self):
        """v3 requires action_class; the root allOf is the only place it says so."""
        packet = json.loads(json.dumps(RELEASE_UNIT))
        packet["schema_version"] = "agentops-task/v3"
        packet.pop("action_class", None)
        errors = validate(packet, SCHEMA)
        self.assertTrue(
            any("action_class" in e for e in errors),
            f"v3 without action_class must fail; got {errors}")

    def test_a_v1_packet_may_not_carry_a_v2_acceptance_id(self):
        packet = json.loads(json.dumps(RELEASE_UNIT))
        packet["schema_version"] = "agentops-task/v1"
        packet["acceptance_properties"] = [{
            "id": "a-v2-only-id",
            "command_id": packet["allowed_command_ids"][0],
            "requirement": "r",
            "fails_when": "f",
        }]
        self.assertTrue(validate(packet, SCHEMA),
                        "the v1 branch of the root allOf was not applied")

    def test_min_items_is_enforced(self):
        packet = json.loads(json.dumps(RELEASE_UNIT))
        packet["writable_patch_paths"] = []
        self.assertTrue(validate(packet, SCHEMA))

    def test_maximum_is_enforced(self):
        packet = json.loads(json.dumps(RELEASE_UNIT))
        packet["context_churn"]["max_repeated_reads_per_path"] = 10**6
        self.assertTrue(validate(packet, SCHEMA))


if __name__ == "__main__":
    unittest.main()
