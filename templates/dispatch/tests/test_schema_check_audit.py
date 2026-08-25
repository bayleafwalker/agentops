"""Oracle for the ``audit_schema`` row of ``templates/dispatch/scripts/schema_check.py``.

The module's governing rule is not in question here and does not move: a
construct the checker cannot enforce raises ``UnsupportedKeyword`` rather than
passing, because a constraint the checker ignores is a constraint that does not
exist and a clean result would be a lie. ``validate`` keeps raising, on the
first unenforceable construct, exactly as it does today.

What this row fixes is that the eager audit raises on the *first* unhandled
construct and tells the caller nothing about where it is or what else is wrong.
That was found the hard way: ``manifest.schema.json`` carried the (then
unenforceable) subschema form of ``additionalProperties`` in three separate
nodes -- ``routing.properties.action_classes``,
``hybrid.properties.commands``, and
``instruction_set.properties.skill_lock.oneOf[0]``, the last only reachable
through a ``oneOf`` -- and finding all three took repeated raise-and-fix
cycles, because each run named one and stopped. For a gate, raising is right.
For a human fixing a schema, one anonymous exception per run is close to
useless.

So the module grows one name::

    def audit_schema(schema, path="$") -> list[str]

It reports *every* construct the checker cannot enforce, one entry each, and
raises nothing. Each entry carries the breadcrumb of the offending node
(``$.properties.routing.properties.action_classes``) and names the offending
keyword. An empty list means the whole schema is enforceable.

The sharpest claim in this file is the agreement between the two::

    audit_schema(s) == []   if and only if   validate(instance, s) does not raise

pinned in *both* directions over a table of schemas -- clean ones, ones with a
single defect, ones with several, and the two real schema files in the repo.
An implementation where one drifts from the other reintroduces exactly the
silence this module exists to prevent, in a new place. How the two share code
is deliberately not pinned: an implementer may build one on the other or not.

Conventions follow the two sibling oracles (``test_schema_check.py`` and
``test_schema_check_composition.py``, both of which must keep passing): the
subject is loaded with importlib, and nothing is asserted about message
*wording* -- only breadcrumbs and offending keyword names, via ``assertIn``.

Three deliberate choices, stated so the next reader does not have to guess:

1. **No ordering is pinned.** Entry order is not asserted anywhere; every
   assertion is membership or count. There is no defensible order for a walk
   over an unordered document, and pinning one would forbid an implementation
   that walks breadth-first or collects defects out of a queue.

2. **Breadcrumbs use the grammar the module's own raise messages already
   use** -- ``$.properties.a``, ``$.items``, ``$.$defs.orphan``,
   ``$.allOf[0]``, ``$.not``, ``$.propertyNames``,
   ``$.additionalProperties``. That grammar is already load-bearing in the
   exception text this row leaves alone, so the audit reusing it is the only
   reading that keeps the two surfaces legible together. The one place it is
   *not* pinned is a node reached through ``$ref``, where the module has two
   equally honest breadcrumbs for one node; there this file asserts only that
   the definition's name appears.

3. **A bare boolean in schema position has no keyword to name**, so those
   entries are pinned on the breadcrumb and the count alone, never on a word.

Keyword *names* that some later row might legitimately implement (``anyOf``,
``patternProperties``, ``maxItems``, ``contains``, ``maxLength``) are
conditioned on ``SUPPORTED_KEYWORDS`` membership, as the sibling oracles do, so
that row can land without editing this file. Unenforceable *forms* of already
supported keywords are pinned unconditionally, as the composition oracle pins
them.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
MANIFEST_SCHEMA_PATH = ROOT / "templates/dispatch/manifest.schema.json"
TASK_PACKET_SCHEMA_PATH = ROOT / "templates/dispatch/hybrid/task-packet.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


schema_check = _load("schema_check_audit_subject", SCRIPTS / "schema_check.py")

validate = schema_check.validate
UnsupportedKeyword = schema_check.UnsupportedKeyword

#: A keyword nobody will ever implement, for the many places that need a defect
#: whose name is guaranteed to stay a defect.
BOGUS = "totallyBogusKeyword"


def _handled(keyword: str) -> bool:
    return (keyword in schema_check.SUPPORTED_KEYWORDS
            or keyword in schema_check.ANNOTATION_KEYWORDS)


def _audit(schema, path="$"):
    """Call the seam, failing loudly if it is missing rather than erroring out."""
    function = getattr(schema_check, "audit_schema", None)
    if function is None:
        raise AssertionError(
            "schema_check.audit_schema is missing; this row adds it")
    return function(schema, path) if path != "$" else function(schema)


def _validate_raises(instance, schema) -> bool:
    try:
        validate(instance, schema)
    except UnsupportedKeyword:
        return True
    return False


# --------------------------------------------------------------------------
# The real schema nodes this row was written for.
# --------------------------------------------------------------------------

MANIFEST_SCHEMA = json.loads(MANIFEST_SCHEMA_PATH.read_text())
TASK_PACKET_SCHEMA = json.loads(TASK_PACKET_SCHEMA_PATH.read_text())

#: The three nodes of ``manifest.schema.json`` that cost repeated raise-and-fix
#: cycles, lifted from the real file. ``RealSchemaShapeTests`` asserts each one
#: still has the shape the tests below rely on, so a rewrite of that file fails
#: loudly instead of making this file vacuous.
REAL_NODES = {
    "action_classes": ("routing", "action_classes"),
    "commands": ("hybrid", "commands"),
    "skill_lock": ("instruction_set", "skill_lock"),
}


def _real_node(name):
    section, prop = REAL_NODES[name]
    return copy.deepcopy(
        MANIFEST_SCHEMA["properties"][section]["properties"][prop])


def _real_node_schema():
    """A schema wrapping the three real nodes at their real breadcrumbs."""
    return {
        "type": "object",
        "properties": {
            "routing": {
                "type": "object",
                "properties": {"action_classes": _real_node("action_classes")},
            },
            "hybrid": {
                "type": "object",
                "properties": {"commands": _real_node("commands")},
            },
            "instruction_set": {
                "type": "object",
                "properties": {"skill_lock": _real_node("skill_lock")},
            },
        },
    }


# --------------------------------------------------------------------------
# The table. Every entry is exercised by the equivalence tests below.
# --------------------------------------------------------------------------

#: name -> schema. ``audit_schema`` must return ``[]`` for each.
CLEAN_SCHEMAS = {
    "empty schema": {},
    "scalar": {"type": "string", "minLength": 1, "pattern": "^x"},
    "object with properties": {
        "type": "object",
        "required": ["a"],
        "additionalProperties": False,
        "properties": {"a": {"type": "string", "enum": ["x", "y"]}},
    },
    "additionalProperties as a subschema (implemented, not a defect)": {
        "type": "object",
        "additionalProperties": {"type": "string", "minLength": 1},
    },
    "array with items": {
        "type": "array", "minItems": 1, "uniqueItems": True,
        "items": {"type": "integer", "minimum": 0, "maximum": 9},
    },
    "composition": {
        "type": "object",
        "propertyNames": {"pattern": "^[a-z]+$"},
        "allOf": [{"type": "object"}],
        "oneOf": [{"required": ["a"]}, {"required": ["b"]}],
        "not": {"required": ["c"]},
        "if": {"required": ["a"]},
        "then": {"required": ["d"]},
    },
    "$defs and $ref": {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/thing"}},
        "$defs": {"thing": {"type": "string"}, "orphan": {"type": "integer"}},
    },
    "annotations only": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:x", "title": "t", "description": "d",
        "default": 1, "examples": [1], "deprecated": False,
        "format": "uri", "$comment": "c",
    },
    "the three real manifest nodes, unmodified": _real_node_schema(),
    "manifest.schema.json": MANIFEST_SCHEMA,
    "hybrid/task-packet.schema.json": TASK_PACKET_SCHEMA,
}

#: name -> (schema, breadcrumb, keyword-or-None, conditional-on-this-keyword)
#: Exactly one defect each. ``keyword is None`` marks a bare boolean in schema
#: position, which has no keyword to name.
SINGLE_DEFECT_SCHEMAS = {
    "unimplemented keyword at the root": (
        {"type": "object", "anyOf": [{"type": "object"}]}, "$", "anyOf", "anyOf"),
    "unimplemented keyword under properties": (
        {"type": "object",
         "properties": {"routing": {"type": "object",
                                    "patternProperties": {"^x$": {"type": "string"}}}}},
        "$.properties.routing", "patternProperties", "patternProperties"),
    "unimplemented keyword under items": (
        {"type": "array", "items": {"type": "array", "maxItems": 3}},
        "$.items", "maxItems", "maxItems"),
    "invented keyword in an unreferenced $defs": (
        {"type": "object", "$defs": {"orphan": {"type": "string", BOGUS: 1}}},
        "$.$defs.orphan", BOGUS, BOGUS),
    "unimplemented keyword under not": (
        {"not": {"contains": {"type": "string"}}},
        "$.not", "contains", "contains"),
    "unimplemented keyword under propertyNames": (
        {"type": "object", "propertyNames": {"maxLength": 3}},
        "$.propertyNames", "maxLength", "maxLength"),
    "invented keyword under an additionalProperties subschema": (
        {"type": "object", "additionalProperties": {"type": "string", BOGUS: 1}},
        "$.additionalProperties", BOGUS, BOGUS),
    "invented keyword under if": (
        {"if": {BOGUS: 1}, "then": {"type": "object"}}, "$.if", BOGUS, BOGUS),
    "invented keyword under then": (
        {"if": {"type": "object"}, "then": {BOGUS: 1}}, "$.then", BOGUS, BOGUS),
    "items as a positional list": (
        {"type": "array", "items": [{"type": "string"}, {"type": "integer"}]},
        "$", "items", None),
    "type as a union list, under allOf": (
        {"allOf": [{"type": "object"}, {"type": ["string", "integer"]}]},
        "$.allOf[1]", "type", None),
    "type as a union list, under oneOf": (
        {"oneOf": [{"type": ["string", "integer"]}, {"type": "array"}]},
        "$.oneOf[0]", "type", None),
    "a bare boolean in schema position": (
        {"type": "object", "properties": {"a": True}},
        "$.properties.a", None, None),
    "a dangling internal $ref": (
        {"type": "object", "properties": {"a": {"$ref": "#/$defs/missing"}}},
        "$.properties.a", "$ref", None),
    "an external $ref": (
        {"type": "object", "properties": {"a": {"$ref": "https://x/y.json"}}},
        "$.properties.a", "$ref", None),
    "allOf that is not a list": (
        {"allOf": {"type": "object"}}, "$", "allOf", None),
    "minItems that is not a number": (
        {"type": "array", "minItems": "3"}, "$", "minItems", None),
    "additionalProperties that is neither boolean nor subschema": (
        {"type": "object", "additionalProperties": "yes"},
        "$", "additionalProperties", None),
}

#: name -> (schema, [(breadcrumb, keyword-or-None), ...]). Several defects in
#: one schema, all of which must be reported. This is the entire point of the
#: row.
MULTI_DEFECT_SCHEMAS = {
    "three defects at three depths": (
        {
            "type": "object",
            BOGUS: 1,
            "properties": {
                "a": {"type": "array", "items": [{"type": "string"}]},
                "b": {"type": "object",
                      "properties": {"c": {"type": "object",
                                           "additionalProperties": "yes"}}},
            },
        },
        [("$", BOGUS),
         ("$.properties.a", "items"),
         ("$.properties.b.properties.c", "additionalProperties")],
    ),
    "five defects across five composition sites": (
        {
            "allOf": [{BOGUS: 1}],
            "oneOf": [{"type": "object"}, {"type": ["string", "integer"]}],
            "not": {"items": [{"type": "string"}]},
            "propertyNames": {"additionalProperties": "yes"},
            "$defs": {"orphan": {BOGUS: 2}},
        },
        [("$.allOf[0]", BOGUS),
         ("$.oneOf[1]", "type"),
         ("$.not", "items"),
         ("$.propertyNames", "additionalProperties"),
         ("$.$defs.orphan", BOGUS)],
    ),
    "two defects hiding under one array's items": (
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "x": {BOGUS: 1},
                    "y": {"type": ["string", "integer"]},
                },
            },
        },
        [("$.items.properties.x", BOGUS),
         ("$.items.properties.y", "type")],
    ),
    "a defect beside a bare boolean subschema": (
        {"type": "object", "properties": {"a": True, "b": {BOGUS: 1}}},
        [("$.properties.a", None), ("$.properties.b", BOGUS)],
    ),
}


def _real_nodes_with_defects():
    """The real manifest nodes, one invented keyword injected into each.

    Mirrors the historical failure: three unenforceable constructs in three
    nodes, the third reachable only through a ``oneOf``. Depends on the shapes
    ``RealSchemaShapeTests`` pins.
    """
    schema = _real_node_schema()
    properties = schema["properties"]
    action_classes = properties["routing"]["properties"]["action_classes"]
    action_classes["additionalProperties"]["properties"]["enabled"][BOGUS] = 1
    properties["hybrid"]["properties"]["commands"]["additionalProperties"][BOGUS] = 1
    properties["instruction_set"]["properties"]["skill_lock"]["oneOf"][0][
        "additionalProperties"][BOGUS] = 1
    return schema


REAL_DEFECT_BREADCRUMBS = (
    "$.properties.routing.properties.action_classes"
    ".additionalProperties.properties.enabled",
    "$.properties.hybrid.properties.commands.additionalProperties",
    "$.properties.instruction_set.properties.skill_lock.oneOf[0]"
    ".additionalProperties",
)

MULTI_DEFECT_SCHEMAS["the three real manifest nodes, one defect injected in each"] = (
    _real_nodes_with_defects(),
    [(breadcrumb, BOGUS) for breadcrumb in REAL_DEFECT_BREADCRUMBS],
)

#: Instances probed against every schema in the equivalence tests. Chosen to
#: cover each JSON type without tripping unrelated behaviour.
PROBE_INSTANCES = ({}, {"a": "x"}, {"a": 1, "b": 2}, [], ["x"], "x", 1, True)


def _live_single_defects():
    """Table rows whose defect is still a defect against today's keyword sets."""
    for name, row in SINGLE_DEFECT_SCHEMAS.items():
        schema, breadcrumb, keyword, conditional = row
        if conditional is not None and _handled(conditional):
            continue
        yield name, schema, breadcrumb, keyword


