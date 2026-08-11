from __future__ import annotations

from datetime import datetime, timedelta, timezone
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/validate_opencode_qualification.py"
RUNNER_SCRIPT = ROOT / "templates/dispatch/scripts/run_opencode_qualification.py"
CORPUS = ROOT / "templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json"


def _load_module(path: Path = SCRIPT, name: str = "validate_opencode_qualification"):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate = _load_module()
runner_impl = _load_module(RUNNER_SCRIPT, "run_opencode_qualification_for_admission_test")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _receipt() -> dict[str, object]:
    return {
        "schema_version": "opencode-provider-qualification-receipt/v2",
        "profile_id": "opencode-nixpkgs-devbox-1.18.4",
        "semantic_adapter": "opencode-noninteractive/v1",
        "cli_version": "1.18.4",
        "executable_fingerprint": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["opencode_digest"],
        "runner_digest": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["runner_digest"],
        "opencode_digest": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["opencode_digest"],
        "channel_revision": "nixpkgs/nixos-unstable@47e6de6",
        "profile_digest": _digest(ROOT / "templates/dispatch/harness-profiles/opencode-nixpkgs-devbox-1.18.4.json"),
        "config_digest": _digest(ROOT / "templates/dispatch/hybrid/opencode.hybrid.json"),
        "overlay_digest": "sha256:" + "g" * 64,
        "policy_digest": _digest(ROOT / "templates/dispatch/hybrid/hybrid-dispatch.v1.json"),
        "provider_model": "opencode-go/deepseek-v4-flash",
        "request_digest": gate._canonical_digest(gate.EXPECTED_REQUEST),
        "runner_digest": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["runner_digest"],
        "opencode_digest": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["opencode_digest"],
        "provider_id": "opencode-go",
        "model_id": "deepseek-v4-flash",
        "route_model": "opencode-go/deepseek-v4-flash",
        "worker_model": "opencode-go/deepseek-v4-flash",
        "model_override": False,
        "worker_identity": "agentworker",
        "provider_contacted": True,
        "workspace_opt_in": True,
        "workspace_evidence": {"manifest_digest": _digest(ROOT / "agentops.dispatch.json"), "repository_opt_in": True, "provider_workspace_opt_in": True},
        "usage_baseline": 100,
        "usage_observed": 200,
        "usage_multiplier": 2,
        "cost_usd": 0.01,
        "cost_limit_semantics": "post-hoc-acceptance",
        "hard_wall_seconds": 120,
        "tokens": 1000,
        "attempts": 1,
        "containment": {"coordinator_write_denied": True, "workspace_round_trip": True, "worker_identity": "agentworker", "exact_groups": ["agentworker", "agentdispatch"], "reads_contained": False, "evidence_digest": "sha256:" + "c" * 64},
        "usage_evidence": {"source": "provider-reported", "provider_request_id_digest": "sha256:" + "3" * 64, "source_event_digest": "sha256:" + "4" * 64, "phase_units": [{"phase": "worker", "units": 200}]},
        "usage_evidence_digest": "sha256:" + "d" * 64,
        "provider_model_evidence": [{"phase": "worker", "providerID": "opencode-go", "modelID": "deepseek-v4-flash", "finish": "stop", "part_types": ["text", "step-finish"], "evidence_digest": "sha256:" + "b" * 64}],
        "capability_probe_results": {probe: "pass" for probe in gate.EXPECTED_REQUIRED_PROBES},
        "lifecycle_probe_results": {probe: "pass" for probe in gate.EXPECTED_REQUIRED_PROBES},
        "capability_evidence_digest": "sha256:" + "e" * 64,
        "lifecycle_evidence_digest": "sha256:" + "f" * 64,
        "evidence_artifacts": {
            "provider_model": {"artifact": "provider.json", "digest": "sha256:" + "b" * 64},
            "usage": {"artifact": "usage.json", "digest": "sha256:" + "d" * 64},
            "containment": {"artifact": "containment.json", "digest": "sha256:" + "c" * 64},
            "capability": {"artifact": "capability.json", "digest": "sha256:" + "e" * 64},
            "lifecycle": {"artifact": "lifecycle.json", "digest": "sha256:" + "f" * 64},
            "overlay": {"artifact": "overlay.json", "digest": "sha256:" + "g" * 64},
            "workspace": {"artifact": "workspace.json", "digest": "sha256:" + "h" * 64},
        },
        "raw_transcript_captured": False,
        "qualification_state": "preflight_observed",
        "independent_review": {"status": "pending", "ref": None},
        "runner_id": gate.RUNNER_ID,
        "run_id": "run-" + "1" * 32,
        "run_nonce": "nonce-" + "2" * 64,
        "packet_digest": gate._canonical_digest(json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["packet"]),
        "request_digest": gate._canonical_digest(gate.EXPECTED_REQUEST),
        "runner_record_digest": "sha256:" + "9" * 64,
        "runner_signature_digest": "sha256:" + "a" * 64,
        "evidence_bundle_digest": "sha256:" + "8" * 64,
    }


