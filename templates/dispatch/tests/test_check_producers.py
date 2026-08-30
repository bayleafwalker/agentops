"""The producer check must discriminate, or it is another declaration with no producer.

A check that reports every contract "produced" is indistinguishable from one that
works, and it would be a particularly embarrassing failure here: this check exists
to find contracts nobody exercises, so a check that cannot tell them apart is its
own first finding.

Every case below therefore pairs a state with a control in the same synthetic
workspace. ``test_the_four_states_are_distinguished_in_one_workspace`` is the
falsifier: it builds one workspace containing all four states at once and fails the
moment any two of them collapse into each other.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "check_producers.py"

_spec = importlib.util.spec_from_file_location("check_producers", SCRIPT)
producers = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(producers)


# --------------------------------------------------------------------------- #
# Fixtures: a workspace shaped like agentops, small enough to reason about
# --------------------------------------------------------------------------- #


def _schema(token=None, required=("alpha", "beta"), properties=None, closed=True):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": list(required),
        "properties": properties or {"alpha": {"type": "string"}, "beta": {"type": "string"}},
    }
    if closed:
        schema["additionalProperties"] = False
    if token:
        schema["properties"]["schema_version"] = {"const": token}
        schema["required"] = ["schema_version", *schema["required"]]
    return schema


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "templates" / "dispatch").mkdir(parents=True)
    return root


def _validation_source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "auditctl" / "auditctl" / "validation.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


EMPTY_VALIDATION = "X = 1\n"


def _store(root: Path, rows) -> Path:
    """A minimal auditctl store with the columns the checker reads."""
    path = root / ".auditctl" / "auditctl.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE audit_event (id TEXT PRIMARY KEY, ts TEXT, type TEXT, actor TEXT,"
        " summary TEXT, refs TEXT, source TEXT, metadata TEXT)"
    )
    for index, row in enumerate(rows):
        conn.execute(
            "INSERT INTO audit_event VALUES (?,?,?,?,?,?,?,?)",
            (
                f"ad:{index}",
                "2026-08-30T00:00:00Z",
                row.get("type", "workflow.session"),
                "test",
                "summary",
                json.dumps(row.get("refs", [])),
                "test",
                json.dumps(row.get("metadata", {})),
            ),
        )
    conn.commit()
    conn.close()
    return path


def _run(workspace: Path, validation: Path):
    return producers.check(workspace, auditctl_source=validation)


def _state(result, contract):
    for finding in result["findings"]:
        if finding["contract"] == contract:
            return finding["state"]
    raise AssertionError(f"{contract} absent from findings: "
                         f"{[f['contract'] for f in result['findings']]}")


# --------------------------------------------------------------------------- #
# The four states, one at a time
# --------------------------------------------------------------------------- #


def test_a_schema_with_no_instance_anywhere_is_no_instance(workspace, tmp_path):
    _write(workspace / "templates/dispatch/ghost.schema.json", _schema(token="ghost/v1"))

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "ghost") == "no-instance"


def test_a_schema_whose_only_instance_is_its_own_example_is_examples_only(workspace, tmp_path):
    """The session-capsule case: a schema, an example beside it, and nothing else."""
    _write(workspace / "templates/dispatch/capsule.schema.json", _schema(token="capsule/v1"))
    _write(
        workspace / "templates/dispatch/capsule.example.json",
        {"schema_version": "capsule/v1", "alpha": "a", "beta": "b"},
    )

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "capsule") == "examples-only"


def test_examples_only_is_not_reported_as_produced(workspace, tmp_path):
    """The single assertion this whole check turns on. An example is not a producer."""
    _write(workspace / "templates/dispatch/capsule.schema.json", _schema(token="capsule/v1"))
    _write(
        workspace / "templates/dispatch/capsule.example.json",
        {"schema_version": "capsule/v1", "alpha": "a", "beta": "b"},
    )

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "capsule") != "produced"


def test_a_schema_with_an_artifact_instance_is_produced(workspace, tmp_path):
    _write(workspace / "templates/dispatch/note.schema.json", _schema(token="note/v1"))
    _write(
        workspace / "_artifacts/scope/notes/abc.json",
        {"schema_version": "note/v1", "alpha": "a", "beta": "b"},
    )

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    finding = next(f for f in result["findings"] if f["contract"] == "note")
    assert finding["state"] == "produced"
    assert finding["tiers"] == {"artifact": 1}


def test_a_schema_carried_inside_an_audit_event_is_produced(workspace, tmp_path):
    """A capsule travelling in an event's metadata is an instance, not an envelope."""
    _write(workspace / "templates/dispatch/note.schema.json", _schema(token="note/v1"))
    _store(workspace, [{"metadata": {"schema_version": "note/v1", "alpha": "a", "beta": "b"}}])

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    finding = next(f for f in result["findings"] if f["contract"] == "note")
    assert finding["state"] == "produced"
    assert finding["tiers"] == {"runtime": 1}