class AuditSeamTests(unittest.TestCase):
    """The seam itself: right shape, and it never raises."""

    def test_audit_schema_exists_and_is_callable(self):
        self.assertTrue(
            callable(getattr(schema_check, "audit_schema", None)),
            "this row adds audit_schema(schema, path='$') -> list[str]")

    def test_a_clean_schema_audits_to_the_empty_list(self):
        for name, schema in CLEAN_SCHEMAS.items():
            with self.subTest(schema=name):
                self.assertEqual(
                    _audit(schema), [],
                    f"{name} is enforceable, so its audit must be empty")

    def test_every_entry_is_a_string(self):
        for name, schema, _, _ in _live_single_defects():
            with self.subTest(schema=name):
                for entry in _audit(schema):
                    self.assertIsInstance(
                        entry, str, "entries are human-readable report lines")

    def test_the_audit_raises_nothing_even_on_malformed_schemas(self):
        malformed = {
            "a bare true": True,
            "a bare false": False,
            "a string in schema position": "not a schema",
            "None in schema position": None,
            "a list in schema position": [{"type": "string"}],
            "a dangling $ref": {"$ref": "#/$defs/missing"},
            "an external $ref": {"$ref": "https://x/y.json"},
            "allOf that is not a list": {"allOf": 3},
            "a boolean nested three deep": {
                "properties": {"a": {"properties": {"b": False}}}},
        }
        for name, schema in malformed.items():
            with self.subTest(schema=name):
                try:
                    entries = _audit(schema)
                except Exception as error:  # noqa: BLE001 -- the whole claim
                    self.fail(f"audit_schema raised on {name}: {error!r}; the "
                              f"seam reports, it never raises")
                self.assertIsInstance(entries, list)
                self.assertTrue(
                    entries,
                    f"{name} is not enforceable, so it must be reported")

    def test_a_self_referential_definition_terminates(self):
        schema = {"type": "object",
                  "properties": {"a": {"$ref": "#/$defs/loop"}},
                  "$defs": {"loop": {"properties": {"next": {"$ref": "#/$defs/loop"}}}}}
        self.assertEqual(
            _audit(schema), [],
            "a cycle through $defs must terminate, not recurse forever")

    def test_the_path_argument_roots_the_breadcrumbs(self):
        schema = {"type": "object", "properties": {"a": {BOGUS: 1}}}
        if _handled(BOGUS):
            self.skipTest(f"{BOGUS} is somehow supported")
        entries = _audit(schema, path="#/root")
        self.assertEqual(len(entries), 1)
        self.assertIn("#/root.properties.a", entries[0])