def _write_fixture(
    temporary: Path,
    *,
    receipt: dict[str, object] | None = None,
    artifact_overrides: dict[str, bytes] | None = None,
    record_patch: dict[str, object] | None = None,
) -> tuple[dict[str, object], Path, Path, Path, Path]:
    receipt = copy.deepcopy(receipt or _receipt())
    evidence_root = temporary / "evidence"
    evidence_root.mkdir()
    os.chmod(evidence_root, 0o700)
    record_root = temporary / "records"
    record_root.mkdir()
    ledger_root = temporary / "ledger"
    ledger_root.mkdir()
    os.chmod(record_root, 0o700)
    os.chmod(ledger_root, 0o700)
    hybrid_dispatch = gate._load_module(ROOT / "templates/dispatch/scripts/hybrid_dispatch.py", "test_hybrid_dispatch")
    manifest = json.loads((ROOT / "agentops.dispatch.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / "templates/dispatch/hybrid/hybrid-dispatch.v1.json").read_text(encoding="utf-8"))
    base_config = json.loads((ROOT / "templates/dispatch/hybrid/opencode.hybrid.json").read_text(encoding="utf-8"))
    command_ids = ["agentops.dispatch.tests"]
    overlay = hybrid_dispatch.build_overlay({"route": "mechanical_bulk", "allowed_command_ids": command_ids}, manifest, policy, base_config)
    artifact_contents: dict[str, bytes] = {
        "provider.json": json.dumps({"schema_version": "opencode-provider-origin/v1", "session_id_digest": "sha256:" + "1" * 64, "request_binding_digest": "sha256:" + "2" * 64, "events": [{"phase": "worker", "providerID": "opencode-go", "modelID": "deepseek-v4-flash", "finish": "stop", "part_types": ["text", "step-finish"]}]}, sort_keys=True, separators=(",", ":")).encode(),
        "usage.json": json.dumps({"schema_version": "opencode-provider-usage/v1", "provider_request_id_digest": "sha256:" + "3" * 64, "source_event_digest": "sha256:" + "4" * 64, "source": "provider-reported", "usage_baseline": 100, "usage_observed": 200, "phase_units": [{"phase": "worker", "units": 200}]}, sort_keys=True, separators=(",", ":")).encode(),
        "containment.json": b'{"coordinator_write_denied":true,"workspace_round_trip":true,"worker_identity":"agentworker","exact_groups":["agentworker","agentdispatch"],"reads_contained":false}',
        "capability.json": json.dumps({probe: "pass" for probe in gate.EXPECTED_REQUIRED_PROBES}, sort_keys=True, separators=(",", ":")).encode(),
        "lifecycle.json": json.dumps({probe: "pass" for probe in gate.EXPECTED_REQUIRED_PROBES}, sort_keys=True, separators=(",", ":")).encode(),
        "overlay.json": json.dumps({"route": "mechanical_bulk", "agent": "ao-mechanical-bulk", "allowed_command_ids": command_ids, "model_override": None, "overlay": overlay}, sort_keys=True, separators=(",", ":")).encode(),
        "workspace.json": json.dumps({"manifest_digest": receipt["workspace_evidence"]["manifest_digest"], "repository_opt_in": True, "provider_workspace_opt_in": True}, sort_keys=True, separators=(",", ":")).encode(),
    }
    artifact_contents.update(artifact_overrides or {})
    artifact_digests: dict[str, str] = {}
    for name, content in artifact_contents.items():
        path = evidence_root / name
        path.write_bytes(content)
        artifact_digests[name] = _digest(path)
    artifact_names = {
        "provider_model": "provider.json",
        "usage": "usage.json",
        "containment": "containment.json",
        "capability": "capability.json",
        "lifecycle": "lifecycle.json",
        "overlay": "overlay.json",
        "workspace": "workspace.json",
    }
    receipt["evidence_artifacts"] = {logical: {"artifact": filename, "digest": artifact_digests[filename]} for logical, filename in artifact_names.items()}
    receipt["provider_model_evidence"][0]["evidence_digest"] = artifact_digests["provider.json"]
    receipt["usage_evidence_digest"] = artifact_digests["usage.json"]
    receipt["containment"]["evidence_digest"] = artifact_digests["containment.json"]
    receipt["capability_evidence_digest"] = artifact_digests["capability.json"]
    receipt["lifecycle_evidence_digest"] = artifact_digests["lifecycle.json"]
    receipt["overlay_digest"] = artifact_digests["overlay.json"]
    receipt["evidence_bundle_digest"] = gate._bundle_digest(receipt["evidence_artifacts"])

    now = datetime.now(timezone.utc).replace(microsecond=0)
    record: dict[str, object] = {
        "schema_version": gate.RUN_RECORD_SCHEMA,
        "runner_id": gate.RUNNER_ID,
        "run_id": receipt["run_id"],
        "nonce": receipt["run_nonce"],
        "packet_digest": receipt["packet_digest"],
        "runner_digest": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["runner_digest"],
        "opencode_digest": json.loads(CORPUS.read_text(encoding="utf-8"))["live_run"]["opencode_digest"],
        "issued_at": (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
        "started_at": (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "finished_at": now.isoformat().replace("+00:00", "Z"),
        "status": "completed",
        "attempts": 1,
        "token_budget": {"soft_ceiling": gate.SOFT_TOKEN_CEILING, "hard_ceiling": gate.HARD_TOKEN_CEILING, "observed_tokens": receipt["tokens"], "soft_enforced": True, "hard_enforced": True, "soft_limit_hit": False, "hard_limit_hit": False, "attempts": 1, "enforcement_events": [{"phase": "worker", "observed_tokens": receipt["tokens"], "soft_ceiling": gate.SOFT_TOKEN_CEILING, "hard_ceiling": gate.HARD_TOKEN_CEILING, "soft_enforced": True, "hard_enforced": True}]},
        "provider_origin": {"source": "opencode-sanitized-export", "providerID": "opencode-go", "modelID": "deepseek-v4-flash", "artifact_digest": artifact_digests["provider.json"], "session_count": 1, "session_id_digest": "sha256:" + "1" * 64, "request_binding_digest": "sha256:" + "2" * 64, "event_count": 1},
        "usage": {"source": "opencode-provider-step-finish", "baseline": receipt["usage_baseline"], "observed": receipt["usage_observed"], "artifact_digest": artifact_digests["usage.json"], "provider_request_id_digest": "sha256:" + "3" * 64, "source_event_digest": "sha256:" + "4" * 64},
        "containment": {"probe_id": "contained-identity", "status": "pass", "worker_identity": "agentworker", "coordinator_write_denied": True, "workspace_round_trip": True, "exact_groups": ["agentworker", "agentdispatch"], "reads_contained": False, "artifact_digest": artifact_digests["containment.json"]},
        "evidence_bundle_digest": receipt["evidence_bundle_digest"],
        "request_digest": gate._canonical_digest(gate.EXPECTED_REQUEST),
        "receipt_binding_digest": "sha256:" + "7" * 64,
        "record_filename": f"{receipt['run_id']}.json",
        "signature_filename": f"{receipt['run_id']}.json.sig",
        "cost_usd": receipt["cost_usd"],
        "cost_limit_semantics": "post-hoc-acceptance",
        "hard_wall_seconds": 120,
        "sealed": True,
    }
    for key, value in (record_patch or {}).items():
        record[key] = value
    record["receipt_binding_digest"] = gate._receipt_binding_digest(receipt)
    key_path = temporary / "runner.key"
    subprocess.run([gate.SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    public_key_path = key_path.with_name(key_path.name + ".pub")
    allowed_signers_path = temporary / "allowed_signers"
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    allowed_signers_path.write_text(f"{gate.RUNNER_ID} namespaces=\"{gate.SIGNATURE_NAMESPACE}\" {public_key}\n", encoding="utf-8")
    os.chmod(key_path, 0o400)
    os.chmod(public_key_path, 0o444)
    os.chmod(allowed_signers_path, 0o444)
    record_path = record_root / f"{receipt['run_id']}.json"
    record_path.write_bytes(gate._canonical(record))
    os.chmod(record_path, 0o400)
    subprocess.run([gate.SSH_KEYGEN, "-q", "-Y", "sign", "-f", str(key_path), "-n", gate.SIGNATURE_NAMESPACE, str(record_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    signature_path = record_path.with_name(record_path.name + ".sig")
    os.chmod(signature_path, 0o400)
    receipt["runner_record_digest"] = _digest(record_path)
    receipt["runner_signature_digest"] = _digest(signature_path)
    sentinel_path = ledger_root / "packet.attempted"
    sentinel_path.write_bytes(gate._canonical({"schema_version": "opencode-provider-qualification-attempt/v1", "runner_id": gate.RUNNER_ID, "packet_digest": receipt["packet_digest"], "attempts": 1, "reserved_at": (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")}))
    os.chmod(sentinel_path, 0o400)
    issued_path = ledger_root / f"{receipt['run_nonce']}.issued"
    issued_path.write_bytes(gate._canonical({"schema_version": "opencode-provider-qualification-nonce/v1", "runner_id": gate.RUNNER_ID, "run_id": receipt["run_id"], "nonce": receipt["run_nonce"], "packet_digest": receipt["packet_digest"], "issued_at": (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"), "attempts": 1, "consumed": False}))
    os.chmod(issued_path, 0o400)
    completed_path = ledger_root / f"{receipt['run_nonce']}.completed"
    completed_path.write_bytes(gate._canonical({"schema_version": "opencode-provider-qualification-nonce/v1-completed", "run_id": receipt["run_id"], "nonce": receipt["run_nonce"], "packet_digest": receipt["packet_digest"], "record_digest": receipt["runner_record_digest"], "signature_digest": receipt["runner_signature_digest"]}))
    os.chmod(completed_path, 0o400)
    receipt_path = temporary / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    gate.EXPECTED_RUNNER_PUBLIC_KEY_PATH = str(public_key_path)
    gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH = str(allowed_signers_path)
    gate.EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT = _digest(public_key_path)
    gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT = _digest(allowed_signers_path)
    gate.EXPECTED_RECORD_ROOT = str(record_root)
    gate.EXPECTED_LEDGER_ROOT = str(ledger_root)
    gate.EXPECTED_EVIDENCE_ROOT = str(evidence_root)
    gate.EXPECTED_OWNER_UID = os.getuid()
    corpus["live_run"]["runner_public_key_fingerprint"] = _digest(public_key_path)
    corpus["live_run"]["runner_public_key_path"] = str(public_key_path)
    corpus["live_run"]["runner_allowed_signers_fingerprint"] = _digest(allowed_signers_path)
    corpus["live_run"]["runner_allowed_signers_path"] = str(allowed_signers_path)
    corpus["live_run"]["record_root"] = str(record_root)
    corpus["live_run"]["consumption_ledger_root"] = str(ledger_root)
    corpus["live_run"]["evidence_root"] = str(evidence_root)
    corpus_path = temporary / "corpus.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    return receipt, receipt_path, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path


class OpenCodeQualificationCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._constants = (
            gate.EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT,
            gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT,
            gate.EXPECTED_RUNNER_PUBLIC_KEY_PATH,
            gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH,
            gate.EXPECTED_RECORD_ROOT,
            gate.EXPECTED_LEDGER_ROOT,
            gate.EXPECTED_EVIDENCE_ROOT,
            gate.EXPECTED_OWNER_UID,
        )

    def tearDown(self) -> None:
        (
            gate.EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT,
            gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT,
            gate.EXPECTED_RUNNER_PUBLIC_KEY_PATH,
            gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH,
            gate.EXPECTED_RECORD_ROOT,
            gate.EXPECTED_LEDGER_ROOT,
            gate.EXPECTED_EVIDENCE_ROOT,
            gate.EXPECTED_OWNER_UID,
        ) = self._constants

    def test_offline_gate_is_deterministic_and_stays_blocked(self) -> None:
        result = gate.evaluate(CORPUS)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["provider_contacted"])
        self.assertFalse(result["qualification_eligible"])
        self.assertEqual(result["qualification_state"], "preflight_observed")
        self.assertEqual(result["gates"]["provider-qualification"], "blocked")

    def test_runner_output_bundle_round_trips_through_admission_and_one_time_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _write_fixture(Path(temporary))
            receipt, receipt_path, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = fixture
            runner_output = {"receipt": receipt_path, "evidence_root": evidence_root, "record": record_path, "public_key": public_key_path, "allowed_signers": allowed_signers_path}
            self.assertEqual(runner_impl._bundle_digest(receipt["evidence_artifacts"]), gate._bundle_digest(receipt["evidence_artifacts"]))
            self.assertEqual(runner_impl._receipt_binding_digest(receipt), gate._receipt_binding_digest(receipt))
            result = gate.evaluate(corpus_path, receipt_path=runner_output["receipt"], evidence_root=runner_output["evidence_root"], runner_record_path=runner_output["record"], runner_public_key_path=runner_output["public_key"], runner_allowed_signers_path=runner_output["allowed_signers"], consume=True)
            self.assertTrue(result["candidate_ready"])
            self.assertFalse(result["qualification_eligible"])
            with self.assertRaisesRegex(gate.QualificationError, "consumed"):
                gate.evaluate(corpus_path, receipt_path=receipt_path, evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path, consume=True)
            copied_root = Path(temporary) / "copied-record-root"
            copied_root.mkdir()
            copied_record = copied_root / record_path.name
            copied_record.write_bytes(record_path.read_bytes())
            os.chmod(copied_record, 0o400)
            with self.assertRaisesRegex(gate.QualificationError, "outside the pinned trusted record root"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=copied_record, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_forged_receipt_and_forged_runner_record_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt, receipt_path, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            receipt["usage_baseline"] = 99
            with self.assertRaisesRegex(gate.QualificationError, "runner-authenticated|two-times"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)
            forged = json.loads(record_path.read_text())
            forged["status"] = "completed"
            forged["run_id"] = "run-" + "3" * 32
            os.chmod(record_path, 0o600)
            record_path.write_text(json.dumps(forged), encoding="utf-8")
            os.chmod(record_path, 0o400)
            with self.assertRaisesRegex(gate.QualificationError, "outside the pinned trusted record root|signature"):
                gate.validate_provider_receipt(json.loads(receipt_path.read_text()), json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)
        with tempfile.TemporaryDirectory() as temporary:
            receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            receipt["cost_usd"] = 2.99
            with self.assertRaisesRegex(gate.QualificationError, "authenticated"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)
        with tempfile.TemporaryDirectory() as temporary:
            receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            untrusted_key = Path(temporary) / "untrusted.key"
            untrusted_key.write_bytes(b"attacker key")
            os.chmod(untrusted_key, 0o400)
            with self.assertRaisesRegex(gate.QualificationError, "exact configured trusted path"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=untrusted_key, runner_allowed_signers_path=allowed_signers_path)

    def test_stale_record_and_missing_trusted_binding_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            old = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
            receipt, receipt_path, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary), record_patch={"issued_at": (old - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"), "started_at": (old - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"), "finished_at": old.isoformat().replace("+00:00", "Z")})
            with self.assertRaisesRegex(gate.QualificationError, "stale"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)
            with self.assertRaisesRegex(gate.QualificationError, "trusted runner"):
                gate.evaluate(corpus_path, receipt_path=receipt_path, evidence_root=evidence_root, consume=True)

    def test_exact_model_and_no_override_are_required(self) -> None:
        for field, value, message in (("provider_id", "opencode", "exact"), ("model_id", "deepseek-v4-pro", "exact"), ("model_override", True, "override"), ("worker_model", "opencode/free-model", "exact")):
            with tempfile.TemporaryDirectory() as temporary:
                receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
                receipt[field] = value
                with self.subTest(field=field), self.assertRaisesRegex(gate.QualificationError, message):
                    gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_workspace_opt_in_and_two_x_ceiling_are_enforced(self) -> None:
        for field, value, message in (("workspace_opt_in", False, "workspace"), ("usage_observed", 201, "two-times"), ("usage_multiplier", 1.5, "inconsistent")):
            with tempfile.TemporaryDirectory() as temporary:
                receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
                receipt[field] = value
                with self.subTest(field=field), self.assertRaisesRegex(gate.QualificationError, message):
                    gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_soft_and_hard_token_limits_are_enforced_at_receipt_and_execution(self) -> None:
        for tokens, message in ((gate.SOFT_TOKEN_CEILING + 1, "soft"), (gate.HARD_TOKEN_CEILING + 1, "hard")):
            with tempfile.TemporaryDirectory() as temporary:
                receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
                receipt["tokens"] = tokens
                with self.subTest(tokens=tokens), self.assertRaisesRegex(gate.QualificationError, message):
                    gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_privacy_schema_rejects_string_leaks_in_every_evidence_artifact(self) -> None:
        cases = {
            "provider.json": b'[{"phase":"/forged/path","providerID":"opencode-go","modelID":"deepseek-v4-flash"}]',
            "usage.json": b'{"source":"provider-reported","usage_baseline":100,"usage_observed":200,"phase_units":[{"phase":"/forged/path","units":200}]}',
            "containment.json": b'{"coordinator_write_denied":true,"workspace_round_trip":true,"worker_identity":"/forged/path","exact_groups":["agentworker","agentdispatch"],"reads_contained":false}',
            "capability.json": b'{"/forged/path":"pass"}',
            "lifecycle.json": b'{"/forged/path":"pass"}',
            "workspace.json": json.dumps({"manifest_digest": "sha256:" + "a" * 64, "repository_opt_in": True, "provider_workspace_opt_in": True, "note": "/forged/path"}).encode(),
        }
        for artifact, content in cases.items():
            with tempfile.TemporaryDirectory() as temporary:
                _, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary), artifact_overrides={artifact: content})
                receipt = json.loads((Path(temporary) / "receipt.json").read_text())
                with self.subTest(artifact=artifact), self.assertRaisesRegex(gate.QualificationError, "absolute workspace path"):
                    gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_strict_privacy_grammars_reject_revision_phase_and_source_smuggling(self) -> None:
        cases = (("channel_revision", "nixpkgs/nixos-unstable@token=secret", "channel grammar|secret-like"),)
        for field, value, message in cases:
            with tempfile.TemporaryDirectory() as temporary:
                receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
                receipt[field] = value
                with self.subTest(field=field), self.assertRaisesRegex(gate.QualificationError, message):
                    gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

        with tempfile.TemporaryDirectory() as temporary:
            receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            receipt["usage_evidence"]["phase_units"][0]["phase"] = "worker-secret=smuggled"
            with self.assertRaisesRegex(gate.QualificationError, "phase"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_corpus_cannot_substitute_any_trust_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, _, _, _, _, _, corpus_path = _write_fixture(Path(temporary))
            corpus = json.loads(corpus_path.read_text())
            for field in ("runner_public_key_path", "runner_allowed_signers_path", "record_root", "consumption_ledger_root"):
                mutated = copy.deepcopy(corpus)
                mutated["live_run"][field] = str(Path(temporary) / "substituted")
                corpus_path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(gate.QualificationError, "exact configured trusted path"):
                    gate.evaluate(corpus_path)

    def test_trusted_material_and_record_modes_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            os.chmod(public_key_path, 0o400)
            with self.assertRaisesRegex(gate.QualificationError, "public key must have mode"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)
            os.chmod(public_key_path, 0o444)
            os.chmod(record_path, 0o600)
            with self.assertRaisesRegex(gate.QualificationError, "execution record.*mode"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_evidence_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            outside = Path(temporary) / "outside.json"
            outside.write_text("{}")
            provider = evidence_root / "provider.json"
            provider.unlink()
            provider.symlink_to(outside)
            with self.assertRaisesRegex(gate.QualificationError, "regular non-symlink|escapes"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_admission_requires_the_packet_sentinel_and_runner_ledger_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
            ledger_root = Path(json.loads(corpus_path.read_text())["live_run"]["consumption_ledger_root"])
            (ledger_root / "packet.attempted").unlink()
            with self.assertRaisesRegex(gate.QualificationError, "attempt sentinel"):
                gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_containment_budget_single_attempt_and_privacy_are_enforced(self) -> None:
        for key, value, message in (("worker_identity", "agent", "contained"), ("attempts", 2, "one attempt"), ("raw_transcript_captured", True, "transcript")):
            with tempfile.TemporaryDirectory() as temporary:
                receipt, _, evidence_root, record_path, public_key_path, allowed_signers_path, corpus_path = _write_fixture(Path(temporary))
                receipt[key] = value
                with self.subTest(field=key), self.assertRaisesRegex(gate.QualificationError, message):
                    gate.validate_provider_receipt(receipt, json.loads(corpus_path.read_text()), evidence_root=evidence_root, runner_record_path=record_path, runner_public_key_path=public_key_path, runner_allowed_signers_path=allowed_signers_path)

    def test_missing_repository_opt_in_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus_path = Path(temporary) / "corpus.json"
            corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
            corpus["workspace"]["repository_opt_in_required"] = False
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(gate.QualificationError, "opt-in"):
                gate.evaluate(corpus_path)

    def test_manual_profile_promotion_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus_path = Path(temporary) / "corpus.json"
            corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
            corpus["qualification"]["state"] = "qualified"
            corpus["qualification"]["qualification_eligible"] = True
            corpus["qualification"]["blocking_probes"] = []
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(gate.QualificationError, "preflight_observed"):
                gate.evaluate(corpus_path)


if __name__ == "__main__":
    unittest.main()