def test_an_unparseable_schema_is_cannot_determine_not_no_instance(workspace, tmp_path):
    """The workspace rule: a probe that could not run is not a negative result."""
    broken = workspace / "templates/dispatch/broken.schema.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text('{"type": "object", "required": ["a"', encoding="utf-8")

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    finding = next(f for f in result["findings"] if f["contract"] == "broken")
    assert finding["state"] == "cannot-determine"
    assert "does not parse" in finding["reason"]


def test_an_undiscriminating_schema_is_cannot_determine(workspace, tmp_path):
    """An open schema with no version token matches everything, which proves nothing."""
    _write(workspace / "templates/dispatch/loose.schema.json",
           _schema(closed=False, required=["alpha"]))
    _write(workspace / "_artifacts/scope/anything.json", {"alpha": "a", "gamma": "g"})

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    finding = next(f for f in result["findings"] if f["contract"] == "loose")
    assert finding["state"] == "cannot-determine"
    assert "no derivable discriminator" in finding["reason"]


def test_missing_auditctl_source_makes_the_whole_vocabulary_family_undeterminable(workspace):
    _write(workspace / "templates/dispatch/ghost.schema.json", _schema(token="ghost/v1"))

    result = producers.check(workspace, auditctl_source=Path("/nonexistent/validation.py"))

    assert any("could not be derived" in e or "cannot read" in e
               for e in result["probe_errors"])


# --------------------------------------------------------------------------- #
# The falsifier
# --------------------------------------------------------------------------- #


def test_the_four_states_are_distinguished_in_one_workspace(workspace, tmp_path):
    """One workspace, four contracts, four different answers.

    This is the test that fails if the check stops discriminating. Collapsing any
    pair of states -- treating an example as a producer, folding cannot-determine
    into no-instance, reporting everything produced -- breaks it.
    """
    _write(workspace / "templates/dispatch/produced.schema.json", _schema(token="produced/v1"))
    _write(workspace / "_artifacts/scope/real.json",
           {"schema_version": "produced/v1", "alpha": "a", "beta": "b"})

    _write(workspace / "templates/dispatch/illustrated.schema.json", _schema(token="illustrated/v1"))
    _write(workspace / "templates/dispatch/illustrated.example.json",
           {"schema_version": "illustrated/v1", "alpha": "a", "beta": "b"})

    _write(workspace / "templates/dispatch/named.schema.json", _schema(token="named/v1"))

    broken = workspace / "templates/dispatch/unreadable.schema.json"
    broken.write_text("{not json", encoding="utf-8")

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "produced") == "produced"
    assert _state(result, "illustrated") == "examples-only"
    assert _state(result, "named") == "no-instance"
    assert _state(result, "unreadable") == "cannot-determine"
    assert result["summary"] == {
        "no-instance": 1, "examples-only": 1, "produced": 1, "cannot-determine": 1
    }


def test_a_permissive_schema_does_not_silently_match_every_document(workspace, tmp_path):
    """Structural matching is only allowed to speak when the schema is tight."""
    _write(workspace / "templates/dispatch/tight.schema.json", _schema())
    _write(workspace / "_artifacts/scope/unrelated.json", {"totally": "different", "shape": 1})

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "tight") == "no-instance"