class BreadcrumbAndKeywordTests(unittest.TestCase):
    """Each entry says where the defect is and what it is."""

    def test_a_single_defect_is_reported_once(self):
        for name, schema, _, _ in _live_single_defects():
            with self.subTest(schema=name):
                self.assertEqual(
                    len(_audit(schema)), 1,
                    f"{name} carries exactly one unenforceable construct, so "
                    f"the audit reports exactly one entry")

    def test_a_single_defect_carries_its_breadcrumb(self):
        for name, schema, breadcrumb, _ in _live_single_defects():
            with self.subTest(schema=name):
                self.assertIn(
                    breadcrumb, _audit(schema)[0],
                    f"{name}: the entry must locate the offending node")

    def test_a_single_defect_names_its_keyword(self):
        for name, schema, _, keyword in _live_single_defects():
            if keyword is None:
                continue  # a bare boolean has no keyword to name
            with self.subTest(schema=name):
                self.assertIn(
                    keyword, _audit(schema)[0],
                    f"{name}: the entry must name the offending keyword")

    def test_a_defect_behind_a_ref_is_reported_naming_the_definition(self):
        if _handled(BOGUS):
            self.skipTest(f"{BOGUS} is somehow supported")
        schema = {"type": "object",
                  "properties": {"a": {"$ref": "#/$defs/thing"}},
                  "$defs": {"thing": {"type": "string", BOGUS: 1}}}
        entries = _audit(schema)
        self.assertTrue(entries, "a defect behind a $ref is still a defect")
        # Not pinning which of the two honest breadcrumbs is used: the node is
        # reachable both as $.$defs.thing and through the pointer.
        self.assertTrue(
            any("thing" in entry and BOGUS in entry for entry in entries),
            f"no entry named the offending definition and keyword: {entries}")


