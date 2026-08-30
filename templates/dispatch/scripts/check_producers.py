#!/usr/bin/env python3
"""Answer, for every contract this workspace declares: has anything ever produced one?

The workspace's recurring defect is not a missing schema. It is a schema, a
validated vocabulary or a hook, complete with tests, that no writer ever exercises.
Four instances were measured on 2026-08-30 alone: a terminal-reason vocabulary
enforced for three months after its only writer was retired; a ``SubagentStop``
hook whose only two production rows are both test rows;
``session-capsule.schema.json``, with sibling scripts, skills and 81 test functions
and (per ``docs/contracts/session-resolved-context.md``) no instance; and
auditctl's ``.auditctl-id``, implemented, documented, and absent from the fleet.

The owner's direction document already names this a falsifier
(``vuoro/docs/plans/2026-08-22-long-term-direction.md`` §13 item 11): *"Every ledger
contract names the lifecycle events its transitions emit, and those events are
observed in auditctl. A Vuoro object that emits no lifecycle events is not an
object, it is a name."* Nothing mechanized it. This does.

What it is *not*
----------------

**Not a gate.** It exits 0 whatever it finds, unless a caller opts in with
``--fail-on``. Two reasons, both from ``docs/plans/agentops/meta-narrative-plan-2026-08-29.md`` §2:

* *"A measurement that never blocks anything is an instrument, not a bar"* — said
  of D8, which was moved to telemetry rather than deleted. An instrument is a
  legitimate thing to build, and this is one.
* *"Every scenario needs an admission subject. A gate with no subject is a gate
  that applies to everyone."* "Every declared contract must have a producer" has no
  subject today. Applied to the standing inventory it fails on the majority of
  schemas at once, which makes it a bar nobody can clear and therefore one that
  gets switched off — the exact fate of the ``dispatchable`` promotion gate. The
  subject that *would* work is narrower and does not exist yet: *a schema added or
  changed by this change*. When something computes that set, it can pass
  ``--fail-on`` and become a bar with a subject.

There is a third reason, and it is the stronger one: this check reports
``cannot-determine``, and does so today. A measurement that admits it could not
look is not yet sound enough to block on. Fold that state into "no instance" and
the gate would fail contracts it never examined.

**Not a hand-written inventory.** A hand-maintained list of contracts would itself
be a declaration with no producer — this check would have to report on itself. Both
families are derived:

* **Schema contracts** — every ``*.schema.json`` under ``templates/dispatch/``.
* **Vocabulary contracts** — every module-level ``UPPER_CASE`` constant in
  ``auditctl/validation.py`` whose value is a literal collection of strings. Read
  by ``ast``, never imported: the checker must run where auditctl is not installed,
  and reading a source file is not the same authority as executing it.

Where the derivation genuinely stops, the output says so rather than filling the
hole with a constant. If auditctl's source cannot be found, the vocabulary family
is reported ``cannot-determine`` in full, not omitted.

How an instance is recognised
-----------------------------

Three discriminators, in descending strength, each derived from the schema itself:

1. ``properties.schema_version`` — a ``const``, or a ``string`` ``enum`` when one
   contract still reads several of its own versions. A document that names itself.
   An **integer** enum (``manifest``'s ``{"enum": [1, 2]}``) is refused: ``1`` counts
   revisions, it does not identify a contract.
2. Structural validation via the sibling ``schema_check`` module, and only when the
   schema is **discriminating**: ``additionalProperties: false`` plus at least two
   required properties, and every keyword in it one that ``schema_check`` will
   actually enforce. A permissive schema matches every object in the workspace, which
   is not evidence of anything; a keyword the checker refuses is not a weaker match
   but an unexamined one.
3. ``$id`` — a document whose ``$schema`` points at this file. Accepted as a match
   where it occurs, but it does **not** make a contract determinable, because ``$id``
   names the schema and not the instance: whether a producer writes a matching
   ``$schema`` is its own choice, and none in this workspace does. Counting it
   reported ``capability-receipt`` as having no instance while a real receipt sat in
   ``_artifacts/agentops/capability/receipts/``.

A schema with neither an identity token nor an enforceable discriminating shape
yields ``cannot-determine``, naming the keyword or the defect that stopped it.

Vocabulary tokens are matched generically — a token counts as observed when it
appears in an event record as a scalar value, as the prefix of one (``wi:``,
``sha:``), or as an object key (``ENVELOPE_FIELDS`` names fields, not values).
Generic matching can over-report, so every hit carries its locus and the human
reading the output can judge it. Over-reporting is the safe direction here: this
check exists to find contracts with *no* producer.

Where it looks
--------------

Instances are looked for where they would actually be, not where they are declared:

* every ``.auditctl/auditctl.db`` SQLite store under the search roots (enumerated,
  never hardcoded — there were 8 on 2026-08-30);
* every ``_artifacts/**/audit/*.ndjson`` shard;
* every other JSON file under the roots.

Search roots default to the agentops workspace, its parent's materialized project
workspaces (a directory holding ``project.context.json``), and the parent tree's
audit stores.

The four states
---------------

``produced``
    At least one instance in a *runtime* locus (an audit row or shard line) or an
    *artifact* locus (under ``_artifacts/`` or ``docs/evidence/``). Something wrote
    one because work happened.

``examples-only``
    Instances exist, and every one is a committed file — ``*.example.json``, a test
    fixture, or a record sitting next to its own schema. **This is a distinct state
    and not a pass.** A schema whose only instances are its own examples is the
    precise case this check was built to catch: the example was written to
    illustrate the schema, so it proves the author understood the schema, and
    nothing else. It is the shape of a producer without a producer.

``no-instance``
    Nothing, anywhere. The contract is a name.

``cannot-determine``
    The probe could not run: the schema does not parse, it offers no derivable
    discriminator, ``schema_check`` refuses a keyword, a store will not open, or
    auditctl's source is missing. **Never folded into ``no-instance``.** A probe that
    could not run is a different fact from a negative result, and that distinction is
    the workspace rule this check would otherwise violate while enforcing it.

What it cannot tell you
-----------------------

``produced`` means an instance exists in a production locus. It does **not** mean
the instance came from real work. The two ``dispatch.exit`` rows in
``/projects/dev/.auditctl/auditctl.db`` are a live probe and a test
(``session`` = ``probe-live-1`` and ``test-1``), and they are what make
``TERMINAL_REASON_CODES`` and ``DISPATCH_EXIT_BOUNDS`` report ``produced`` here.
Separating a test row from a real one would require guessing at session names, and a
guess dressed as a measurement is worse than a measurement with a stated limit. Every
finding carries its loci for exactly this reason: read them.

The per-token coverage on a vocabulary is the sharper number. ``TERMINAL_REASON_CODES``
is ``produced`` on the strength of one code out of seven, and the output says so.

Usage::

    check_producers.py                     # human report over this workspace
    check_producers.py --json              # machine-readable findings
    check_producers.py --fail-on no-instance,examples-only

Exit 0 when the measurement completed (whatever it says), 1 when a state named by
``--fail-on`` was found, 2 on a usage or I/O error that prevented the run.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: The four reported states, in the order a reader should scan them: worst first,
#: with the honest non-answer last so it is never mistaken for a verdict.
STATES = ("no-instance", "examples-only", "produced", "cannot-determine")

#: Where a matched instance was found. The first two are production, the last two
#: are not, and keeping them apart is the whole point of ``examples-only``.
LOCUS_TIERS = ("runtime", "artifact", "example", "committed")
PRODUCING_TIERS = frozenset({"runtime", "artifact"})

#: Directories that hold build output, caches or vendored code. Nothing under them
#: is evidence that a contract was produced by this workspace.
SKIP_DIRS = frozenset({
    ".git", "node_modules", ".next", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv", "dist", "build", ".ruff_cache", ".worktrees",
})

#: Path segments that mark a JSON file as illustrative rather than produced.
EXAMPLE_SEGMENTS = frozenset({"tests", "test", "fixtures", "fixture", "examples", "testdata"})

#: Roots under which a JSON file is evidence that a tool ran, not that an author typed.
ARTIFACT_SEGMENTS = ("_artifacts", "evidence")

#: A schema with no self-identifying token is only usable as a discriminator when
#: it is tight enough that matching it means something. Two required properties is
#: the floor: a single-required-property closed object still matches too much.
MIN_REQUIRED_FOR_STRUCTURAL = 2


def _load_schema_check():
    """Import the sibling hand-rolled validator by path, not by package name.

    These scripts are not a package and are run from anywhere, so a plain import
    would resolve against the caller's CWD.
    """
    spec = importlib.util.spec_from_file_location(
        "_check_producers_schema_check", HERE / "schema_check.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - packaging accident
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Contract discovery
# --------------------------------------------------------------------------- #


class Contract:
    """A declared contract and the discriminators by which its instances are known."""

    def __init__(self, contract_id, family, source, *, token=None, schema_id=None,
                 schema=None, structural=False, undetermined=None, members=None):
        self.contract_id = contract_id
        self.family = family            # "schema" | "vocabulary"
        self.source = source            # path, relative to the workspace when possible
        self.token = tuple(token) if token else ()   # accepted schema_version values
        self.schema_id = schema_id      # $id
        self.schema = schema
        self.structural = structural
        self.undetermined = undetermined  # reason string, or None
        self.members = tuple(members or ())  # vocabulary tokens

    @property
    def discriminators(self):
        found = []
        if self.token:
            found.append("schema_version")
        if self.schema_id:
            found.append("$id")
        if self.structural:
            found.append("structural")
        return found


def discover_schema_contracts(templates_root, checker):
    """Every ``*.schema.json`` under ``templates_root``, with its discriminators.

    A schema that will not parse, or that offers no usable discriminator, is
    returned carrying an ``undetermined`` reason rather than dropped. Dropping it
    would report the workspace as cleaner than it is.
    """
    contracts = []
    for path in sorted(templates_root.rglob("*.schema.json")):
        if _skipped(path):
            continue
        contract_id = path.stem.removesuffix(".schema").removesuffix(".v1").removesuffix(".v2")
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            contracts.append(Contract(
                contract_id, "schema", path,
                undetermined=f"schema does not parse: {exc}",
            ))
            continue
        if not isinstance(schema, dict):
            contracts.append(Contract(
                contract_id, "schema", path,
                undetermined="schema is not a JSON object",
            ))
            continue

        tokens = _identity_tokens(schema)
        required = schema.get("required")
        token_required = bool(tokens) and isinstance(required, list) and "schema_version" in required
        schema_id = schema.get("$id") if isinstance(schema.get("$id"), str) else None

        structural, reason = _structural_usable(schema, checker)
        undetermined = None
        if not (tokens or structural):
            # ``$id`` deliberately does not count here. It names the schema, not the
            # instance, and a document only carries a matching ``$schema`` if its
            # producer chose to -- none in this workspace do. Counting it as a
            # discriminator reported ``capability-receipt`` as having no instance
            # while one sat in ``_artifacts/agentops/capability/receipts/``.
            undetermined = f"no derivable discriminator ({reason})"
        contract = Contract(
            contract_id, "schema", path,
            token=tokens, schema_id=schema_id, schema=schema,
            structural=structural, undetermined=undetermined,
        )
        contract.token_required = token_required
        contracts.append(contract)
    return contracts


def _identity_tokens(schema):
    """The ``schema_version`` values that name this contract, as a tuple.

    ``const`` is one token; a string ``enum`` is several, because a schema that
    still reads two of its own versions is one contract with two names
    (``capability-receipt/v1`` and ``/v2``, ``agentops-task/v1..v3``).

    An **integer** enum is rejected. ``manifest.schema.json`` declares
    ``schema_version: {"enum": [1, 2]}``, and ``1`` is a version, not a name: any
    JSON document in the workspace with a ``schema_version`` of 1 would match it.
    A discriminator must identify the contract, not merely count its revisions.
    """
    version = (schema.get("properties") or {}).get("schema_version")
    if not isinstance(version, dict):
        return ()
    if isinstance(version.get("const"), str):
        return (version["const"],)
    enum = version.get("enum")
    if isinstance(enum, list) and enum and all(isinstance(v, str) for v in enum):
        return tuple(enum)
    return ()


def _structural_usable(schema, checker):
    """Can this schema be used as a discriminator on shape alone?

    Only when it is closed and demands at least two properties, *and* the sibling
    checker will actually enforce it. A keyword the checker refuses is not a
    weaker match, it is an unexamined one.
    """
    if checker is None:
        return False, "schema_check unavailable"
    if schema.get("additionalProperties") is not False:
        return False, "schema is open (additionalProperties is not false)"
    required = schema.get("required")
    if not isinstance(required, list) or len(required) < MIN_REQUIRED_FOR_STRUCTURAL:
        return False, f"fewer than {MIN_REQUIRED_FOR_STRUCTURAL} required properties"
    try:
        checker.validate({}, schema)
    except checker.UnsupportedKeyword as exc:
        return False, f"schema_check cannot enforce: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"schema_check raised {type(exc).__name__}: {exc}"
    return True, "closed and discriminating"


def discover_vocabulary_contracts(validation_source):
    """Every literal string-collection constant in ``auditctl/validation.py``.

    Read with ``ast``. Importing would require auditctl on the path and would run
    its module body; a checker that answers "is this contract produced" must not
    need the contract's own package installed to answer.

    Aliases (``X = Y``) are recorded as a note on the aliased vocabulary rather than
    as a second contract: ``ACTIONQ_TERMINAL_REASON_CODES`` and
    ``TERMINAL_REASON_CODES`` are one vocabulary under two names, and counting them
    twice would double every finding about it.
    """
    try:
        text = validation_source.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, SyntaxError) as exc:
        return None, f"cannot read {validation_source}: {exc}"

    vocabularies = {}
    aliases = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not target.id.isupper():
            continue
        members = _string_collection(node.value)
        if members is not None:
            vocabularies[target.id] = members
        elif isinstance(node.value, ast.Name) and node.value.id.isupper():
            aliases.setdefault(node.value.id, []).append(target.id)

    contracts = []
    for name in sorted(vocabularies):
        contract = Contract(
            name, "vocabulary", validation_source, members=vocabularies[name]
        )
        contract.aliases = tuple(aliases.get(name, ()))
        contracts.append(contract)
    return contracts, None


def _string_collection(node):
    """The string members of a literal set/tuple/list, or a dict's literal keys."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset":
        if len(node.args) == 1:
            return _string_collection(node.args[0])
        return None
    if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        values = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if values and len(values) == len(node.elts):
            return tuple(values)
        return None
    if isinstance(node, ast.Dict):
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if keys and len(keys) == len(node.keys):
            return tuple(keys)
        return None
    return None


