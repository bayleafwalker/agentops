"""Append-only, retrospective interpretation governance over shared Store events.

This module records immutable result/interpretation revisions, attestations, and
advisory reconciliation intents. It never changes task state, gates execution,
or mints owner authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict, deque
from typing import Any, Mapping


SCHEMA_VERSION = "interpretation-governance/v1"
DISPOSITIONS = {"pending", "acknowledged", "ratified", "disputed", "superseded"}
REVISION_EVENTS = {
    "result": "governance.result_revision_recorded",
    "interpretation": "governance.interpretation_revision_recorded",
}
ATTESTATION_EVENT = "governance.disposition_attested"
INTENT_EVENT = "governance.reconciliation_intent_recorded"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _id(value: Any, name: str) -> str:
    value = _text(value, name)
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"{name} has an invalid identifier")
    return value


def _digest(value: Any, name: str) -> str:
    value = _text(value, name)
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _json_value(value: Any, name: str) -> Any:
    try:
        return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite JSON data") from exc


def _refs(values: Any, name: str) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be a list of revision references")
    refs = [_text(value, name) for value in values]
    if len(set(refs)) != len(refs):
        raise ValueError(f"{name} must not contain duplicates")
    return sorted(refs)


class InterpretationGovernance:
    """Event-sourced retrospective records layered over a shared execution Store."""

    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def revision_ref(kind: str, revision_id: str) -> str:
        if kind not in REVISION_EVENTS:
            raise ValueError("revision kind must be result or interpretation")
        return f"{kind}:{_id(revision_id, 'revision_id')}"

    def revisions(self) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        kind_for_event = {event_kind: kind for kind, event_kind in REVISION_EVENTS.items()}
        for event in self.store.events():
            event_kind = event.get("kind")
            if event_kind not in kind_for_event:
                continue
            expected_kind = kind_for_event[event_kind]
            record = event.get("revision")
            if (event.get("schema_version") != SCHEMA_VERSION or not isinstance(record, dict)
                    or record.get("schema_version") != SCHEMA_VERSION):
                raise ValueError(f"invalid revision event schema: {event_kind}")
            revision_ref = record.get("revision_ref")
            if (record.get("kind") != expected_kind
                    or not isinstance(revision_ref, str)
                    or not revision_ref.startswith(expected_kind + ":")):
                raise ValueError(f"revision kind/event mismatch: {event_kind}")
            self.revision_ref(expected_kind, revision_ref.split(":", 1)[1])
            subject_ref = _text(record.get("subject_ref"), "subject_ref")
            if event.get("task") != subject_ref:
                raise ValueError(f"revision subject/event mismatch: {revision_ref}")
            _text(record.get("source_ref"), "source_ref")
            _digest(record.get("source_sha256"), "source_sha256")
            if not isinstance(record.get("provenance"), dict):
                raise ValueError(f"revision provenance missing: {revision_ref}")
            record_dependencies = record.get("depends_on")
            if _refs(record_dependencies, "depends_on") != record_dependencies:
                raise ValueError(f"revision dependencies are not canonical: {revision_ref}")
            if _refs(record.get("evidence_refs"), "evidence_refs") != record.get("evidence_refs"):
                raise ValueError(f"revision evidence references are not canonical: {revision_ref}")
            if record.get("kind") == "interpretation":
                if record.get("result_revision_ref") not in record_dependencies:
                    raise ValueError(f"interpretation lacks its result dependency: {revision_ref}")
                _text(record.get("conclusion"), "conclusion")
            previous = records.get(revision_ref)
            if previous is not None and previous != record:
                raise ValueError(f"immutable revision conflict: {revision_ref}")
            records[revision_ref] = record
        for revision_ref, record in records.items():
            missing = [dependency for dependency in record["depends_on"] if dependency not in records]
            if missing:
                raise ValueError(f"revision has unknown dependency: {revision_ref}")
            if record["kind"] == "interpretation":
                result = records[record["result_revision_ref"]]
                if result["kind"] != "result":
                    raise ValueError(f"interpretation points to non-result: {revision_ref}")
        return records

    def _validate_dependencies(self, dependencies: Any, *, include: str | None = None) -> list[str]:
        refs = _refs(dependencies, "depends_on")
        if include:
            refs = sorted(set(refs) | {include})
        known = self.revisions()
        missing = [ref for ref in refs if ref not in known]
        if missing:
            raise ValueError(f"unknown dependency revision(s): {', '.join(missing)}")
        return refs

    def _append_revision(self, kind: str, revision: dict[str, Any]) -> dict[str, Any]:
        self.revisions()
        event_kind = REVISION_EVENTS[kind]
        for event in self.store.events():
            existing = event.get("revision", {})
            if (event.get("kind") == event_kind
                    and existing.get("revision_ref") == revision["revision_ref"]):
                if event["revision"] == revision:
                    return dict(revision)
                raise ValueError(f"immutable revision conflict: {revision['revision_ref']}")
        self.store.event(event_kind, revision["subject_ref"], schema_version=SCHEMA_VERSION,
                         revision=revision)
        return dict(revision)

    def record_result_revision(
        self,
        revision_id: str,
        *,
        subject_ref: str,
        source_ref: str,
        source_sha256: str,
        evidence_refs: Any = (),
        depends_on: Any = (),
        provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Record one immutable result reference and its source/dependency provenance."""
        if not isinstance(provenance, Mapping):
            raise ValueError("provenance must be a JSON object")
        ref = self.revision_ref("result", revision_id)
        revision = dict(schema_version=SCHEMA_VERSION, kind="result", revision_ref=ref,
                        subject_ref=_text(subject_ref, "subject_ref"),
                        source_ref=_text(source_ref, "source_ref"),
                        source_sha256=_digest(source_sha256, "source_sha256"),
                        evidence_refs=_refs(evidence_refs, "evidence_refs"),
                        depends_on=self._validate_dependencies(depends_on),
                        provenance=_json_value(dict(provenance), "provenance"))
        return self._append_revision("result", revision)

    def record_interpretation_revision(
        self,
        revision_id: str,
        *,
        subject_ref: str,
        result_revision_ref: str,
        conclusion: str,
        source_ref: str,
        source_sha256: str,
        evidence_refs: Any = (),
        depends_on: Any = (),
        provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Record a conclusion bound to an exact immutable result revision."""
        if not isinstance(provenance, Mapping):
            raise ValueError("provenance must be a JSON object")
        result_revision_ref = _text(result_revision_ref, "result_revision_ref")
        known = self.revisions()
        if result_revision_ref not in known or known[result_revision_ref].get("kind") != "result":
            raise ValueError("result_revision_ref must reference a recorded result revision")
        ref = self.revision_ref("interpretation", revision_id)
        revision = dict(schema_version=SCHEMA_VERSION, kind="interpretation", revision_ref=ref,
                        subject_ref=_text(subject_ref, "subject_ref"),
                        result_revision_ref=result_revision_ref,
                        conclusion=_text(conclusion, "conclusion"),
                        source_ref=_text(source_ref, "source_ref"),
                        source_sha256=_digest(source_sha256, "source_sha256"),
                        evidence_refs=_refs(evidence_refs, "evidence_refs"),
                        depends_on=self._validate_dependencies(depends_on, include=result_revision_ref),
                        provenance=_json_value(dict(provenance), "provenance"))
        return self._append_revision("interpretation", revision)

    def attest_disposition(
        self,
        attestation_id: str,
        *,
        subject_ref: str,
        disposition: str,
        actor_ref: str,
        evidence_refs: Any = (),
        note: str | None = None,
        superseded_by_ref: str | None = None,
    ) -> dict[str, Any]:
        """Append a disposition observation; disputes create a non-blocking intent."""
        subject_ref = _text(subject_ref, "subject_ref")
        revisions = self.revisions()
        if subject_ref not in revisions:
            raise ValueError("subject_ref must identify a recorded revision")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"unsupported disposition: {disposition}")
        if disposition == "superseded":
            superseded_by_ref = _text(superseded_by_ref, "superseded_by_ref")
            if superseded_by_ref not in revisions:
                raise ValueError("superseded_by_ref must identify a recorded revision")
            if revisions[superseded_by_ref]["kind"] != revisions[subject_ref]["kind"]:
                raise ValueError("superseded_by_ref must have the same revision kind")
            if superseded_by_ref == subject_ref:
                raise ValueError("a revision cannot supersede itself")
        elif superseded_by_ref is not None:
            raise ValueError("superseded_by_ref is only valid for a superseded disposition")
        attestation = dict(schema_version=SCHEMA_VERSION,
                           attestation_id=_id(attestation_id, "attestation_id"),
                           subject_ref=subject_ref, disposition=disposition,
                           actor_ref=_text(actor_ref, "actor_ref"),
                           evidence_refs=_refs(evidence_refs, "evidence_refs"),
                           note=None if note is None else _text(note, "note"),
                           superseded_by_ref=superseded_by_ref)
        existing_attestations = self.attestations()
        existing_attestation = next((item for item in existing_attestations
                                     if item["attestation_id"] == attestation["attestation_id"]), None)
        if existing_attestation:
            if existing_attestation != attestation:
                raise ValueError(f"immutable attestation conflict: {attestation['attestation_id']}")
            prior_event = next(event for event in self.store.events()
                               if event.get("kind") == ATTESTATION_EVENT
                               and event.get("attestation", {}).get("attestation_id") == attestation["attestation_id"])
            result = dict(attestation)
            existing_intent = self._intent_for(prior_event.get("reconciliation_intent_id"))
            if existing_intent:
                result["reconciliation_intent"] = existing_intent
            return result

        intent = (self._build_reconciliation_intent(subject_ref, attestation["attestation_id"])
                  if disposition == "disputed" else None)
        intent_id = intent["intent_id"] if intent else None
        subject_task = revisions[subject_ref]["subject_ref"]
        with self.store.db:
            if intent and not self._intent_for(intent_id):
                self.store.db.execute(
                    "INSERT INTO events(at,kind,task,body) VALUES (?,?,?,?)",
                    (time.time(), INTENT_EVENT, subject_task,
                     json.dumps(dict(schema_version=SCHEMA_VERSION, intent=intent), sort_keys=True)))
            self.store.db.execute(
                "INSERT INTO events(at,kind,task,body) VALUES (?,?,?,?)",
                (time.time(), ATTESTATION_EVENT, subject_task,
                 json.dumps(dict(schema_version=SCHEMA_VERSION, attestation=attestation,
                                 reconciliation_intent_id=intent_id), sort_keys=True)))
        result = dict(attestation)
        if intent:
            result["reconciliation_intent"] = intent
        return result

    def attestations(self, subject_ref: str | None = None) -> list[dict[str, Any]]:
        revisions = self.revisions()
        attestations: dict[str, tuple[dict[str, Any], str | None]] = {}
        for event in self.store.events():
            if event.get("kind") != ATTESTATION_EVENT:
                continue
            attestation = event.get("attestation")
            intent_id = event.get("reconciliation_intent_id")
            if (event.get("schema_version") != SCHEMA_VERSION or not isinstance(attestation, dict)
                    or attestation.get("schema_version") != SCHEMA_VERSION):
                raise ValueError("invalid disposition attestation schema")
            attestation_id = _id(attestation.get("attestation_id"), "attestation_id")
            source_ref = _text(attestation.get("subject_ref"), "subject_ref")
            if source_ref not in revisions:
                raise ValueError(f"attestation references unknown revision: {source_ref}")
            if event.get("task") != revisions[source_ref]["subject_ref"]:
                raise ValueError(f"attestation subject/event mismatch: {attestation_id}")
            disposition = attestation.get("disposition")
            if disposition not in DISPOSITIONS:
                raise ValueError(f"unsupported disposition in event: {attestation_id}")
            _text(attestation.get("actor_ref"), "actor_ref")
            if _refs(attestation.get("evidence_refs"), "evidence_refs") != attestation.get("evidence_refs"):
                raise ValueError(f"attestation evidence references are not canonical: {attestation_id}")
            if disposition == "superseded":
                target = attestation.get("superseded_by_ref")
                if (target not in revisions
                        or revisions[target]["kind"] != revisions[source_ref]["kind"]
                        or target == source_ref):
                    raise ValueError(f"invalid supersession link: {attestation_id}")
            elif attestation.get("superseded_by_ref") is not None:
                raise ValueError(f"unexpected supersession link: {attestation_id}")
            if (disposition == "disputed") != bool(intent_id):
                raise ValueError(f"dispute intent binding mismatch: {attestation_id}")
            if intent_id and not self._intent_for(intent_id):
                raise ValueError(f"dispute intent missing: {attestation_id}")
            prior = attestations.get(attestation_id)
            pair = (attestation, intent_id)
            if prior is not None and prior != pair:
                raise ValueError(f"immutable attestation conflict: {attestation_id}")
            attestations[attestation_id] = pair
        return [attestation for attestation, _ in attestations.values()
                if subject_ref is None or attestation["subject_ref"] == subject_ref]

    def reconciliation_intents(self) -> list[dict[str, Any]]:
        revisions = self.revisions()
        intents: dict[str, dict[str, Any]] = {}
        for event in self.store.events():
            if event.get("kind") != INTENT_EVENT:
                continue
            intent = event.get("intent")
            if (event.get("schema_version") != SCHEMA_VERSION or not isinstance(intent, dict)
                    or intent.get("schema_version") != SCHEMA_VERSION
                    or intent.get("advisory_only") is not True):
                raise ValueError("invalid reconciliation intent schema")
            intent_id = _id(intent.get("intent_id"), "intent_id")
            disputed_ref = _text(intent.get("disputed_revision_ref"), "disputed_revision_ref")
            if disputed_ref not in revisions:
                raise ValueError(f"intent references unknown revision: {disputed_ref}")
            if event.get("task") != revisions[disputed_ref]["subject_ref"]:
                raise ValueError(f"intent subject/event mismatch: {intent_id}")
            prior = intents.get(intent_id)
            if prior is not None and prior != intent:
                raise ValueError(f"immutable reconciliation intent conflict: {intent_id}")
            intents[intent_id] = intent
        return list(intents.values())

    def downstream_impacts(self, revision_ref: str) -> dict[str, Any]:
        """Project the current dependent revision closure, including later additions."""
        revision_ref = _text(revision_ref, "revision_ref")
        revisions = self.revisions()
        if revision_ref not in revisions:
            raise ValueError("revision_ref must identify a recorded revision")
        return self._impact_snapshot(revision_ref, revisions)

    def _intent_for(self, intent_id: str | None) -> dict[str, Any] | None:
        if not intent_id:
            return None
        return next((intent for intent in self.reconciliation_intents()
                     if intent.get("intent_id") == intent_id), None)

    def _build_reconciliation_intent(self, source_ref: str, attestation_id: str) -> dict[str, Any] | None:
        revisions = self.revisions()
        if source_ref not in revisions:
            raise ValueError("disputed subject revision disappeared")
        impact = self._impact_snapshot(source_ref, revisions)
        affected_refs = impact["affected_revision_refs"]
        identity = dict(source_ref=source_ref, affected_revision_refs=affected_refs)
        intent_id = "reconcile-" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        existing = self._intent_for(intent_id)
        if existing:
            return existing
        return dict(schema_version=SCHEMA_VERSION, intent_id=intent_id,
                    trigger_attestation_id=_id(attestation_id, "attestation_id"),
                    disputed_revision_ref=source_ref,
                    affected_revision_refs=affected_refs,
                    reevaluate_interpretation_refs=impact["reevaluate_interpretation_refs"],
                    preserved_evidence=impact["preserved_evidence"],
                    advisory_only=True)

    @staticmethod
    def _impact_snapshot(source_ref: str, revisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        reverse: dict[str, set[str]] = defaultdict(set)
        for revision_ref, revision in revisions.items():
            for dependency in revision["depends_on"]:
                reverse[dependency].add(revision_ref)
        affected = {source_ref}
        pending = deque([source_ref])
        while pending:
            dependency = pending.popleft()
            for dependent in reverse.get(dependency, ()):
                if dependent not in affected:
                    affected.add(dependent)
                    pending.append(dependent)
        affected_refs = sorted(affected)
        reevaluate = [ref for ref in affected_refs if revisions[ref]["kind"] == "interpretation"]
        preserved = [dict(revision_ref=ref, source_ref=revisions[ref]["source_ref"],
                          source_sha256=revisions[ref]["source_sha256"],
                          evidence_refs=revisions[ref]["evidence_refs"])
                     for ref in affected_refs]
        return dict(revision_ref=source_ref, affected_revision_refs=affected_refs,
                    reevaluate_interpretation_refs=reevaluate,
                    preserved_evidence=preserved)