class MultipleDefectTests(unittest.TestCase):
    """Several defects in one schema, all reported. The entire point."""

    def test_every_defect_is_reported_with_a_distinct_breadcrumb(self):
        for name, (schema, expected) in MULTI_DEFECT_SCHEMAS.items():
            with self.subTest(schema=name):
                entries = _audit(schema)
                self.assertEqual(
                    len(entries), len(expected),
                    f"{name} carries {len(expected)} unenforceable "
                    f"constructs; the audit reported {len(entries)}: {entries}")
                claimed = set()
                for breadcrumb, keyword in expected:
                    hits = {index for index, entry in enumerate(entries)
                            if breadcrumb in entry
                            and (keyword is None or keyword in entry)}
                    self.assertTrue(
                        hits,
                        f"{name}: nothing reported for {breadcrumb} "
                        f"({keyword}); got {entries}")
                    free = hits - claimed
                    self.assertTrue(
                        free,
                        f"{name}: {breadcrumb} ({keyword}) has no entry of "
                        f"its own -- each offending node gets one entry; got "
                        f"{entries}")
                    claimed.add(sorted(free)[0])
                self.assertEqual(
                    len(claimed), len(entries),
                    f"{name}: every entry must correspond to one expected "
                    f"offending node; got {entries}")

    def test_at_least_one_case_carries_three_defects_at_different_depths(self):
        schema, expected = MULTI_DEFECT_SCHEMAS["three defects at three depths"]
        self.assertGreaterEqual(len(expected), 3)
        self.assertEqual(
            len({breadcrumb.count(".") for breadcrumb, _ in expected}),
            len(expected),
            "the three defects are meant to sit at three different depths")
        entries = _audit(schema)
        for breadcrumb, keyword in expected:
            self.assertTrue(
                any(breadcrumb in entry and keyword in entry
                    for entry in entries),
                f"missing {breadcrumb} ({keyword}) in {entries}")

    def test_the_three_real_manifest_nodes_are_all_found_in_one_pass(self):
        """The failure that motivated the row: three nodes, one run."""
        schema, expected = MULTI_DEFECT_SCHEMAS[
            "the three real manifest nodes, one defect injected in each"]
        if _handled(BOGUS):
            self.skipTest(f"{BOGUS} is somehow supported")
        entries = _audit(schema)
        self.assertEqual(
            len(entries), 3,
            f"three defective nodes, three entries, one run: {entries}")
        for breadcrumb in REAL_DEFECT_BREADCRUMBS:
            self.assertTrue(
                any(breadcrumb in entry for entry in entries),
                f"{breadcrumb} was not reported; got {entries}")

    def test_the_oneOf_reachable_node_is_not_the_one_that_gets_dropped(self):
        """``skill_lock.oneOf[0]`` was the one that took the extra cycle."""
        if _handled(BOGUS):
            self.skipTest(f"{BOGUS} is somehow supported")
        schema = _real_node_schema()
        schema["properties"]["instruction_set"]["properties"]["skill_lock"][
            "oneOf"][0]["additionalProperties"][BOGUS] = 1
        entries = _audit(schema)
        self.assertEqual(len(entries), 1, entries)
        self.assertIn(REAL_DEFECT_BREADCRUMBS[2], entries[0])
        self.assertIn(BOGUS, entries[0])