def find_auditctl_validation(search_from):
    """Locate ``auditctl/validation.py`` among the workspace's sibling repositories.

    Derived, like everything else: the parent tree is scanned one level deep for a
    repository that contains it. Absence is reported, never assumed away.
    """
    candidates = [search_from / "auditctl" / "validation.py"]
    parent = search_from.parent
    if parent != search_from:
        for entry in sorted(parent.iterdir()) if parent.is_dir() else []:
            if entry.is_dir() and not entry.name.startswith("."):
                candidates.append(entry / "auditctl" / "validation.py")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Instance discovery
# --------------------------------------------------------------------------- #


def _skipped(path):
    return any(part in SKIP_DIRS for part in path.parts)


def locus_tier(path):
    """Classify where a JSON file sits. See ``LOCUS_TIERS``.

    A file under ``_artifacts/`` or an ``evidence/`` tree was written by a tool run.
    Anything matching an example or fixture segment was written by an author to show
    what the schema means. Everything else committed in the tree is ``committed``:
    a record living beside its own schema is, for this check's purpose, an example
    that forgot to say so.
    """
    parts = path.parts
    name = path.name
    if name.endswith(".example.json") or "example" in name:
        return "example"
    if any(part in EXAMPLE_SEGMENTS for part in parts):
        return "example"
    if any(part in ARTIFACT_SEGMENTS or part.startswith("_artifacts") for part in parts):
        return "artifact"
    return "committed"


