from __future__ import annotations

import io
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import tempfile
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/run_opencode_qualification.py"
VALIDATOR = ROOT / "templates/dispatch/scripts/validate_opencode_qualification.py"
HELPER = ROOT / "templates/dispatch/scripts/verify_and_consume_opencode_qualification.py"
SUDOERS = ROOT / "templates/dispatch/provider-qualification/opencode-qualification.sudoers"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = _load(SCRIPT, "run_opencode_qualification")


class FakeProcess:
    def __init__(self, events: list[dict[str, object]], returncode: int = 0):
        self.stdout = io.StringIO("\n".join(json.dumps(event) for event in events) + "\n")
        self.returncode = returncode
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: int = 0) -> int:
        return self.returncode


def _event(tokens: int) -> dict[str, object]:
    return {
        "type": "step_finish",
        "providerID": "opencode-go",
        "modelID": "deepseek-v4-flash",
        "finish": "stop",
        "sessionID": "ses_test_0001",
        "providerRequestID": "req_test_0001",
        "usage": {"baseline_units": 100, "observed_units": 200, "total_tokens": tokens, "cost_usd": 0.01},
    }


class OneShotRunnerTests(unittest.TestCase):
    def test_one_contained_invocation_and_exact_boundary_are_accepted(self) -> None:
        calls: list[list[str]] = []
        process = FakeProcess([_event(runner.SOFT_TOKENS)])

        def popen(command, **kwargs):
            calls.append(command)
            return process

        result = runner.execute_once(
            command=[str(runner.RUNUSER), "--user", runner.WORKER_USER, "--", str(runner.OPENCODE), "run", "bounded", "--agent", "ao-mechanical-bulk", "--format", "json"],
            environment={"OPENCODE_CONFIG_CONTENT": "{}"},
            popen=popen,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["observed_tokens"], runner.SOFT_TOKENS)
        self.assertFalse(process.killed)

    def test_final_repository_byte_pins_are_self_consistent(self) -> None:
        corpus_path = ROOT / "templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        self.assertEqual(runner._file_digest(corpus_path), (ROOT / "templates/dispatch/provider-qualification/corpus.sha256").read_text(encoding="ascii").strip())
        self.assertEqual(runner._file_digest(SCRIPT), corpus["live_run"]["runner_digest"])
        self.assertEqual(runner._file_digest(ROOT / "templates/dispatch/scripts/verify_and_consume_opencode_qualification.py"), (ROOT / "templates/dispatch/provider-qualification/verify-consume.sha256").read_text(encoding="ascii").strip())
        for name, digest in corpus["live_run"]["preflight_evidence"].items():
            self.assertEqual(runner._file_digest(ROOT / "templates/dispatch/provider-qualification/preflight-evidence" / name), digest)

    def test_auth_contract_is_native_opencode_not_runner_invented(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("OPENCODE_AUTH_FILE", source)
        self.assertIn("OPENCODE_AUTH_CONTENT", source)
        self.assertIn(".local" + '" / "share"', source)
        self.assertIn('"opencode-go"', source)
        self.assertIn('"type"', source)
        self.assertIn('"key"', source)

    def test_soft_and_hard_overruns_terminate_before_success(self) -> None:
        for tokens, expected in ((runner.SOFT_TOKENS + 1, "soft"), (runner.HARD_TOKENS + 1, "hard")):
            process = FakeProcess([_event(tokens)])
            with self.subTest(tokens=tokens), self.assertRaisesRegex(runner.RunnerError, expected):
                runner.execute_once(
                    command=[str(runner.RUNUSER), "--user", runner.WORKER_USER, "--", str(runner.OPENCODE), "run", "bounded"],
                    environment={},
                    popen=lambda *args, **kwargs: process,
                )
            self.assertTrue(process.killed)

    def test_cost_overrun_terminates_before_a_success_record(self) -> None:
        event = _event(1)
        event["usage"]["cost_usd"] = runner.MAX_COST_USD + 0.01
        process = FakeProcess([event])
        with self.assertRaisesRegex(runner.RunnerError, "cost ceiling"):
            runner.execute_once(
                command=[str(runner.RUNUSER), "--user", runner.WORKER_USER, "--", str(runner.OPENCODE), "run", "bounded"],
                environment={},
                popen=lambda *args, **kwargs: process,
            )
        self.assertTrue(process.killed)

    def test_second_provider_event_and_missing_usage_fail_closed(self) -> None:
        for events, message in (([_event(1), _event(2)], "exactly one"), ([_event(0) | {"usage": {}}], "positive bounded|token count|usage structure")):
            process = FakeProcess(events)
            with self.subTest(message=message), self.assertRaisesRegex(runner.RunnerError, message):
                runner.execute_once(
                    command=[str(runner.RUNUSER), "--user", runner.WORKER_USER, "--", str(runner.OPENCODE), "run", "bounded"],
                    environment={},
                    popen=lambda *args, **kwargs: process,
                )

    def test_validator_has_no_shared_secret_authentication_or_private_key_argument(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8").lower()
        self.assertNotIn("hmac", source)
        self.assertNotIn("runner-key-file", source)
        self.assertIn("ssh-keygen", source)
        self.assertIn("runner_public_key_path", source)

    def test_privilege_separated_consumer_has_no_private_key_or_caller_root_interface(self) -> None:
        source = HELPER.read_text(encoding="utf-8").lower()
        self.assertNotIn("runner.key", source)
        self.assertNotIn("private_key", source)
        self.assertIn("consume=true", source)

    def test_os_identity_boundary_denies_worker_read_of_key_and_limits_sudo_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / "runner.key"
            key.write_text("private-test-material")
            os.chmod(key, 0o400)
            denied = subprocess.run(["/run/current-system/sw/bin/runuser", "--user", "agentworker", "--", "/run/current-system/sw/bin/cat", str(key)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(denied.returncode, 0)
        policy = SUDOERS.read_text(encoding="utf-8")
        self.assertIn("(root)", policy)
        self.assertIn("agentops-opencode-qualification-verify-consume", policy)
        self.assertNotIn("runner.key", policy)
        self.assertNotIn("/bin/sh", policy)

    def test_real_worker_uid_traverses_native_auth_tree_and_other_uid_is_denied(self) -> None:
        if os.geteuid() != 0:
            proof = r'''
import atexit, json, os, pathlib, shutil, subprocess, sys
base = pathlib.Path(sys.argv[1])
os.chmod(base, 0o711)
workspace = base / "workspace"
atexit.register(lambda: shutil.rmtree(workspace, ignore_errors=True))
workspace.mkdir(mode=0o700)
os.chown(workspace, 1101, 1101)
auth_dir = workspace / ".local" / "share" / "opencode"
auth_dir.mkdir(mode=0o700, parents=True)
for directory in (workspace / ".local", workspace / ".local" / "share", auth_dir):
    os.chown(directory, 1101, 1101)
    os.chmod(directory, 0o700)
auth = auth_dir / "auth.json"
auth.write_text('{"opencode-go":{"type":"api","key":"uid-proof"}}')
os.chown(auth, 1101, 1101)
os.chmod(auth, 0o400)
def read_as(uid):
    return subprocess.run(["/run/current-system/sw/bin/setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups", "--", "/run/current-system/sw/bin/cat", str(auth)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
worker = read_as(1101)
other = read_as(1102)
assert worker.returncode == 0 and json.loads(worker.stdout) == {"opencode-go": {"type": "api", "key": "uid-proof"}}, worker.stderr
assert other.returncode != 0
for path in (workspace / ".local", workspace / ".local" / "share", auth_dir, auth):
    info = path.lstat()
    assert info.st_uid == 1101
    assert (info.st_mode & 0o777) == (0o400 if path == auth else 0o700)
shutil.rmtree(workspace)
'''
            with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                result = subprocess.run([
                    "/run/current-system/sw/bin/unshare", "--user",
                    "--map-users", f"0:{os.getuid()}:1", "--map-users", "1101:100000:2",
                    "--map-groups", f"0:{os.getgid()}:1", "--map-groups", "1101:100000:2",
                    sys.executable, "-c", proof, temporary,
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
            return
        worker = pwd.getpwnam(runner.WORKER_USER)
        other = pwd.getpwnam("agent")
        self.assertNotEqual(worker.pw_uid, other.pw_uid)
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            os.chmod(temporary, 0o711)
            state = Path(temporary) / "qualification"
            workspace_parent = state / "workspaces"
            workspace = workspace_parent / "run-real-uid-proof"
            auth_dir = workspace / ".local" / "share" / "opencode"
            state.mkdir(mode=0o711)
            workspace_parent.mkdir(mode=0o711)
            workspace.mkdir(mode=0o700)
            os.chown(workspace, worker.pw_uid, worker.pw_gid)
            auth_dir.mkdir(mode=0o700, parents=True)
            for directory in (workspace / ".local", workspace / ".local" / "share", auth_dir):
                os.chown(directory, worker.pw_uid, worker.pw_gid)
                os.chmod(directory, 0o700)
            auth = auth_dir / "auth.json"
            auth.write_text('{"opencode-go":{"type":"api","key":"uid-proof"}}')
            os.chown(auth, worker.pw_uid, worker.pw_gid)
            os.chmod(auth, 0o400)
            readable = subprocess.run([runner.RUNUSER, "--user", runner.WORKER_USER, "--", "/run/current-system/sw/bin/cat", str(auth)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
            denied = subprocess.run([runner.RUNUSER, "--user", "agent", "--", "/run/current-system/sw/bin/cat", str(auth)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
            self.assertEqual(readable.returncode, 0, readable.stderr)
            self.assertEqual(json.loads(readable.stdout), {"opencode-go": {"type": "api", "key": "uid-proof"}})
            self.assertNotEqual(denied.returncode, 0)
            for path in (workspace / ".local", workspace / ".local" / "share", auth_dir, auth):
                info = path.lstat()
                self.assertEqual(info.st_uid, worker.pw_uid)
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o400 if path == auth else 0o700)

    def test_provider_auth_provisioning_rolls_back_each_partial_failure_phase(self) -> None:
        phases = ("create", "chown", "chmod", "check")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir(mode=0o700)
            old_active, old_owner, old_worker = runner.ACTIVE_WORKSPACE_ROOT, runner.EXPECTED_OWNER_UID, runner.EXPECTED_WORKER_UID
            runner.ACTIVE_WORKSPACE_ROOT = workspace
            runner.EXPECTED_OWNER_UID = os.getuid()
            runner.EXPECTED_WORKER_UID = os.getuid()
            try:
                for phase in phases:
                    with self.subTest(phase=phase):
                        auth_root = workspace / ".local"
                        target = auth_root / "share" / "opencode" / "auth.json"
                        if phase == "create":
                            original_mkdir = Path.mkdir
                            def fail_mkdir(path, *args, **kwargs):
                                if Path(path) == auth_root:
                                    raise OSError("injected create failure")
                                return original_mkdir(path, *args, **kwargs)
                            patcher = mock.patch.object(Path, "mkdir", new=fail_mkdir)
                        elif phase == "chown":
                            original_chown = os.chown
                            def fail_chown(path, uid, gid):
                                if Path(path) == target:
                                    raise OSError("injected chown failure")
                                return original_chown(path, uid, gid)
                            patcher = mock.patch.object(runner.os, "chown", new=fail_chown)
                        elif phase == "chmod":
                            original_chmod = os.chmod
                            def fail_chmod(path, mode):
                                if Path(path) == target:
                                    raise OSError("injected chmod failure")
                                return original_chmod(path, mode)
                            patcher = mock.patch.object(runner.os, "chmod", new=fail_chmod)
                        else:
                            def fail_check(*args, **kwargs):
                                raise runner.RunnerError("injected check failure")
                            patcher = mock.patch.object(runner, "_check_path", new=fail_check)
                        with patcher, self.assertRaises(runner.RunnerError):
                            runner._provision_provider_auth(b'{"opencode-go":{"type":"api","key":"rollback-proof"}}')
                        self.assertFalse(target.exists())
                        self.assertFalse(auth_root.exists())
            finally:
                runner.ACTIVE_WORKSPACE_ROOT, runner.EXPECTED_OWNER_UID, runner.EXPECTED_WORKER_UID = old_active, old_owner, old_worker

    def test_sanitized_export_projection_matches_lifecycle_evidence_shape(self) -> None:
        exported = {"info": {"id": "ses_test_0001"}, "messages": [{"info": {"role": "assistant", "providerID": "opencode-go", "modelID": "deepseek-v4-flash", "finish": "stop"}, "parts": [{"type": "text", "text": "secret transcript must not survive"}, {"type": "step-finish"}]}]}
        projection = runner._parse_sanitized_export(json.dumps(exported), "ses_test_0001")
        self.assertEqual(projection["events"][0]["part_types"], ["text", "step-finish"])
        self.assertNotIn("secret transcript", json.dumps(projection))

    def test_real_fake_provider_end_to_end_runner_admission_and_replay_rejection(self) -> None:
        """Run the actual one-shot runner against a disposable fake-provider installation."""
        gate = _load(VALIDATOR, "validate_opencode_qualification_e2e")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = root / "etc/agentops/opencode-qualification"
            state = root / "var/lib/agentops/opencode-qualification"
            for path in (install, state, state / "records", state / "ledger", state / "evidence", state / "workspaces", install / "preflight-evidence"):
                path.mkdir(parents=True, exist_ok=True); os.chmod(path, 0o711 if path == state / "workspaces" else 0o700)
            copies = (
                ("templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json", "corpus.json"),
                ("templates/dispatch/hybrid/opencode.hybrid.json", "opencode.hybrid.json"),
                ("templates/dispatch/harness-profiles/opencode-nixpkgs-devbox-1.18.4.json", "profile.json"),
                ("templates/dispatch/hybrid/hybrid-dispatch.v1.json", "hybrid-dispatch.v1.json"),
                ("agentops.dispatch.json", "agentops.dispatch.json"),
            )
            for source, name in copies:
                target = install / name; shutil.copyfile(ROOT / source, target); os.chmod(target, 0o400)
            manifest = json.loads((ROOT / "agentops.dispatch.json").read_text())
            policy = json.loads((ROOT / "templates/dispatch/hybrid/hybrid-dispatch.v1.json").read_text())
            config = json.loads((ROOT / "templates/dispatch/hybrid/opencode.hybrid.json").read_text())
            hybrid = gate._load_module(ROOT / "templates/dispatch/scripts/hybrid_dispatch.py", "e2e_overlay")
            overlay = hybrid.build_overlay({"route": "mechanical_bulk", "allowed_command_ids": ["agentops.dispatch.tests"]}, manifest, policy, config)
            static = {
                "capability.json": {probe: "pass" for probe in runner.REQUIRED_PROBES},
                "lifecycle.json": {probe: "pass" for probe in runner.REQUIRED_PROBES},
                "overlay.json": {"route": "mechanical_bulk", "agent": "ao-mechanical-bulk", "allowed_command_ids": ["agentops.dispatch.tests"], "model_override": None, "overlay": overlay},
                "workspace.json": {"manifest_digest": "sha256:" + hashlib.sha256((ROOT / "agentops.dispatch.json").read_bytes()).hexdigest(), "repository_opt_in": True, "provider_workspace_opt_in": True},
            }
            for name, payload in static.items():
                path = install / "preflight-evidence" / name; shutil.copyfile(ROOT / "templates/dispatch/provider-qualification/preflight-evidence" / name, path); os.chmod(path, 0o400)

            key = state / "runner.key"
            subprocess.run([runner.SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            public = state / "runner.pub"; shutil.copyfile(Path(str(key) + ".pub"), public)
            allowed = state / "allowed_signers"; allowed.write_text(f'{runner.RUNNER_ID} namespaces="{runner.SIGNATURE_NAMESPACE}" {public.read_text().strip()}\n')
            auth_source = state / "provider-auth.json"
            auth_source.write_text(json.dumps({"opencode-go": {"type": "api", "key": "fake-test-credential"}}, sort_keys=True, separators=(",", ":")))
            for path, mode in ((key, 0o400), (public, 0o444), (allowed, 0o444), (auth_source, 0o400)): os.chmod(path, mode)
            fake_bin = root / "bin"; fake_bin.mkdir()
            opencode = fake_bin / "opencode"
            fake_provider = """#!/usr/bin/python3
import json, os, pathlib, sys
a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("1.18.4")
elif a[:1] == ["run"]:
    state = pathlib.Path(os.environ["XDG_DATA_HOME"]) / "opencode"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    (state / "opencode-stable.db").write_bytes(b"fake non-secret sqlite state")
    (state / "opencode-stable.db-wal").write_bytes(b"fake non-secret wal state")
    (state / "opencode.log").write_bytes(b"fake non-secret log state")
    (state / "repos").mkdir(mode=0o700, exist_ok=True)
    native = json.loads((state / "auth.json").read_text())
    assert native == {"opencode-go": {"type": "api", "key": "fake-test-credential"}}
    assert json.loads(os.environ["OPENCODE_AUTH_CONTENT"]) == native
    print(json.dumps({"type": "step_finish", "sessionID": "ses_fake_0001", "part": {"type": "step-finish", "requestID": "req_fake_0001", "tokens": {"input": 100, "output": 50, "reasoning": 50}, "cost": 0.01}}))
elif a[:1] == ["export"]:
    print(json.dumps({"info": {"id": a[1]}, "messages": [{"info": {"role": "assistant", "providerID": "opencode-go", "modelID": "deepseek-v4-flash", "finish": "stop"}, "parts": [{"type": "text"}, {"type": "step-finish"}]}]}))
else:
    raise SystemExit(2)
"""
            opencode.write_text(fake_provider)
            opencode.write_text(opencode.read_text().replace("#!/usr/bin/python3", f"#!{sys.executable}", 1))
            os.chmod(opencode, 0o755)
            runuser = fake_bin / "runuser"
            runuser.write_text("#!/usr/bin/python3\nimport os,sys\na=sys.argv[1:]; c=a[a.index('--')+1:]\nif c and c[0].endswith('/id') and c[1:]==['-Gn']: print('agentworker agentdispatch'); raise SystemExit(0)\nif c and c[0].endswith('/test') and c[1:2]==['-w'] and c[2].endswith('/records'): raise SystemExit(1)\nos.execvpe(c[0],c,os.environ)\n")
            runuser.write_text(runuser.read_text().replace("#!/usr/bin/python3", f"#!{sys.executable}", 1))
            os.chmod(runuser, 0o755)
            tools = {}
            for name in ("touch", "mkdir", "ssh-keygen"):
                target = fake_bin / name; source = Path(runner.SSH_KEYGEN if name == "ssh-keygen" else f"/run/current-system/sw/bin/{name}"); shutil.copyfile(source, target); os.chmod(target, 0o755); tools[name] = target
            runner_install = fake_bin / "runner"; shutil.copyfile(SCRIPT, runner_install); os.chmod(runner_install, 0o755)
            installed_corpus = json.loads((install / "corpus.json").read_text())
            installed_corpus["live_run"].update({"runner_public_key_path": str(public), "runner_allowed_signers_path": str(allowed), "record_root": str(state / "records"), "consumption_ledger_root": str(state / "ledger"), "evidence_root": str(state / "evidence"), "provider_auth_source": str(auth_source), "runner_path": str(runner_install), "runner_digest": runner._file_digest(runner_install), "opencode_path": str(opencode), "opencode_digest": runner._file_digest(opencode)})
            os.chmod(install / "corpus.json", 0o600)
            (install / "corpus.json").write_text(json.dumps(installed_corpus, sort_keys=True, separators=(",", ":")))
            os.chmod(install / "corpus.json", 0o400)
            corpus_pin = install / "corpus.sha256"; corpus_pin.write_text(runner._file_digest(install / "corpus.json") + "\n"); os.chmod(corpus_pin, 0o400)
            names = ("INSTALL_ROOT", "CORPUS", "CORPUS_DIGEST_FILE", "CONFIG", "PROFILE", "POLICY", "MANIFEST", "STATIC_EVIDENCE_ROOT", "PRIVATE_KEY", "AUTH_SOURCE", "PUBLIC_KEY", "ALLOWED_SIGNERS", "RECORD_ROOT", "LEDGER_ROOT", "ATTEMPT_SENTINEL", "EVIDENCE_ROOT", "WORKSPACE_PARENT", "OPENCODE", "RUNUSER", "TOUCH", "MKDIR", "SSH_KEYGEN", "RUNNER_PATH", "EXPECTED_OWNER_UID", "EXPECTED_EUID", "EXPECTED_WORKER_UID", "ACTIVE_WORKSPACE_ROOT")
            old = {name: getattr(runner, name) for name in names}
            pins = ("PINNED_CONFIG_DIGEST", "PINNED_PROFILE_DIGEST", "PINNED_POLICY_DIGEST", "PINNED_MANIFEST_DIGEST", "PINNED_PUBLIC_KEY_DIGEST", "PINNED_ALLOWED_SIGNERS_DIGEST")
            old_pins = {name: getattr(runner, name) for name in pins}
            try:
                runner.INSTALL_ROOT = install; runner.CORPUS = install / "corpus.json"; runner.CORPUS_DIGEST_FILE = corpus_pin; runner.CONFIG = install / "opencode.hybrid.json"; runner.PROFILE = install / "profile.json"; runner.POLICY = install / "hybrid-dispatch.v1.json"; runner.MANIFEST = install / "agentops.dispatch.json"; runner.STATIC_EVIDENCE_ROOT = install / "preflight-evidence"
                runner.PRIVATE_KEY = key; runner.AUTH_SOURCE = auth_source; runner.PUBLIC_KEY = public; runner.ALLOWED_SIGNERS = allowed; runner.RECORD_ROOT = state / "records"; runner.LEDGER_ROOT = state / "ledger"; runner.ATTEMPT_SENTINEL = state / "ledger/packet.attempted"; runner.EVIDENCE_ROOT = state / "evidence"; runner.WORKSPACE_PARENT = state / "workspaces"; runner.OPENCODE = opencode; runner.RUNUSER = runuser; runner.TOUCH = tools["touch"]; runner.MKDIR = tools["mkdir"]; runner.SSH_KEYGEN = tools["ssh-keygen"]; runner.RUNNER_PATH = runner_install
                runner.EXPECTED_OWNER_UID = os.getuid(); runner.EXPECTED_EUID = os.geteuid(); runner.EXPECTED_WORKER_UID = os.getuid(); runner.ACTIVE_WORKSPACE_ROOT = runner.WORKSPACE_ROOT
                for name, path in (("CORPUS", runner.CORPUS), ("CONFIG", runner.CONFIG), ("PROFILE", runner.PROFILE), ("POLICY", runner.POLICY), ("MANIFEST", runner.MANIFEST)):
                    setattr(runner, "PINNED_" + name + "_DIGEST", runner._file_digest(path))
                runner.PINNED_PUBLIC_KEY_DIGEST = runner._file_digest(public); runner.PINNED_ALLOWED_SIGNERS_DIGEST = runner._file_digest(allowed)
                verification = runner.verify_installation_only()
                self.assertFalse(verification["side_effects"])
                self.assertFalse((state / "ledger" / "packet.attempted").exists())
                self.assertEqual(list((state / "workspaces").iterdir()), [])
                output = runner.run_one_shot()
            finally:
                for name, value in old.items(): setattr(runner, name, value)
                for name, value in old_pins.items(): setattr(runner, name, value)
            self.assertEqual({path.name for path in Path(output["evidence_root"]).iterdir()}, {"provider.json", "usage.json", "containment.json", "capability.json", "lifecycle.json", "overlay.json", "workspace.json", "receipt.json"})
            self.assertTrue((state / "ledger" / "packet.attempted").is_file())
            workspace = state / "workspaces" / output["run_id"]
            runtime = workspace / ".local" / "share" / "opencode"
            self.assertEqual(set(workspace.iterdir()), {workspace / ".config", workspace / ".cache", workspace / ".local"})
            self.assertEqual({path.name for path in runtime.iterdir()}, {"opencode-stable.db", "opencode-stable.db-wal", "opencode.log", "repos"})
            self.assertFalse((workspace / ".local" / "share" / "opencode" / "auth.json").exists())
            self.assertNotIn(b"fake-test-credential", b"".join(path.read_bytes() for path in runtime.rglob("*") if path.is_file()))
            for output_root in (Path(output["evidence_root"]), state / "records", state / "ledger"):
                for output_file in output_root.rglob("*"):
                    if output_file.is_file():
                        self.assertNotIn(b"fake-test-credential", output_file.read_bytes())

            corpus = json.loads((install / "corpus.json").read_text())
            corpus["live_run"].update({"runner_public_key_fingerprint": gate._sha256_file(public), "runner_public_key_path": str(public), "runner_allowed_signers_fingerprint": gate._sha256_file(allowed), "runner_allowed_signers_path": str(allowed), "record_root": str(state / "records"), "consumption_ledger_root": str(state / "ledger"), "evidence_root": str(state / "evidence"), "provider_auth_source": str(auth_source), "runner_path": str(runner_install), "runner_digest": runner._file_digest(runner_install), "opencode_path": str(opencode), "opencode_digest": runner._file_digest(opencode)})
            corpus_path = root / "corpus-e2e.json"; corpus_path.write_text(json.dumps(corpus))
            validator_names = ("EXPECTED_RUNNER_PUBLIC_KEY_PATH", "EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH", "EXPECTED_RECORD_ROOT", "EXPECTED_LEDGER_ROOT", "EXPECTED_EVIDENCE_ROOT", "EXPECTED_AUTH_SOURCE", "EXPECTED_RUNNER_PATH", "EXPECTED_OPENCODE_PATH", "EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT", "EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT", "EXPECTED_OWNER_UID")
            validator_old = {name: getattr(gate, name) for name in validator_names}
            try:
                gate.EXPECTED_RUNNER_PUBLIC_KEY_PATH = str(public); gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH = str(allowed); gate.EXPECTED_RECORD_ROOT = str(state / "records"); gate.EXPECTED_LEDGER_ROOT = str(state / "ledger"); gate.EXPECTED_EVIDENCE_ROOT = str(state / "evidence"); gate.EXPECTED_AUTH_SOURCE = str(auth_source); gate.EXPECTED_RUNNER_PATH = str(runner_install); gate.EXPECTED_OPENCODE_PATH = str(opencode); gate.EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT = gate._sha256_file(public); gate.EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT = gate._sha256_file(allowed); gate.EXPECTED_OWNER_UID = os.getuid()
                helper = _load(HELPER, "verify_and_consume_opencode_qualification_e2e")
                helper.CORPUS = corpus_path; helper.PUBLIC_KEY = public; helper.ALLOWED_SIGNERS = allowed; helper._verify_installed_material = lambda: None; helper._validator = lambda: gate
                result = helper.verify_and_consume(Path(output["receipt"]), Path(output["evidence_root"]), Path(output["record"]))
                self.assertTrue(result["candidate_ready"]); self.assertFalse(result["qualification_eligible"])
                with self.assertRaisesRegex(gate.QualificationError, "consumed"):
                    helper.verify_and_consume(Path(output["receipt"]), Path(output["evidence_root"]), Path(output["record"]))
            finally:
                for name, value in validator_old.items(): setattr(gate, name, value)


if __name__ == "__main__":
    unittest.main()
