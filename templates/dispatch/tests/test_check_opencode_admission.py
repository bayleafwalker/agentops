from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/check_opencode_admission.py"
VALIDATOR = ROOT / "templates/dispatch/scripts/validate_opencode_qualification.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load(SCRIPT, "check_opencode_admission")
gate = _load(VALIDATOR, "validate_opencode_qualification_for_checker_test")


class FakeProcess:
    def __init__(self, events: list[dict[str, object]], returncode: int = 0):
        self.stdout = io.StringIO("\n".join(json.dumps(event) for event in events) + "\n")
        self.returncode = returncode
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: int = 0) -> int:
        return self.returncode


def _event(tokens: int, *, session_id: str = "ses_test_0001") -> dict[str, object]:
    """Matches the real captured OpenCode 1.18.4 shape: no provider-issued
    request-ID field anywhere -- confirmed absent across seven live
    transcripts in an earlier investigation on this same corpus."""
    return {
        "type": "step_finish",
        "sessionID": session_id,
        "part": {"type": "step-finish", "reason": "stop", "tokens": {"input": 100, "output": tokens - 100 if tokens > 100 else 0, "reasoning": 0}, "cost": 0.01},
        "usage": {"baseline_units": 100, "observed_units": 150, "total_tokens": tokens, "cost_usd": 0.01},
    }


class RunOpencodeOnceTests(unittest.TestCase):
    def test_one_clean_completion_is_accepted(self) -> None:
        process = FakeProcess([_event(150)])
        result = checker._run_opencode_once(
            command=[str(checker.RUNUSER), "--user", checker.WORKER_USER, "--", str(checker.OPENCODE), "run", "bounded"],
            environment={},
            popen=lambda *args, **kwargs: process,
        )
        self.assertEqual(result["completion_events"], 1)
        self.assertFalse(process.killed)

    def test_multiple_clean_completions_are_accepted_and_sanity_bound_all(self) -> None:
        """The key behavior change from the prior design: a genuine
        multi-step tool-use response legitimately emits more than one
        step-finish event. 'Exactly one, hard-fail otherwise' was the same
        over-fit-security-gate pattern that produced a false diagnosis
        earlier in this corpus's history -- this must not reintroduce it."""
        process = FakeProcess([_event(150, session_id="ses_test_0001"), _event(180, session_id="ses_test_0001")])
        result = checker._run_opencode_once(
            command=[str(checker.RUNUSER), "--user", checker.WORKER_USER, "--", str(checker.OPENCODE), "run", "bounded"],
            environment={},
            popen=lambda *args, **kwargs: process,
        )
        self.assertEqual(result["completion_events"], 2)
        self.assertFalse(process.killed)

    def test_zero_completions_fail_closed(self) -> None:
        process = FakeProcess([{"type": "step_start", "sessionID": "ses_test_0001"}])
        with self.assertRaisesRegex(checker.CheckError, "no clean completion event"):
            checker._run_opencode_once(
                command=[str(checker.RUNUSER), "--user", checker.WORKER_USER, "--", str(checker.OPENCODE), "run", "bounded"],
                environment={},
                popen=lambda *args, **kwargs: process,
            )

    def test_soft_and_hard_overruns_still_terminate(self) -> None:
        for tokens, expected in ((checker.SOFT_TOKENS + 1, "soft"), (checker.HARD_TOKENS + 1, "hard")):
            process = FakeProcess([_event(tokens)])
            with self.subTest(tokens=tokens), self.assertRaisesRegex(checker.CheckError, expected):
                checker._run_opencode_once(
                    command=[str(checker.RUNUSER), "--user", checker.WORKER_USER, "--", str(checker.OPENCODE), "run", "bounded"],
                    environment={},
                    popen=lambda *args, **kwargs: process,
                )
            self.assertTrue(process.killed)

    def test_cost_overrun_still_terminates(self) -> None:
        event = _event(1)
        event["usage"]["cost_usd"] = checker.MAX_COST_USD + 0.01
        process = FakeProcess([event])
        with self.assertRaisesRegex(checker.CheckError, "cost ceiling"):
            checker._run_opencode_once(
                command=[str(checker.RUNUSER), "--user", checker.WORKER_USER, "--", str(checker.OPENCODE), "run", "bounded"],
                environment={},
                popen=lambda *args, **kwargs: process,
            )
        self.assertTrue(process.killed)

    def test_non_json_event_fails_closed(self) -> None:
        process = FakeProcess([])
        process.stdout = io.StringIO("not json\n")
        with self.assertRaisesRegex(checker.CheckError, "non-JSON"):
            checker._run_opencode_once(
                command=[str(checker.RUNUSER), "--user", checker.WORKER_USER, "--", str(checker.OPENCODE), "run", "bounded"],
                environment={},
                popen=lambda *args, **kwargs: process,
            )

    def test_wrong_command_prefix_is_rejected(self) -> None:
        with self.assertRaisesRegex(checker.CheckError, "exact contained OpenCode run"):
            checker._run_opencode_once(command=["/bin/sh", "-c", "true"], environment={}, popen=lambda *args, **kwargs: FakeProcess([]))