def runtime_concentration(events):
    """How narrow the runtime evidence for a contract is, as counts rather than a verdict.

    ``produced`` says an instance exists in a production locus. It cannot say the
    instance came from real work, and this module refuses to guess at that from session
    names -- a guess dressed as a measurement is worse than a measurement with a stated
    limit. But the limit does not have to be left to prose.

    Every ``dispatch.*`` event in the agentops store is one ``task_id`` (``EX-1``, the
    fixture in ``tests/test_hybrid_dispatch.py``), one source, one day. Read as a bare
    count -- 24 reviewed, 11 preflight-rejected -- that looks like a working producer.
    Read with its spread, it does not. So report the spread and let the reader judge;
    that is measurement, and the verdict stays theirs.

    ``narrow`` is a description, not a failure: a genuinely young contract looks the
    same as a fixture, and this cannot and should not tell them apart.
    """
    if not events:
        return None
    sources, actors, days, subjects = set(), set(), set(), set()
    for event in events:
        sources.add(str(event.get("source") or "?"))
        actors.add(str(event.get("actor") or "?"))
        days.add(str(event.get("ts") or "")[:10] or "?")
        metadata = event.get("metadata")
        if isinstance(metadata, dict):
            for key in ("task_id", "session", "session_id", "repo_id"):
                if metadata.get(key) is not None:
                    subjects.add(f"{key}={metadata[key]}")
                    break
    return {
        "events": len(events),
        "sources": sorted(sources),
        "actors": sorted(actors),
        "days": sorted(days),
        "subjects": sorted(subjects),
        "narrow": len(sources) == 1 and len(days) == 1 and len(subjects) <= 1,
    }