class RealSchemaShapeTests(unittest.TestCase):
    """The shapes lifted from ``manifest.schema.json`` still hold.

    Asserted separately from the audit claims so that a rewrite of that file
    fails *here*, loudly, instead of quietly making the tests above vacuous by
    injecting defects into nodes that no longer exist.
    """

    def test_the_real_schema_files_are_readable_objects(self):
        for name, schema in (("manifest.schema.json", MANIFEST_SCHEMA),
                             ("task-packet.schema.json", TASK_PACKET_SCHEMA)):
            with self.subTest(schema=name):
                self.assertIsInstance(schema, dict)
                self.assertIn("properties", schema)

    def test_action_classes_still_has_the_shape_this_file_relies_on(self):
        node = _real_node("action_classes")
        self.assertEqual(node.get("type"), "object")
        additional = node.get("additionalProperties")
        self.assertIsInstance(
            additional, dict,
            "action_classes uses additionalProperties in its subschema form; "
            "that form is implemented now, so it is not a defect -- but the "
            "injection sites below assume it is still a subschema")
        self.assertIsInstance(additional.get("properties"), dict)
        self.assertIn(
            "enabled", additional["properties"],
            "the injection site $...action_classes.additionalProperties"
            ".properties.enabled must exist")

    def test_hybrid_commands_still_has_the_shape_this_file_relies_on(self):
        node = _real_node("commands")
        self.assertIsInstance(
            node.get("additionalProperties"), dict,
            "the injection site $...commands.additionalProperties must exist")

    def test_skill_lock_still_hides_a_subschema_behind_a_oneOf(self):
        node = _real_node("skill_lock")
        branches = node.get("oneOf")
        self.assertIsInstance(
            branches, list, "skill_lock is a oneOf; that is the whole point")
        self.assertTrue(branches)
        self.assertIsInstance(
            branches[0].get("additionalProperties"), dict,
            "the injection site $...skill_lock.oneOf[0].additionalProperties "
            "must exist")

    def test_both_real_schema_files_are_fully_enforceable_today(self):
        for name, schema in (("manifest.schema.json", MANIFEST_SCHEMA),
                             ("task-packet.schema.json", TASK_PACKET_SCHEMA)):
            with self.subTest(schema=name):
                self.assertEqual(
                    _audit(schema), [],
                    f"{name} audits clean today; an audit that reports "
                    f"anything here is crying wolf on a shipped schema")