def test_a_near_miss_version_is_not_counted_as_the_version_it_is_not(workspace, tmp_path):
    _write(workspace / "templates/dispatch/note.schema.json", _schema(token="note/v2"))
    _write(workspace / "_artifacts/scope/old.json",
           {"schema_version": "note/v1", "alpha": "a", "beta": "b"})

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "note") == "no-instance"


def test_a_schema_id_alone_does_not_make_a_contract_determinable(workspace, tmp_path):
    """``$id`` names the schema, not the instance.

    A regression guard with a measured cause: while ``$id`` counted as a
    discriminator, ``capability-receipt`` was reported ``no-instance`` with a real
    receipt sitting in ``_artifacts/agentops/capability/receipts/``. Nothing in this
    workspace writes a matching ``$schema`` into its output, so an ``$id``-only
    schema is one the check cannot answer -- which is ``cannot-determine``, not "no".
    """
    _write(workspace / "templates/dispatch/opaque.schema.json", {
        "$id": "https://agentops.local/schemas/opaque.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["alpha", "beta"],
        "properties": {"alpha": {"type": ["string", "null"]}, "beta": {"type": "string"}},
    })

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "opaque") == "cannot-determine"


def test_a_string_version_enum_names_the_contract():
    """``capability-receipt`` reads v1 and v2. One contract, two names."""
    schema = {"properties": {"schema_version": {
        "enum": ["capability-receipt/v1", "capability-receipt/v2"]}}}

    assert producers._identity_tokens(schema) == (
        "capability-receipt/v1", "capability-receipt/v2")


def test_an_integer_version_enum_does_not_name_the_contract():
    """``manifest`` declares ``schema_version: {enum: [1, 2]}``; 1 identifies nothing."""
    schema = {"properties": {"schema_version": {"type": "integer", "enum": [1, 2]}}}

    assert producers._identity_tokens(schema) == ()


def test_any_accepted_version_counts_as_an_instance(workspace, tmp_path):
    schema = _schema(token="receipt/v1")
    schema["properties"]["schema_version"] = {"enum": ["receipt/v1", "receipt/v2"]}
    _write(workspace / "templates/dispatch/receipt.schema.json", schema)
    _write(workspace / "_artifacts/scope/r.json",
           {"schema_version": "receipt/v2", "alpha": "a", "beta": "b"})

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    assert _state(result, "receipt") == "produced"


# --------------------------------------------------------------------------- #
# Vocabulary contracts, derived by ast from auditctl's source
# --------------------------------------------------------------------------- #


VOCAB_SOURCE = """
COLOURS = frozenset({"red", "blue"})
PREFIXES = ("wi:", "ka:")
BOUNDS = {"phase": 32, "session": 128}
ALIAS_OF_COLOURS = COLOURS
lowercase = frozenset({"ignored"})
MIXED = frozenset({"a", 1})
"""


def test_vocabularies_are_derived_from_source_not_imported(workspace, tmp_path):
    contracts, error = producers.discover_vocabulary_contracts(
        _validation_source(tmp_path, VOCAB_SOURCE)
    )

    assert error is None
    names = {c.contract_id for c in contracts}
    assert names == {"COLOURS", "PREFIXES", "BOUNDS"}
    assert dict((c.contract_id, c.members) for c in contracts)["BOUNDS"] == ("phase", "session")


def test_an_alias_is_not_a_second_contract(tmp_path):
    contracts, _ = producers.discover_vocabulary_contracts(
        _validation_source(tmp_path, VOCAB_SOURCE)
    )

    colours = next(c for c in contracts if c.contract_id == "COLOURS")
    assert colours.aliases == ("ALIAS_OF_COLOURS",)
    assert "ALIAS_OF_COLOURS" not in {c.contract_id for c in contracts}


def test_an_unobserved_vocabulary_is_no_instance(workspace, tmp_path):
    _store(workspace, [{"type": "workflow.session", "metadata": {"cost": 1}}])

    result = _run(workspace, _validation_source(tmp_path, VOCAB_SOURCE))

    assert _state(result, "COLOURS") == "no-instance"