def collect_json_files(roots):
    """Every candidate JSON document under the roots, excluding the schemas themselves."""
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            if _skipped(path) or path.name.endswith(".schema.json"):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def collect_audit_stores(roots):
    """Every ``.auditctl/auditctl.db`` under the roots. Enumerated, never listed."""
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob(".auditctl/auditctl.db")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def collect_shards(roots):
    """Every append-only NDJSON shard under an ``_artifacts/**/audit/`` path."""
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("_artifacts/*/audit*/*.ndjson")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def read_store_events(db_path):
    """Every row of ``audit_event`` as an event dict, with JSON columns parsed.

    Returns ``(events, error)``. An unreadable store is an error, not an empty
    store; the caller turns that into ``cannot-determine`` for everything it would
    have answered.
    """
    events = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return events, f"{db_path}: {exc}"
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_event").fetchall()
    except sqlite3.Error as exc:
        conn.close()
        return events, f"{db_path}: {exc}"
    for row in rows:
        event = {}
        for key in row.keys():
            value = row[key]
            if isinstance(value, str) and value[:1] in "{[":
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            event[key] = value
        events.append(event)
    conn.close()
    return events, None


def read_shard_events(path):
    """Every parseable line of an NDJSON shard. Returns ``(events, error)``."""
    events = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return events, f"{path}: {exc}"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events, None