class ValidateIsUnchangedTests(unittest.TestCase):
    """``validate`` still raises on the first unenforceable construct."""

    def test_validate_still_raises_on_a_single_defect(self):
        for name, schema, _, _ in _live_single_defects():
            with self.subTest(schema=name):
                with self.assertRaises(
                        UnsupportedKeyword,
                        msg=f"{name}: validate must keep refusing; a gate that "
                            f"returns a list of complaints is a gate that "
                            f"passes"):
                    validate({}, schema)

    def test_validate_still_raises_on_a_multi_defect_schema(self):
        for name, (schema, _) in MULTI_DEFECT_SCHEMAS.items():
            with self.subTest(schema=name):
                with self.assertRaises(UnsupportedKeyword):
                    validate({}, schema)

    def test_validate_still_returns_violations_for_clean_schemas(self):
        for name, schema in CLEAN_SCHEMAS.items():
            with self.subTest(schema=name):
                result = validate({}, schema)
                self.assertIsInstance(result, list)

    def test_the_keyword_sets_are_untouched(self):
        self.assertIsInstance(schema_check.SUPPORTED_KEYWORDS, frozenset)
        self.assertIsInstance(schema_check.ANNOTATION_KEYWORDS, frozenset)
        self.assertTrue(schema_check.SUPPORTED_KEYWORDS)
        self.assertTrue(schema_check.ANNOTATION_KEYWORDS)
        self.assertFalse(
            schema_check.SUPPORTED_KEYWORDS & schema_check.ANNOTATION_KEYWORDS)


