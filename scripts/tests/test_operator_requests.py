"""Focused tests for the local operator-request transport boundary."""
from __future__ import annotations

import asyncio
import sys
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import operator_requests as requests


def complete_packet():
    return {
        "schema": "operator-request/v1",
        "kind": "perform",
        "required_outcome": "The operator runs the checked migration command.",
        "reason": "The native session has no route to the approved operator host.",
        "execution": {
            "host": "ops.example.invalid",
            "directory": "/srv/service",
            "intended_identity": "deployment-operator",
            "target": "staging/service-a",
            "inputs": [{"name": "operator session", "acquire_from": "approved terminal login"}],
        },
        "procedure": {
            "version": "1.0.0",
            "steps": [{
                "step_id": "check",
                "instruction": "Run the documented read-only preflight command.",
                "expected_result": "The target reports the expected release digest.",
                "preconditions": ["The operator is on ops.example.invalid."],
                "verification": "Compare the returned digest with the pinned release.",
                "partial_progress": "Record the observed step before proceeding.",
                "recovery": "Stop and refresh this request if the digest differs.",
            }],
        },
        "blocker": {
            "condition": "A checked operator-only preflight remains outstanding.",
            "checked_at": "2026-10-24T10:00:00Z",
            "fresh_until": "2026-10-24T11:00:00Z",
            "source_revisions": [{"source": "release", "revision": "sha256:abc"}],
        },
    }