def candidate_documents(event):
    """The objects inside an audit event that could themselves be a schema instance.

    An event is an envelope. A capsule or a receipt travels *inside* it, under
    ``metadata``, ``payload`` or a JSON ``detail`` — so matching only the envelope
    would miss every contract that is carried rather than emitted.
    """
    documents = [event]
    for key in ("metadata", "payload", "detail", "resolved_context"):
        value = event.get(key)
        if isinstance(value, dict):
            documents.append(value)
            for nested in value.values():
                if isinstance(nested, dict):
                    documents.append(nested)
    return documents


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #


def matches(document, contract, checker):
    """Does ``document`` instantiate ``contract``? Returns the discriminator, or None."""
    if not isinstance(document, dict):
        return None
    if contract.token and document.get("schema_version") in contract.token:
        return "schema_version"
    if contract.schema_id and document.get("$schema") == contract.schema_id:
        return "$id"
    if contract.token and getattr(contract, "token_required", False):
        # When the schema *requires* its own version token, every valid instance
        # carries it, so shape is not allowed to stand in for the name. Falling back
        # here would let a near-miss document -- wrong version, right fields -- count
        # as an instance of the version it is not.
        #
        # ``$id`` deliberately does not suppress the fallback. ``$id`` is a property
        # of the schema; whether an instance carries a matching ``$schema`` is a
        # choice its producer makes, and most do not. Treating ``$id`` as a required
        # name reported every ``$id``-only schema in this workspace as unproduced,
        # including ones with instances sitting in ``_artifacts/``.
        return None
    if contract.structural and checker is not None:
        try:
            if checker.validate(document, contract.schema) == []:
                return "structural"
        except Exception:
            return None
    return None