def test_an_observed_vocabulary_token_makes_it_produced_and_names_the_rest(workspace, tmp_path):
    _store(workspace, [{"type": "workflow.session", "metadata": {"colour": "red"}}])

    result = _run(workspace, _validation_source(tmp_path, VOCAB_SOURCE))

    finding = next(f for f in result["findings"] if f["contract"] == "COLOURS")
    assert finding["state"] == "produced"
    assert finding["observed"] == ["red"]
    assert finding["unobserved"] == ["blue"]


def test_a_prefix_token_is_observed_by_prefix(workspace, tmp_path):
    _store(workspace, [{"refs": ["wi:agentops#1"]}])

    result = _run(workspace, _validation_source(tmp_path, VOCAB_SOURCE))

    finding = next(f for f in result["findings"] if f["contract"] == "PREFIXES")
    assert finding["observed"] == ["wi:"]


def test_a_field_name_vocabulary_is_observed_as_a_key(workspace, tmp_path):
    """ENVELOPE_FIELDS names fields, not values; matching values alone would miss it."""
    _store(workspace, [{"metadata": {"phase": "review"}}])

    result = _run(workspace, _validation_source(tmp_path, VOCAB_SOURCE))

    finding = next(f for f in result["findings"] if f["contract"] == "BOUNDS")
    assert "phase" in finding["observed"]


# --------------------------------------------------------------------------- #
# The event-type census: the inverse measurement
# --------------------------------------------------------------------------- #


def test_the_census_counts_producers_that_have_no_declared_type(workspace, tmp_path):
    _store(workspace, [
        {"type": "workflow.session"},
        {"type": "workflow.session"},
        {"type": "dispatch.exit", "metadata": {"terminal_reason": "crash-inferred"}},
    ])

    result = _run(workspace, _validation_source(tmp_path, EMPTY_VALIDATION))

    census = result["event_types"]
    assert census["declared_vocabulary"] is None
    assert census["observed"] == {"workflow.session": 2, "dispatch.exit": 1}


# --------------------------------------------------------------------------- #
# Exit codes: an instrument by default, a bar only when a caller names a subject
# --------------------------------------------------------------------------- #


def test_it_exits_zero_even_when_nothing_is_produced(workspace, tmp_path, capsys):
    _write(workspace / "templates/dispatch/ghost.schema.json", _schema(token="ghost/v1"))
    validation = _validation_source(tmp_path, EMPTY_VALIDATION)

    code = producers.main([
        "--workspace", str(workspace), "--auditctl-source", str(validation)
    ])

    assert code == 0
    assert "no-instance" in capsys.readouterr().out


def test_fail_on_turns_it_into_a_gate_for_a_caller_that_names_one(workspace, tmp_path):
    _write(workspace / "templates/dispatch/ghost.schema.json", _schema(token="ghost/v1"))
    validation = _validation_source(tmp_path, EMPTY_VALIDATION)

    code = producers.main([
        "--workspace", str(workspace), "--auditctl-source", str(validation),
        "--fail-on", "no-instance",
    ])

    assert code == 1


def test_fail_on_does_not_fire_on_a_state_that_is_absent(workspace, tmp_path):
    _write(workspace / "templates/dispatch/note.schema.json", _schema(token="note/v1"))
    _write(workspace / "_artifacts/scope/real.json",
           {"schema_version": "note/v1", "alpha": "a", "beta": "b"})
    validation = _validation_source(tmp_path, EMPTY_VALIDATION)

    code = producers.main([
        "--workspace", str(workspace), "--auditctl-source", str(validation),
        "--fail-on", "no-instance,examples-only",
    ])

    assert code == 0


def test_an_unknown_fail_on_state_is_a_usage_error(workspace, tmp_path):
    code = producers.main([
        "--workspace", str(workspace), "--fail-on", "probably-fine",
    ])

    assert code == 2


def test_a_missing_workspace_is_a_usage_error():
    assert producers.main(["--workspace", "/nonexistent/workspace"]) == 2


def test_json_output_is_machine_readable(workspace, tmp_path, capsys):
    _write(workspace / "templates/dispatch/ghost.schema.json", _schema(token="ghost/v1"))
    validation = _validation_source(tmp_path, EMPTY_VALIDATION)

    producers.main([
        "--workspace", str(workspace), "--auditctl-source", str(validation), "--json"
    ])

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["no-instance"] == 1