class RequestContentBoundaryTests(unittest.TestCase):
    def test_refuses_sensitive_aliases_recursively(self) -> None:
        for payload in (
            {"conversation_transcript": "private words"},
            {"nested": [{"apiKey": "not-a-real-key"}]},
            {"claimed_authority": "can approve"},
            {"session": {"credential_reference": "file:secret"}},
            {"context": {"raw_transcript": "private words"}},
            {"identity": "claimed-user"},
            {"authority": "can-approve"},
        ):
            with self.subTest(payload=payload), self.assertRaises(requests.RequestClientError) as caught:
                requests._check_content(payload)
            self.assertEqual(caught.exception.code, "sensitive-content-refused")

    def test_sensitive_content_is_refused_before_owner_initialization(self) -> None:
        owner = requests.VuoroRequestOwner(Path("/missing/profile"))
        with self.assertRaises(requests.RequestClientError) as caught:
            owner.invoke("publish", "repo", {"packet": {"private_key": "x"}})
        self.assertEqual(caught.exception.code, "sensitive-content-refused")
        self.assertIsNone(owner._client)

    def test_mcp_returns_bounded_error_without_calling_owner(self) -> None:
        owner = Mock()
        server = requests.MCPServer(lambda: owner)
        reply = server.call_tool("report-performed", {
            "repo_id": "repo",
            "arguments": {"report": {"rawTranscript": "private words"}},
        })
        self.assertTrue(reply["isError"])
        self.assertEqual(reply["structuredContent"]["code"], "sensitive-content-refused")
        owner.invoke.assert_not_called()

    def test_complete_publish_packet_with_intended_identity_passes_adapter_and_mcp(self):
        request_id = "req_01JZZZZZZZZZZZZZZZZZZZZZZZ"
        arguments = {
            "request_id": request_id,
            "packet": complete_packet(),
            "dependants": [{"work_item_id": 42, "session_id": "session-1"}],
            "idempotency_key": "publish-req-01JZZZZZZZZZZZZZZZZZZZZZZZ",
        }
        owner = requests.VuoroRequestOwner(Path("/unused/profile"))
        loop = asyncio.new_event_loop()
        owner._loop = loop
        calls = []

        class Client:
            async def invoke(self, operation, payload, *, repo_id):
                calls.append((operation, payload, repo_id))
                return {"request_id": request_id, "revision": 1, "replayed": False}

        owner._client = Client()
        owner._operations = {requests.OPERATIONS["publish"]}
        try:
            result = owner.invoke("publish", "sprintctl", arguments)
        finally:
            owner.close()
        self.assertEqual(result, {"request_id": request_id, "revision": 1, "replayed": False})
        self.assertEqual(calls, [(requests.OPERATIONS["publish"], arguments, "sprintctl")])

        forwarded = []
        server = requests.MCPServer(lambda: type("Owner", (), {
            "invoke": lambda _self, suffix, repo, payload: (
                forwarded.append((suffix, repo, payload))
                or {"request_id": request_id, "revision": 1, "replayed": False}
            ),
        })())
        reply = server.call_tool("publish", {"repo_id": "sprintctl", "arguments": arguments})
        self.assertFalse(reply["isError"])
        self.assertEqual(forwarded, [("publish", "sprintctl", arguments)])

    def test_strict_json_rejects_duplicate_nonfinite_overdeep_and_oversize(self):
        overdeep = "{" * (requests.MAX_REQUEST_JSON_DEPTH + 1) + "0" + "}" * (requests.MAX_REQUEST_JSON_DEPTH + 1)
        for raw in (
            '{"x":1,"x":2}',
            '{"x":NaN}',
            '{"x":1e9999}',
            overdeep,
            " " * (requests.MAX_REQUEST_JSON_BYTES + 1),
        ):
            with self.subTest(length=len(raw)), self.assertRaises(requests.RequestClientError) as caught:
                requests._strict_json(raw)
            self.assertEqual(caught.exception.code, "invalid-json")

    def test_mcp_strict_parse_refusal_precedes_owner_initialization(self):
        overdeep = "{" * (requests.MAX_REQUEST_JSON_DEPTH + 1) + "0" + "}" * (requests.MAX_REQUEST_JSON_DEPTH + 1)
        invalid = (
            '{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/list"}',
            '{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":NaN}}',
            '{"jsonrpc":"2.0","id":1,"method":"ping","params":' + overdeep + "}",
            " " * (requests.MAX_REQUEST_JSON_BYTES + 2),
        )
        owner_factory = Mock(side_effect=AssertionError("owner must remain unopened"))
        output = StringIO()
        requests.serve(requests.MCPServer(owner_factory), StringIO("\n".join(invalid) + "\n"), output)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(replies), len(invalid))
        self.assertTrue(all(reply["error"]["code"] == -32700 for reply in replies))
        owner_factory.assert_not_called()

    def test_cli_strict_arguments_refuse_before_owner_initialization(self):
        overdeep = "{" * (requests.MAX_REQUEST_JSON_DEPTH + 1) + "0" + "}" * (requests.MAX_REQUEST_JSON_DEPTH + 1)
        invalid = (
            '{"request_id":"one","request_id":"two"}',
            '{"request_id":NaN}',
            '{"request_id":1e9999}',
            overdeep,
            " " * (requests.MAX_REQUEST_JSON_BYTES + 1),
        )
        for raw in invalid:
            with self.subTest(length=len(raw)), patch.object(requests.sys, "stdin", StringIO(raw)), \
                    patch.object(requests.sys, "stderr", StringIO()), \
                    patch.object(requests.VuoroRequestOwner, "_ensure") as ensure:
                result = requests.main([
                    "invoke", "publish", "--repo", "sprintctl", "--arguments", "-",
                    "--profile", "/unused/profile",
                ])
                self.assertEqual(result, 2)
                ensure.assert_not_called()

    def test_owner_refusal_for_stale_or_revoked_access_is_not_rewritten(self) -> None:
        class Owner:
            def invoke(self, suffix, repo_id, arguments):
                raise requests.RequestClientError("request-stale")

        reply = requests.MCPServer(Owner).call_tool("operator_request_attest".replace("operator_request_", "attest"), {
            "repo_id": "repo", "arguments": {"request_id": "req_example"},
        })
        self.assertTrue(reply["isError"])
        self.assertEqual(reply["structuredContent"]["code"], "request-stale")


class LocalRequestOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "private-outbox"
        self.store = requests.LocalRequestOutbox(self.directory)
        self.repo = "sprintctl"
        self.arguments = {
            "request_id": "req_01JZZZZZZZZZZZZZZZZZZZZZZZ",
            "idempotency_key": "publish-req-01JZZZZZZZZZZZZZZZZZZZZZZZ",
            "packet": complete_packet(),
            "dependants": [{"work_item_id": 42, "session_id": "session-1"}],
        }

    def snapshot(self, **overrides):
        value = {
            "request_id": self.arguments["request_id"], "revision": 1, "state": "open",
            "freshness": "current", "packet": self.arguments["packet"],
            "dependants": [{
                "work_item_id": 42, "session_id": "session-1", "runtime_id": None,
                "work_revision": "work-r1", "current_work_revision": "work-r1",
                "source_changed": False, "state": "active", "attached_at": "2026-10-24T00:00:00Z",
                "withdrawn_at": None,
            }],
            "created_at": "2026-10-24T00:00:00Z", "updated_at": "2026-10-24T00:00:00Z",
        }
        return {**value, **overrides}

    def test_stage_is_non_authoritative_and_duplicate_preserves_identity(self):
        first = self.store.stage_publish(self.repo, self.arguments)
        second = self.store.stage_publish(self.repo, self.arguments)
        self.assertEqual(first["state"], "pending")
        self.assertEqual(first, second)
        self.assertEqual(self.store.list_entries(), [{
            "request_id": self.arguments["request_id"], "repo_id": self.repo, "state": "pending",
        }])

    def test_conflicting_request_id_is_refused(self):
        self.store.stage_publish(self.repo, self.arguments)
        changed = {**self.arguments, "request": {"summary": "different"}}
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.stage_publish(self.repo, changed)
        self.assertEqual(caught.exception.code, "outbox-identity-conflict")

    def test_sensitive_content_is_rejected_before_directory_creation(self):
        bad = {**self.arguments, "request": {"rawTranscript": "private"}}
        with self.assertRaises(requests.RequestClientError):
            self.store.stage_publish(self.repo, bad)
        self.assertFalse(self.directory.exists())

    def test_failed_delivery_remains_pending_then_acknowledges_same_payload(self):
        self.store.stage_publish(self.repo, self.arguments)
        observed = []
        def unavailable(suffix, repo, payload):
            observed.append((suffix, repo, payload))
            raise requests.RequestClientError("owner-transport-failed")
        result = self.store.deliver(unavailable)
        self.assertEqual(result[0]["state"], "uncertain")
        self.assertEqual(self.store.list_entries()[0]["state"], "uncertain")

        self.store.reconcile(lambda suffix, repo, args: (_ for _ in ()).throw(
            requests.RequestClientError("not-found")
        ))
        self.assertEqual(self.store.list_entries()[0]["state"], "pending")

        def acknowledged(suffix, repo, payload):
            observed.append((suffix, repo, payload))
            return {"request_id": payload["request_id"], "revision": 1, "replayed": True}
        result = self.store.deliver(acknowledged)
        self.assertEqual(result, [{"request_id": self.arguments["request_id"], "state": "acknowledged"}])
        self.assertEqual(self.store.list_entries()[0]["state"], "acknowledged")
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0][0], "publish")
        self.assertEqual(observed[0][2]["idempotency_key"], self.arguments["idempotency_key"])

    def test_symlink_and_hardlink_storage_are_refused(self):
        self.store.stage_publish(self.repo, self.arguments)
        data = self.directory / "outbox.json"
        linked = self.directory / "linked.json"
        os.link(data, linked)
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-refused")

        data.unlink()
        target = self.directory / "target.json"
        target.write_text('{"schema":"operator-request-outbox/v1","entries":[]}')
        data.symlink_to(target)
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-refused")

    def test_capacity_is_bounded(self):
        self.store.MAX_ENTRIES = 1
        self.store.stage_publish(self.repo, self.arguments)
        second = {**self.arguments, "request_id": "req_second", "idempotency_key": "publish-second"}
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.stage_publish(self.repo, second)
        self.assertEqual(caught.exception.code, "outbox-capacity-exceeded")

    def test_malformed_owner_acknowledgements_require_reconciliation(self):
        responses = (
            {},
            {"request_id": "req_wrong", "revision": 1, "replayed": False},
            {"request_id": self.arguments["request_id"], "replayed": False},
            {"request_id": self.arguments["request_id"], "revision": 0, "replayed": False},
            {"request_id": self.arguments["request_id"], "revision": True, "replayed": False},
            {"request_id": self.arguments["request_id"], "revision": 1, "replayed": "true"},
            None,
        )
        for index, response in enumerate(responses):
            with self.subTest(response=response):
                store = requests.LocalRequestOutbox(self.directory / f"invalid-ack-{index}")
                store.stage_publish(self.repo, self.arguments)
                result = store.deliver(lambda *args: response)
                self.assertEqual(result[0]["state"], "uncertain")
                self.assertEqual(result[0]["error"], "owner-acknowledgement-invalid")
                self.assertEqual(store.list_entries()[0]["state"], "uncertain")

    def test_valid_replay_acknowledgement_marks_entry_acknowledged(self):
        self.store.stage_publish(self.repo, self.arguments)
        response = {
            "request_id": self.arguments["request_id"],
            "revision": 3,
            "replayed": True,
        }
        result = self.store.deliver(lambda *args: response)
        self.assertEqual(result, [{"request_id": self.arguments["request_id"], "state": "acknowledged"}])
        self.assertEqual(self.store.list_entries()[0]["state"], "acknowledged")

    def _make_uncertain(self):
        self.store.stage_publish(self.repo, self.arguments)
        result = self.store.deliver(lambda *args: (_ for _ in ()).throw(
            requests.RequestClientError("owner-transport-failed")
        ))
        self.assertEqual(result[0]["state"], "uncertain")

    def test_committed_but_lost_response_is_read_before_any_repost(self):
        self.store.stage_publish(self.repo, self.arguments)
        calls = []
        def committed_then_lost(suffix, repo, payload):
            calls.append(suffix)
            persisted_states = json.loads((self.directory / "outbox.json").read_text())["entries"]
            self.assertEqual(persisted_states[0]["state"], "uncertain")
            raise requests.RequestClientError("owner-transport-failed")
        self.store.deliver(committed_then_lost)
        self.assertEqual(self.store.list_entries()[0]["state"], "uncertain")
        self.assertEqual(self.store.deliver(lambda *args: self.fail("must not POST while uncertain")), [])

        result = self.store.reconcile(lambda suffix, repo, args: (calls.append(suffix), self.snapshot())[1])
        self.assertEqual(result[0]["state"], "acknowledged")
        self.assertEqual(calls, ["publish", "get"])

    def test_confirmed_absence_returns_to_retryable_pending(self):
        self._make_uncertain()
        result = self.store.reconcile(lambda *args: (_ for _ in ()).throw(requests.RequestClientError("not-found")))
        self.assertEqual(result[0]["result"], "confirmed-absent")
        self.assertEqual(self.store.list_entries()[0]["state"], "pending")

    def test_changed_packet_and_malformed_snapshot_stay_uncertain(self):
        self._make_uncertain()
        changed = self.snapshot(packet={"summary": "changed"})
        result = self.store.reconcile(lambda *args: changed)
        self.assertEqual(result[0]["state"], "uncertain")
        self.assertEqual(self.store.list_entries()[0]["state"], "uncertain")

        malformed = self.snapshot()
        malformed.pop("dependants")
        result = self.store.reconcile(lambda *args: malformed)
        self.assertEqual(result[0]["state"], "uncertain")
        self.assertEqual(result[0]["error"], "owner-snapshot-mismatch")

        changed_dependants = self.snapshot(dependants=[])
        result = self.store.reconcile(lambda *args: changed_dependants)
        self.assertEqual(result[0]["state"], "uncertain")
        self.assertEqual(result[0]["error"], "owner-snapshot-mismatch")

    def test_revoked_owner_read_stays_uncertain_and_does_not_post(self):
        self._make_uncertain()
        result = self.store.reconcile(lambda *args: (_ for _ in ()).throw(requests.RequestClientError("authority-required")))
        self.assertEqual(result[0]["state"], "uncertain")
        self.assertEqual(result[0]["error"], "authority-required")
        self.assertEqual(self.store.deliver(lambda *args: self.fail("must not POST while uncertain")), [])

    def test_only_acknowledged_rows_can_be_pruned(self):
        self.store.stage_publish(self.repo, self.arguments)
        self.assertEqual(self.store.prune_acknowledged(), 0)
        self.store.deliver(lambda suffix, repo, payload: {
            "request_id": payload["request_id"], "revision": 1, "replayed": False,
        })
        self.assertEqual(self.store.prune_acknowledged(), 1)
        self.assertEqual(self.store.list_entries(), [])

    def test_load_rejects_tampered_rows_and_more_than_200_rows(self):
        self.store.stage_publish(self.repo, self.arguments)
        data = self.directory / "outbox.json"
        valid = json.loads(data.read_text())
        row = valid["entries"][0]
        malformed = (
            {**row, "unexpected": "field"},
            {**row, "state": []},
            {**row, "arguments": {**row["arguments"], "idempotency_key": "different"}},
            {**row, "arguments": {**row["arguments"], "rawTranscript": "private"}},
        )
        for bad_row in malformed:
            with self.subTest(row=bad_row):
                data.write_text(json.dumps({"schema": valid["schema"], "entries": [bad_row]}))
                with self.assertRaises(requests.RequestClientError) as caught:
                    self.store.list_entries()
                self.assertEqual(caught.exception.code, "outbox-storage-invalid")
        data.write_text(json.dumps({"schema": valid["schema"], "entries": [row, row]}))
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-invalid")
        data.write_text('{"schema":"operator-request-outbox/v1","entries":[],"entries":[]}')
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-invalid")
        duplicated_nested_key = json.dumps(valid).replace(
            '"required_outcome": "The operator runs the checked migration command."',
            '"required_outcome": "first", "required_outcome": "second"',
        )
        data.write_text(duplicated_nested_key)
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-invalid")
        data.write_text(" " * (self.store.MAX_BYTES + 1))
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-invalid")
        data.write_text(json.dumps({"schema": valid["schema"], "entries": [row] * 201}))
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-invalid")
        data.write_text(json.dumps({"schema": valid["schema"], "entries": [], "extra": True}))
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-invalid")