def _scalars_and_keys(value, out, depth=0):
    """Flatten a record to the strings a vocabulary token could be observed as."""
    if depth > 12:
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            out.add(key)
            _scalars_and_keys(nested, out, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _scalars_and_keys(item, out, depth + 1)
    elif isinstance(value, str):
        out.add(value)


def vocabulary_hits(event, members):
    """Which vocabulary tokens this event observes.

    Exact match on a value or key, or — for a token that is itself a prefix, like
    ``wi:`` — a value that starts with it.
    """
    strings = set()
    _scalars_and_keys(event, strings)
    hits = set()
    for token in members:
        if token in strings:
            hits.add(token)
        elif token.endswith(":") and any(s.startswith(token) for s in strings):
            hits.add(token)
    return hits


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #


def check(workspace, *, extra_roots=(), auditctl_source=None):
    """Return the full finding record. Pure over the filesystem; never writes."""
    workspace = Path(workspace).resolve()
    checker = _load_schema_check()
    templates_root = workspace / "templates" / "dispatch"

    roots = [workspace]
    parent = workspace.parent
    projects_dir = parent / "_projects"
    if projects_dir.is_dir():
        for entry in sorted(projects_dir.iterdir()):
            if entry.is_dir() and (entry / "project.context.json").is_file():
                roots.append(entry)
    roots.extend(Path(r).resolve() for r in extra_roots)

    probe_errors = []

    # --- contracts -------------------------------------------------------- #
    schema_contracts = []
    if templates_root.is_dir():
        schema_contracts = discover_schema_contracts(templates_root, checker)
    else:
        probe_errors.append(f"no templates root at {templates_root}")

    if auditctl_source is None:
        auditctl_source = find_auditctl_validation(workspace)
    vocab_contracts, vocab_error = ([], None)
    if auditctl_source is None:
        vocab_error = (
            "auditctl/validation.py not found; the vocabulary family could not be derived"
        )
    else:
        vocab_contracts, vocab_error = discover_vocabulary_contracts(Path(auditctl_source))
        if vocab_contracts is None:
            vocab_contracts = []
    if vocab_error:
        probe_errors.append(vocab_error)

    contracts = schema_contracts + vocab_contracts

    # --- corpus ----------------------------------------------------------- #
    stores = list(collect_audit_stores([parent] + roots))
    shards = list(collect_shards(roots))
    files = list(collect_json_files(roots))

    runtime_events = []   # (locus, event)
    for store in stores:
        events, error = read_store_events(store)
        if error:
            probe_errors.append(error)
            continue
        for event in events:
            runtime_events.append((str(store), event))
    for shard in shards:
        events, error = read_shard_events(shard)
        if error:
            probe_errors.append(error)
            continue
        for event in events:
            runtime_events.append((str(shard), event))

    file_documents = []   # (locus, tier, document)
    for path in files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        except OSError as exc:
            probe_errors.append(f"{path}: {exc}")
            continue
        file_documents.append((str(path), locus_tier(path), document))

    # --- matching --------------------------------------------------------- #
    findings = []
    for contract in contracts:
        if contract.family == "schema":
            findings.append(_finding_for_schema(
                contract, checker, runtime_events, file_documents, probe_errors
            ))
        else:
            findings.append(_finding_for_vocabulary(
                contract, runtime_events, vocab_error
            ))

    findings.sort(key=lambda f: (STATES.index(f["state"]), f["family"], f["contract"]))
    return {
        "event_types": _event_type_census(runtime_events, auditctl_source),
        "workspace": str(workspace),
        "roots": [str(r) for r in roots],
        "corpus": {
            "audit_stores": [str(s) for s in stores],
            "shards": len(shards),
            "runtime_events": len(runtime_events),
            "json_files": len(file_documents),
        },
        "auditctl_validation_source": str(auditctl_source) if auditctl_source else None,
        "probe_errors": probe_errors,
        "findings": findings,
        "summary": {state: sum(1 for f in findings if f["state"] == state) for state in STATES},
    }


#: The one part of the inventory that could not be derived, and the reason.
#:
#: The brief asked for "the event-type vocabularies auditctl validates". There are
#: none. ``validate_event_object`` accepts any non-empty ``type`` string;
#: ``validate_dispatch_exit_metadata`` branches on the literal ``"dispatch.exit"``
#: inside a function body, which constrains that type's *metadata* and does not
#: enumerate the types. Every event type in this workspace -- ``workflow.session``
#: included, the single most-written type on record -- is a free-form string passed
#: to ``auditctl add``, spelled in a shell hook.
#:
#: So the census below is deliberately the *inverse* measurement, and it is reported
#: rather than hidden: not "which declared type has no producer" but "which producer
#: has no declared type". Hardcoding a plausible list here would have manufactured
#: exactly the artifact this check exists to find.
NO_DECLARED_EVENT_TYPE_VOCABULARY = (
    "auditctl declares no event-type vocabulary: validate_event_object accepts any "
    "non-empty type string, and validate_dispatch_exit_metadata branches on one "
    "literal rather than enumerating a set. Every type below is therefore a producer "
    "with no contract -- the mirror of the defect this check was built for."
)


def _event_type_census(runtime_events, auditctl_source):
    """Count the event types actually written, since none are declared anywhere.

    Each type carries its spread as well as its count, because a count alone reads a
    fixture as a producer. Every ``dispatch.*`` event in the agentops store is one
    ``task_id`` -- ``EX-1``, the packet fixture in ``tests/test_hybrid_dispatch.py`` --
    written on one day from one source. As "24 reviewed, 11 preflight-rejected" that
    looks like a working dispatch cycle. With its spread beside it, it does not.
    """
    counts = {}
    by_type = {}
    for _, event in runtime_events:
        event_type = event.get("type") or event.get("event_type")
        if isinstance(event_type, str) and event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
            by_type.setdefault(event_type, []).append(event)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "declared_vocabulary": None,
        "declaration_note": NO_DECLARED_EVENT_TYPE_VOCABULARY
        if auditctl_source
        else "auditctl source not found; the declaration could not be checked either way",
        "observed": dict(ordered),
        "spread": {name: runtime_concentration(by_type[name]) for name, _ in ordered},
    }