class AuditAndValidateAgreeTests(unittest.TestCase):
    """``audit_schema(s) == []`` iff ``validate(instance, s)`` does not raise.

    Pinned in both directions, over the whole table. An implementation where
    one drifts from the other reintroduces exactly the silence this module
    exists to prevent, in a new place: a schema the gate accepts but the audit
    condemns is a false alarm, and a schema the audit calls clean but the gate
    refuses is a fix the human cannot find.
    """

    def _all_schemas(self):
        for name, schema in CLEAN_SCHEMAS.items():
            yield f"clean: {name}", schema
        for name, row in SINGLE_DEFECT_SCHEMAS.items():
            yield f"single: {name}", row[0]
        for name, (schema, _) in MULTI_DEFECT_SCHEMAS.items():
            yield f"multi: {name}", schema
        for name, schema in {
            "a bare true": True,
            "a bare false": False,
            "a string in schema position": "not a schema",
            "None in schema position": None,
        }.items():
            yield f"malformed: {name}", schema

    def test_the_two_agree_in_both_directions_for_every_schema(self):
        for name, schema in self._all_schemas():
            for instance in PROBE_INSTANCES:
                with self.subTest(schema=name, instance=instance):
                    empty = _audit(schema) == []
                    raised = _validate_raises(instance, schema)
                    self.assertEqual(
                        empty, not raised,
                        f"{name}: audit_schema returned "
                        f"{'no' if empty else 'some'} entries but validate "
                        f"{'raised' if raised else 'did not raise'}; the two "
                        f"must agree exactly")

    def test_an_empty_audit_means_validate_accepts_the_schema(self):
        for name, schema in self._all_schemas():
            if _audit(schema) != []:
                continue
            with self.subTest(schema=name):
                for instance in PROBE_INSTANCES:
                    self.assertFalse(
                        _validate_raises(instance, schema),
                        f"{name}: the audit called it enforceable, so the "
                        f"gate must not refuse it")

    def test_a_non_empty_audit_means_validate_refuses_the_schema(self):
        for name, schema in self._all_schemas():
            if _audit(schema) == []:
                continue
            with self.subTest(schema=name):
                for instance in PROBE_INSTANCES:
                    self.assertTrue(
                        _validate_raises(instance, schema),
                        f"{name}: the audit found an unenforceable construct, "
                        f"so the gate must refuse it")