# --------------------------------------------------------------------------- #
# Locus classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("relative,expected", [
    ("templates/dispatch/x.example.json", "example"),
    ("templates/dispatch/tests/fixture.json", "example"),
    ("templates/dispatch/execution-plan/fixtures/bindings.json", "example"),
    ("_artifacts/agentops/model/claim-a.json", "artifact"),
    ("docs/evidence/packets/V5.json", "artifact"),
    ("templates/dispatch/role-presets/planner.json", "committed"),
])
def test_locus_tiers(relative, expected):
    assert producers.locus_tier(Path("/ws") / relative) == expected


# --------------------------------------------------------------------------- #
# The live workspace: the check must reproduce the two known cases
# --------------------------------------------------------------------------- #


LIVE = HERE.parent.parent.parent  # the agentops repository root
LIVE_CAPSULE = LIVE / "templates/dispatch/session-mechanization/session-capsule.schema.json"


@pytest.mark.skipif(not LIVE_CAPSULE.is_file(), reason="not running inside agentops")
def test_on_the_live_workspace_session_capsule_is_not_produced_and_something_is():
    """The two controls the brief demands, measured against the real tree.

    ``session-capsule`` is known unproduced -- ``docs/contracts/session-resolved-context.md``
    says it "has never emitted an instance" -- and ``workflow.session`` is the most
    written event type on record. If this check reported both the same way it would
    be worthless, so it is asserted that it does not.
    """
    result = producers.check(LIVE)

    assert _state(result, "session-capsule") in {"examples-only", "no-instance"}
    assert result["event_types"]["observed"].get("workflow.session", 0) > 100
    assert result["summary"]["produced"] > 0
    assert result["summary"]["no-instance"] > 0


# --------------------------------------------------------------------------- #
# Runtime spread: a count alone reads a fixture as a producer
# --------------------------------------------------------------------------- #


def _spread_event(source, ts, subject, event_type="x"):
    return {"type": event_type, "source": source, "actor": source, "ts": ts,
            "metadata": {"task_id": subject}}


def test_one_source_one_day_one_subject_is_narrow():
    """Every `dispatch.*` event in the agentops store is this shape.

    All carry `task_id` `EX-1`, the packet fixture from `test_hybrid_dispatch.py`, on one
    day from one source. Read as "24 reviewed, 11 preflight-rejected" that is a working
    dispatch cycle; read with its spread beside it, it is one rehearsal. The check still
    refuses to *call* it a test -- a young contract and a fixture look identical from
    here -- so it reports the shape and leaves the verdict with the reader.
    """
    events = [_spread_event("hybrid-dispatch", f"2026-08-29T10:0{i}:00Z", "EX-1") for i in range(5)]
    spread = producers.runtime_concentration(events)
    assert spread["narrow"] is True
    assert spread["events"] == 5
    assert spread["subjects"] == ["task_id=EX-1"]


def test_many_subjects_over_many_days_is_not_narrow():
    events = [_spread_event("claude-hook", f"2026-08-2{i}T10:00:00Z", f"task-{i}") for i in range(5)]
    spread = producers.runtime_concentration(events)
    assert spread["narrow"] is False
    assert len(spread["days"]) == 5


def test_no_events_yields_no_spread():
    """A contract with only committed instances has no runtime shape to report.

    A zeroed spread would read as "measured, and narrow" for something never measured at
    all -- the distinction this whole check exists to keep.
    """
    assert producers.runtime_concentration([]) is None


def test_spread_is_an_instrument_and_does_not_change_the_state():
    """Narrow must not silently demote `produced`.

    A reader decides what a narrow producer means, exactly as with `cannot-determine`.
    """
    narrow = [_spread_event("hybrid-dispatch", "2026-08-29T10:00:00Z", "EX-1")]
    assert producers.runtime_concentration(narrow)["narrow"] is True
    assert producers.STATES == ("no-instance", "examples-only", "produced", "cannot-determine")