def _finding_for_schema(contract, checker, runtime_events, file_documents, probe_errors):
    base = {
        "contract": contract.contract_id,
        "family": "schema",
        "source": str(contract.source),
        "discriminators": contract.discriminators,
    }
    if contract.undetermined:
        return {**base, "state": "cannot-determine", "reason": contract.undetermined,
                "instances": [], "tiers": {}}

    instances = []
    matched_events = []
    for locus, event in runtime_events:
        for document in candidate_documents(event):
            how = matches(document, contract, checker)
            if how:
                instances.append({"locus": locus, "tier": "runtime", "via": how})
                matched_events.append(event)
                break
    for locus, tier, document in file_documents:
        how = matches(document, contract, checker)
        if how:
            instances.append({"locus": locus, "tier": tier, "via": how})

    tiers = {tier: sum(1 for i in instances if i["tier"] == tier) for tier in LOCUS_TIERS}
    tiers = {k: v for k, v in tiers.items() if v}
    if any(tier in PRODUCING_TIERS for tier in tiers):
        state = "produced"
    elif instances:
        state = "examples-only"
    else:
        state = "no-instance"
    return {**base, "state": state, "instances": _condense(instances), "tiers": tiers,
            "concentration": runtime_concentration(matched_events)}


def _finding_for_vocabulary(contract, runtime_events, vocab_error):
    base = {
        "contract": contract.contract_id,
        "family": "vocabulary",
        "source": str(contract.source),
        "discriminators": ["token-occurrence"],
        "members": list(contract.members),
        "aliases": list(getattr(contract, "aliases", ())),
    }
    if vocab_error:
        return {**base, "state": "cannot-determine", "reason": vocab_error,
                "instances": [], "tiers": {}, "observed": [], "unobserved": list(contract.members)}

    observed = {}
    matched_events = []
    for locus, event in runtime_events:
        hits = vocabulary_hits(event, contract.members)
        if hits:
            matched_events.append(event)
        for token in hits:
            observed.setdefault(token, set()).add(locus)

    instances = [
        {"locus": sorted(loci)[0], "tier": "runtime", "via": token}
        for token, loci in sorted(observed.items())
    ]
    unobserved = [m for m in contract.members if m not in observed]
    state = "produced" if observed else "no-instance"
    return {
        **base,
        "state": state,
        "instances": instances,
        "tiers": {"runtime": len(instances)} if instances else {},
        "observed": sorted(observed),
        "unobserved": unobserved,
        "concentration": runtime_concentration(matched_events),
    }


def _condense(instances, limit=5):
    """Keep every distinct locus, but cap the list so one busy store cannot bury the rest."""
    by_locus = {}
    for instance in instances:
        key = (instance["locus"], instance["tier"], instance["via"])
        by_locus[key] = by_locus.get(key, 0) + 1
    condensed = [
        {"locus": locus, "tier": tier, "via": via, "count": count}
        for (locus, tier, via), count in sorted(by_locus.items())
    ]
    if len(condensed) > limit:
        head = condensed[:limit]
        head.append({"locus": f"... and {len(condensed) - limit} more loci",
                     "tier": "", "via": "", "count": 0})
        return head
    return condensed


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_HEADINGS = {
    "no-instance": "DECLARED, NO INSTANCE ANYWHERE",
    "examples-only": "EXAMPLES ONLY -- the shape of a producer, without one",
    "produced": "PRODUCED IN ANGER",
    "cannot-determine": "CANNOT DETERMINE -- the probe did not run, which is not a negative result",
}