class AuditDiscriminationTests(unittest.TestCase):
    """The two wrong implementations this file exists to catch.

    1. **The silent stub.** An ``audit_schema`` that returns ``[]`` for
       everything. It is the current behaviour dressed up -- every schema
       "enforceable", nothing located, nothing named -- and it is the most
       likely wrong implementation, because it passes any test that only checks
       that the clean cases are clean. Killed by asserting a non-empty audit
       for every defective schema in the table, and by the iff above, which
       such a stub breaks on every defective row.

    2. **The first-defect-only stub.** An ``audit_schema`` that wraps the
       existing eager walk in a ``try``/``except`` and returns one entry. It
       looks right on every single-defect case and reproduces the exact failure
       this row was raised to fix: three defective nodes, one named per run,
       repeated raise-and-fix cycles. Killed by asserting the full count on the
       multi-defect cases, the real-manifest case among them.

    Both mistakes are asserted here directly rather than only as a consequence
    of the tests above, so a future edit that softens those tests still has to
    walk past this class.
    """

    def test_a_stub_that_always_returns_empty_is_refused(self):
        defective = [row[0] for row in SINGLE_DEFECT_SCHEMAS.values()]
        defective += [schema for schema, _ in MULTI_DEFECT_SCHEMAS.values()]
        reported = 0
        for schema in defective:
            if _audit(schema):
                reported += 1
        self.assertEqual(
            reported, len(defective),
            "every schema in the defect table carries at least one construct "
            "the checker cannot enforce; an audit that returns [] for any of "
            "them is the silence this module exists to prevent")

    def test_a_stub_that_reports_only_the_first_defect_is_refused(self):
        for name, (schema, expected) in MULTI_DEFECT_SCHEMAS.items():
            if len(expected) < 2:
                continue
            with self.subTest(schema=name):
                entries = _audit(schema)
                self.assertGreaterEqual(
                    len(entries), len(expected),
                    f"{name} carries {len(expected)} unenforceable "
                    f"constructs; reporting {len(entries)} is the "
                    f"raise-and-fix cycle this row was raised to end")
                breadcrumbs = {breadcrumb for breadcrumb, _ in expected}
                for breadcrumb in breadcrumbs:
                    self.assertTrue(
                        any(breadcrumb in entry for entry in entries),
                        f"{name}: {breadcrumb} went unreported")

    def test_reporting_and_raising_are_not_the_same_surface(self):
        """The audit reports where the gate raises; neither may impersonate the other."""
        schema, expected = MULTI_DEFECT_SCHEMAS["three defects at three depths"]
        entries = _audit(schema)
        self.assertGreaterEqual(len(entries), len(expected))
        with self.assertRaises(
                UnsupportedKeyword,
                msg="validate must still raise even though audit_schema now "
                    "returns a list for the same schema"):
            validate({}, schema)


if __name__ == "__main__":
    unittest.main()