class ContinuationReadyTests(unittest.TestCase):
    request_id = "req_01JZZZZZZZZZZZZZZZZZZZZZZZ"

    def owner_records(self, *, state="resolved", stale=False, action="resolved-human-attestation"):
        snapshot = {
            "request_id": self.request_id, "revision": 4, "state": state, "freshness": "current",
            "packet": {"schema": "operator-request/v1", "kind": "perform", "required_outcome": "service healthy",
                       "reason": "operator action required", "execution": {}, "procedure": {}, "blocker": {}},
            "dependants": [
                {"work_item_id": 55, "session_id": "old-session", "runtime_id": "codex-local",
                 "work_revision": "work-r7", "current_work_revision": "work-r7" if not stale else "work-r8",
                 "source_changed": stale, "state": "active", "attached_at": "2026-10-24T00:00:00Z", "withdrawn_at": None},
                {"work_item_id": 56, "session_id": "withdrawn-session", "runtime_id": None,
                 "work_revision": "work-r2", "current_work_revision": "work-r2", "source_changed": False,
                 "state": "withdrawn", "attached_at": "2026-10-24T00:00:00Z", "withdrawn_at": "2026-10-24T00:01:00Z"},
            ],
            "created_at": "2026-10-24T00:00:00Z", "updated_at": "2026-10-24T00:02:00Z",
        }
        events = {
            "request_id": self.request_id, "next_after_revision": 4,
            "events": [{"request_id": self.request_id, "revision": 4, "action": action,
                        "actor": "private-principal", "details": {"completion_basis": "human-attestation",
                        "statement": "private attestation text", "performed_at": "2026-10-24T00:01:00Z",
                        "protected_effect_authorized": False}, "recorded_at": "2026-10-24T00:02:00Z"}],
        }
        class Owner:
            def __init__(self): self.calls = []
            def invoke(self, suffix, repo, args):
                self.calls.append((suffix, repo, args))
                return snapshot if suffix == "get" else events
        return Owner()

    def test_human_attestation_produces_metadata_only_successor_packet(self):
        owner = self.owner_records()
        result = requests.continuation_ready_packet(owner, "sprintctl", self.request_id)
        self.assertEqual([call[0] for call in owner.calls], ["get", "events"])
        self.assertEqual(owner.calls[1][2], {"request_id": self.request_id, "after_revision": 3, "limit": 1})
        self.assertEqual(result["schema"], "operator-request-continuation-ready/v1")
        self.assertEqual(result["owner"], {"repo_id": "sprintctl", "read_operation": "work.request.get-v1"})
        self.assertEqual(result["resolution"]["basis"], "human-attestation")
        self.assertEqual(len(result["dependants"]), 1)
        self.assertEqual(result["dependants"][0]["state"], "continuation-ready")
        serialized = json.dumps(result)
        self.assertNotIn("private attestation text", serialized)
        self.assertNotIn("private-principal", serialized)

    def test_stale_work_link_is_marked_needs_refresh(self):
        owner = self.owner_records(stale=True)
        result = requests.continuation_ready_packet(owner, "sprintctl", self.request_id)
        self.assertEqual(result["dependants"][0]["state"], "needs-refresh")

    def test_performed_report_without_resolution_does_not_create_packet(self):
        owner = self.owner_records(state="reported-performed")
        with self.assertRaises(requests.RequestClientError) as caught:
            requests.continuation_ready_packet(owner, "sprintctl", self.request_id)
        self.assertEqual(caught.exception.code, "continuation-not-ready")
        self.assertEqual([call[0] for call in owner.calls], ["get"])

    def test_unrecognized_resolution_evidence_is_refused(self):
        owner = self.owner_records(action="performed-reported")
        with self.assertRaises(requests.RequestClientError) as caught:
            requests.continuation_ready_packet(owner, "sprintctl", self.request_id)
        self.assertEqual(caught.exception.code, "resolution-evidence-unavailable")

    def test_revoked_event_read_does_not_emit_a_successor_packet(self):
        snapshot_owner = self.owner_records()
        snapshot = snapshot_owner.invoke("get", "sprintctl", {"request_id": self.request_id})

        class RevokedEventsOwner:
            def __init__(self):
                self.calls = []

            def invoke(self, suffix, repo_id, arguments):
                self.calls.append((suffix, repo_id, arguments))
                if suffix == "get":
                    return snapshot
                raise requests.RequestClientError("authority-required")

        owner = RevokedEventsOwner()
        with self.assertRaises(requests.RequestClientError) as caught:
            requests.continuation_ready_packet(owner, "sprintctl", self.request_id)

        self.assertEqual(caught.exception.code, "authority-required")
        self.assertEqual([call[0] for call in owner.calls], ["get", "events"])

    def test_malformed_work_link_identity_is_refused(self):
        malformed_fields = (
            {"work_item_id": requests._MAX_SAFE_INTEGER + 1},
            {"runtime_id": ""},
        )
        for fields in malformed_fields:
            with self.subTest(fields=fields):
                source = self.owner_records()
                snapshot = source.invoke("get", "sprintctl", {"request_id": self.request_id})
                snapshot["dependants"][0].update(fields)

                class MalformedSnapshotOwner:
                    def __init__(self):
                        self.calls = []

                    def invoke(self, suffix, repo_id, arguments):
                        self.calls.append(suffix)
                        if suffix == "get":
                            return snapshot
                        return source.invoke(suffix, repo_id, arguments)

                owner = MalformedSnapshotOwner()
                with self.assertRaises(requests.RequestClientError) as caught:
                    requests.continuation_ready_packet(owner, "sprintctl", self.request_id)

                self.assertEqual(caught.exception.code, "continuation-snapshot-invalid")

    def test_reconciliation_rejects_unsafe_dependent_identity(self):
        source = self.owner_records()
        snapshot = source.invoke("get", "sprintctl", {"request_id": self.request_id})
        snapshot["dependants"] = snapshot["dependants"][:1]
        expected = {"work_item_id": 55, "session_id": "old-session"}
        for change in (
            {"work_item_id": requests._MAX_SAFE_INTEGER + 1},
            {"runtime_id": ""},
        ):
            with self.subTest(change=change):
                row = {
                    "request_id": self.request_id,
                    "arguments": {
                        "packet": snapshot["packet"],
                        "dependants": [{**expected, **change}],
                    },
                }
                candidate = {**snapshot, "dependants": [dict(snapshot["dependants"][0])]}
                candidate["dependants"][0].update(change)
                self.assertFalse(requests.LocalRequestOutbox._snapshot_matches(row, candidate))


if __name__ == "__main__":
    unittest.main()