def render(result):
    lines = []
    corpus = result["corpus"]
    lines.append(f"contract producers -- {result['workspace']}")
    lines.append(
        f"  corpus: {len(corpus['audit_stores'])} audit store(s), {corpus['shards']} shard(s), "
        f"{corpus['runtime_events']} event record(s), {corpus['json_files']} JSON file(s)"
    )
    lines.append(
        "  (an event indexed in a store and appended to a shard is two records here; "
        "loci are counted, not distinct events)"
    )
    lines.append(f"  auditctl vocabularies from: {result['auditctl_validation_source'] or 'NOT FOUND'}")
    summary = result["summary"]
    lines.append("  " + "  ".join(f"{state}={summary[state]}" for state in STATES))
    for error in result["probe_errors"]:
        lines.append(f"  ! probe error: {error}")
    lines.append("")

    for state in STATES:
        findings = [f for f in result["findings"] if f["state"] == state]
        if not findings:
            continue
        lines.append(f"{_HEADINGS[state]}  ({len(findings)})")
        for finding in findings:
            lines.append(f"  {finding['contract']}  [{finding['family']}]  {finding['source']}")
            if finding.get("reason"):
                lines.append(f"      reason: {finding['reason']}")
            if finding["family"] == "vocabulary" and state != "cannot-determine":
                observed = finding["observed"]
                unobserved = finding["unobserved"]
                lines.append(
                    f"      {len(observed)}/{len(observed) + len(unobserved)} tokens observed"
                )
                if unobserved:
                    lines.append(f"      never observed: {', '.join(unobserved)}")
            spread = finding.get("concentration")
            if spread:
                detail = (
                    f"{spread['events']} event(s), "
                    f"{len(spread['sources'])} source(s), {len(spread['days'])} day(s)"
                )
                if spread["subjects"]:
                    detail += f", subject(s): {', '.join(spread['subjects'][:3])}"
                lines.append(f"      spread: {detail}")
                if spread["narrow"]:
                    lines.append(
                        "      NARROW -- one source, one day, one subject. Consistent with a "
                        "fixture or a single rehearsal as much as with a working producer; "
                        "this check does not guess which."
                    )
            for instance in finding["instances"][:5]:
                if not instance.get("tier"):
                    lines.append(f"      {instance['locus']}")
                    continue
                count = instance.get("count")
                suffix = f" x{count}" if count and count > 1 else ""
                lines.append(
                    f"      {instance['tier']}: {instance['locus']} (via {instance['via']}){suffix}"
                )
        lines.append("")

    census = result["event_types"]
    lines.append(f"EVENT TYPES OBSERVED  ({len(census['observed'])})")
    lines.append(f"  {census['declaration_note']}")
    spreads = census.get("spread") or {}
    for event_type, count in census["observed"].items():
        spread = spreads.get(event_type)
        note = ""
        if spread:
            note = (
                f"   [{len(spread['sources'])} src, {len(spread['days'])} day, "
                f"{len(spread['subjects'])} subj]"
            )
            if spread["narrow"]:
                subject = spread["subjects"][0] if spread["subjects"] else "one subject"
                note = f"   [NARROW: 1 src, 1 day, {subject}]"
        lines.append(f"      {count:>6}  {event_type}{note}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", default=".", help="workspace root (default: CWD)")
    parser.add_argument("--root", action="append", default=[],
                        help="extra search root for instances; repeatable")
    parser.add_argument("--auditctl-source",
                        help="path to auditctl/validation.py (default: derived)")
    parser.add_argument("--json", action="store_true", help="emit the findings as JSON")
    parser.add_argument("--fail-on", default="",
                        help="comma-separated states that make this exit 1; default none, "
                             "because this is an instrument and not a bar (see module docstring)")
    args = parser.parse_args(argv)

    fail_on = {s.strip() for s in args.fail_on.split(",") if s.strip()}
    unknown = fail_on - set(STATES)
    if unknown:
        print(f"unknown state(s) for --fail-on: {', '.join(sorted(unknown))}; "
              f"known: {', '.join(STATES)}", file=sys.stderr)
        return 2

    workspace = Path(args.workspace)
    if not workspace.is_dir():
        print(f"not a directory: {workspace}", file=sys.stderr)
        return 2

    source = Path(args.auditctl_source) if args.auditctl_source else None
    result = check(workspace, extra_roots=args.root, auditctl_source=source)

    print(json.dumps(result, indent=2) if args.json else render(result))

    if not fail_on:
        return 0
    hit = [f["contract"] for f in result["findings"] if f["state"] in fail_on]
    if hit:
        print(f"\n{len(hit)} contract(s) in a state named by --fail-on: {', '.join(hit)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