class SanitizedExportTests(unittest.TestCase):
    def _export(self, *, parts: list[dict[str, object]] | None = None, provider: str = "opencode-go", model: str = "deepseek-v4-flash", finish: str = "stop") -> dict[str, object]:
        return {
            "info": {"id": "ses_test_0001"},
            "messages": [
                {"info": {"role": "assistant", "providerID": provider, "modelID": model, "finish": finish}, "parts": parts if parts is not None else [{"type": "text"}, {"type": "step-finish"}]},
            ],
        }

    def test_exact_two_part_grammar_is_accepted(self) -> None:
        result = checker._parse_sanitized_export(json.dumps(self._export()), "ses_test_0001", provider="opencode-go", model="deepseek-v4-flash")
        self.assertEqual(result["finish"], "stop")

    def test_loosened_grammar_accepts_extra_parts_around_a_completion(self) -> None:
        """Loosened from an exact ['text', 'step-finish'] match (over-fit to
        one harness snapshot) -- a tool call or extra text part must not
        fail this check as long as a real completion occurred."""
        parts = [{"type": "text"}, {"type": "tool"}, {"type": "text"}, {"type": "step-finish"}]
        result = checker._parse_sanitized_export(json.dumps(self._export(parts=parts)), "ses_test_0001", provider="opencode-go", model="deepseek-v4-flash")
        self.assertEqual(result["finish"], "stop")

    def test_missing_completion_evidence_fails_closed(self) -> None:
        parts = [{"type": "text"}]
        with self.assertRaisesRegex(checker.CheckError, "no completion evidence"):
            checker._parse_sanitized_export(json.dumps(self._export(parts=parts)), "ses_test_0001", provider="opencode-go", model="deepseek-v4-flash")

    def test_completion_with_no_generated_text_fails_closed(self) -> None:
        """A bare step-finish with no text part must not pass as routable:
        that would satisfy 'routable' and 'cost-sane' without ever answering
        the check's second question (does it produce a reasonable output)."""
        parts = [{"type": "step-finish"}]
        with self.assertRaisesRegex(checker.CheckError, "no generated text content"):
            checker._parse_sanitized_export(json.dumps(self._export(parts=parts)), "ses_test_0001", provider="opencode-go", model="deepseek-v4-flash")

    def test_wrong_provider_model_finish_fails_closed(self) -> None:
        for kwargs, message in (
            ({"provider": "other-provider"}, "provider/model/finish"),
            ({"model": "other-model"}, "provider/model/finish"),
            ({"finish": "tool-calls"}, "provider/model/finish"),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(checker.CheckError, message):
                checker._parse_sanitized_export(json.dumps(self._export(**kwargs)), "ses_test_0001", provider="opencode-go", model="deepseek-v4-flash")

    def test_session_identity_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(checker.CheckError, "session identity"):
            checker._parse_sanitized_export(json.dumps(self._export()), "ses_other", provider="opencode-go", model="deepseek-v4-flash")


class ProviderUsageAndTokensTests(unittest.TestCase):
    def test_usage_dict_shape(self) -> None:
        event = {"usage": {"baseline_units": 10, "observed_units": 12, "cost_usd": 0.5}}
        self.assertEqual(checker._provider_usage(event), (10.0, 12.0, 0.5))

    def test_tokens_dict_fallback_shape(self) -> None:
        event = {"part": {"tokens": {"input": 10, "output": 2, "reasoning": 0}, "cost": 0.1}}
        self.assertEqual(checker._provider_usage(event), (10.0, 12.0, 0.1))

    def test_no_usage_structure_fails_closed(self) -> None:
        with self.assertRaisesRegex(checker.CheckError, "no provider usage structure"):
            checker._provider_usage({"part": {}})

    def test_provider_event_identification(self) -> None:
        self.assertTrue(checker._provider_event({"type": "step_finish", "sessionID": "ses_ok"}))
        self.assertFalse(checker._provider_event({"type": "step_start", "sessionID": "ses_ok"}))
        self.assertFalse(checker._provider_event({"type": "step_finish", "sessionID": "has spaces"}))


class CredentialProvisioningTests(unittest.TestCase):
    def test_round_trip_provision_and_scrub_leaves_no_trace(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as temporary:
            workspace = Path(temporary)
            checker.ACTIVE_WORKSPACE_ROOT = workspace
            checker.EXPECTED_WORKER_UID = os.getuid()
            auth_bytes = json.dumps({"opencode-go": {"type": "api", "key": "fake-test-credential"}}).encode()
            auth_path = checker._provision_provider_auth(auth_bytes)
            self.assertTrue(auth_path.is_file())
            self.assertEqual(auth_path.read_bytes(), auth_bytes)
            checker._scrub_provider_auth(auth_path, auth_bytes)
            self.assertFalse(auth_path.exists())
            for root, _dirs, files in os.walk(workspace):
                for name in files:
                    self.assertNotIn(b"fake-test-credential", (Path(root) / name).read_bytes())

    def test_scrub_detects_leftover_credential_bytes(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as temporary:
            workspace = Path(temporary)
            checker.ACTIVE_WORKSPACE_ROOT = workspace
            checker.EXPECTED_WORKER_UID = os.getuid()
            auth_bytes = json.dumps({"opencode-go": {"type": "api", "key": "fake-test-credential"}}).encode()
            auth_path = checker._provision_provider_auth(auth_bytes)
            leaked = workspace / "leaked.txt"
            leaked.write_bytes(b"fake-test-credential")
            with self.assertRaisesRegex(checker.CheckError, "remain in disposable workspace"):
                checker._scrub_provider_auth(auth_path, auth_bytes)
            leaked.unlink()
            checker._scrub_provider_auth(auth_path, auth_bytes)


class LoadConfigTests(unittest.TestCase):
    def test_real_corpus_loads_for_its_own_reviewed_route(self) -> None:
        config = checker._load_config("opencode-go", "deepseek-v4-flash", "ao-mechanical-bulk")
        self.assertEqual(config["route"]["provider_model"], "opencode-go/deepseek-v4-flash")

    def test_unreviewed_route_is_rejected(self) -> None:
        with self.assertRaisesRegex(checker.CheckError, "no reviewed route"):
            checker._load_config("some-other-provider", "some-other-model", "ao-mechanical-bulk")


class CooldownTests(unittest.TestCase):
    def test_recent_report_blocks_unless_forced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checker.RUN_REPORT_ROOT = root
            (root / "opencode-opencode-go-deepseek-v4-flash-2026-01-01.json").write_text("{}")
            with self.assertRaisesRegex(checker.CheckError, "cooldown"):
                checker._cooldown_check("opencode-go", "deepseek-v4-flash", force=False)
            checker._cooldown_check("opencode-go", "deepseek-v4-flash", force=True)

    def test_no_prior_report_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checker.RUN_REPORT_ROOT = Path(temporary)
            checker._cooldown_check("opencode-go", "deepseek-v4-flash", force=False)


class EndToEndCheckerAndValidatorTests(unittest.TestCase):
    def test_real_fake_provider_end_to_end_check_and_validate(self) -> None:
        """Run the actual checker against a disposable fake-provider
        installation, then confirm the validator accepts its plain result."""
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as temporary:
            root = Path(temporary)
            var_root = root / "var"
            workspaces = var_root / "workspaces"
            workspaces.mkdir(parents=True)
            auth_source = var_root / "provider-auth.json"
            auth_source.write_text(json.dumps({"opencode-go": {"type": "api", "key": "fake-test-credential"}}, sort_keys=True, separators=(",", ":")))
            os.chmod(auth_source, 0o400)

            fake_bin = root / "bin"
            fake_bin.mkdir()
            opencode = fake_bin / "opencode"
            fake_provider = """#!/usr/bin/python3
import json, os, pathlib, sys
a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("1.18.4")
elif a[:1] == ["run"]:
    # Matches real captured OpenCode 1.18.4 output for opencode-go: no
    # requestID/requestId/providerRequestID field anywhere.
    print(json.dumps({"type": "step_finish", "sessionID": "ses_fake_0001", "part": {"type": "step-finish", "reason": "stop", "tokens": {"input": 100, "output": 50, "reasoning": 0}, "cost": 0.01}, "usage": {"baseline_units": 100, "observed_units": 150, "total_tokens": 150, "cost_usd": 0.01}}))
elif a[:1] == ["export"]:
    print(json.dumps({"info": {"id": a[1]}, "messages": [{"info": {"role": "assistant", "providerID": "opencode-go", "modelID": "deepseek-v4-flash", "finish": "stop"}, "parts": [{"type": "text"}, {"type": "step-finish"}]}]}))
else:
    raise SystemExit(2)
"""
            opencode.write_text(fake_provider.replace("#!/usr/bin/python3", f"#!{sys.executable}", 1))
            os.chmod(opencode, 0o755)
            runuser = fake_bin / "runuser"
            runuser.write_text(f"#!{sys.executable}\nimport os,sys\na=sys.argv[1:]; c=a[a.index('--')+1:]\nif c and c[0].endswith('/id') and c[1:]==['-Gn']: print('agentworker agentdispatch'); raise SystemExit(0)\nos.execvpe(c[0],c,os.environ)\n")
            os.chmod(runuser, 0o755)
            touch = fake_bin / "touch"
            shutil.copyfile("/run/current-system/sw/bin/touch", touch)
            os.chmod(touch, 0o755)
            mkdir = fake_bin / "mkdir"
            shutil.copyfile("/run/current-system/sw/bin/mkdir", mkdir)
            os.chmod(mkdir, 0o755)

            old = {name: getattr(checker, name) for name in ("AUTH_SOURCE", "WORKSPACE_PARENT", "OPENCODE", "RUNUSER", "TOUCH", "MKDIR", "RUN_REPORT_ROOT", "EXPECTED_WORKER_UID")}
            try:
                checker.AUTH_SOURCE = auth_source
                checker.WORKSPACE_PARENT = workspaces
                checker.OPENCODE = opencode
                checker.RUNUSER = runuser
                checker.TOUCH = touch
                checker.MKDIR = mkdir
                checker.RUN_REPORT_ROOT = root / "reports"
                checker.EXPECTED_WORKER_UID = os.getuid()
                result = checker.check_admission(provider="opencode-go", model="deepseek-v4-flash", agent="ao-mechanical-bulk", prompt="Reply with the bounded admission-check acknowledgement.", force=True)
            finally:
                for name, value in old.items():
                    setattr(checker, name, value)

            self.assertTrue(result["pass"])
            self.assertEqual(result["completion_events"], 1)
            report_path = Path(result["run_report"])
            self.assertTrue(report_path.is_file())
            self.assertNotIn(b"fake-test-credential", report_path.read_bytes())

            corpus = gate._load(gate.DEFAULT_CORPUS)
            gate.validate_result(json.loads(report_path.read_text()), corpus)


if __name__ == "__main__":
    unittest.main()
