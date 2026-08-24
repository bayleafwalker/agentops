"""Coordinator-authored oracle for spec row M-10a - the secret scan.

A module-level scan over text that returns the *names* of the patterns that
matched and never the matched text. It is a pure function with no control
flow: nothing here drives the driver, and nothing here depends on the capture
step or the body generator. M-10a is the first of the three packets M-10 was
split into; M-10c and M-10b both depend on this function existing.

Written against the M-10 spec only: the driver has no scan_for_secrets today,
so every test here fails.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"

#: The packet branch, and a base branch that shares nothing with it.
BRANCH = "hybrid/t-driver"
BASE_BRANCH = "trunk-never-pushed"

TASK_ID = "T-DRIVER"
STARTING_COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
COMMITTED_SHA = "fedcba9876543210fedcba9876543210fedcba98"
RESOLVED_URL = "git@example.invalid:coordinator/repo.git"

#: GitHub's cap on a pull request body. The number the whole row exists for.
BODY_LIMIT = 65536

#: The five parts of the PR step, in the only order that works. M-10 adds the
#: capture and puts it *first*: the captured files have to be in the commit.
PR_STEP_NAMES = ("receipt-capture", "commit", "remote-add", "push", "pr-create")

#: Where the capture lands, relative to the repository root. The directory
#: already carries an ``.ignore`` (coordinator work, §3c hand-pass #69), which
#: is why this oracle neither writes nor asserts one.
CAPTURE_DIR = f"docs/evidence/receipts/{TASK_ID}"
CAPTURED_RECEIPT = f"{CAPTURE_DIR}/receipt.json"
CAPTURED_STDOUT = f"{CAPTURE_DIR}/worker-stdout.txt"
SIDECAR_NAME = "worker-stdout.txt"

#: The name this oracle fixes for the module-level secret scan. It takes text
#: and returns the *names* of the patterns that matched — never the matched
#: text, because the finding is going into a report that may be read anywhere.
SCAN_FUNCTION = "scan_for_secrets"

#: Planted in the worker's stdout. Distinctive enough that "it appears nowhere
#: in the body" is a real claim about the body and not about coincidence.
MARKER = "TRANSCRIPT-MARKER-9d1f4a7c-DO-NOT-LEAK"

#: The worker's spend, as ``hybrid_dispatch.worker_spend`` reports it on the
#: run stage's receipt. Both numbers are distinctive so "the body carries the
#: cost" cannot pass on a substring that was going to be there anyway.
COST_USD = 4.257131
TOKENS = 131346

#: The gate table, as ``post_gates`` reports it under ``evidence.gates``. One
#: gate is false on purpose: a body that renders every row as "true" is not a
#: gate table. ``passed`` is supplied true independently, because the driver
#: reads only ``passed`` to decide redness and the fixture needs the PR step to
#: run in order to see the table at all.
GATES = {
    "diff-nonempty": True,
    "diff-scope-respected": True,
    "protected-paths-untouched": True,
    "registered-commands-green": False,
    "worktree-state-captured": True,
}

#: Tokens a body may reasonably use to render each boolean. The spec fixes the
#: table, not its wording, so the oracle accepts any of these — but it does not
#: accept a body that renders true and false the same way.
TRUE_WORDS = ("true", "yes", "pass", "passed", "ok", "green", "✓", "✔")
FALSE_WORDS = ("false", "no", "fail", "failed", "red", "✗", "✘", "×")

#: Sample credentials, assembled at runtime from fragments so that no complete
#: secret-shaped literal sits in this file for a scanner to find. None of them
#: is real.
SECRETS: dict[str, str] = {
    "github": "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "aws": "AKIA" + "IOSFODNN7EXAMPLE",
    "pem": "-----BEGIN RSA PRIVATE" + " KEY-----",
    "slack": "xoxb-" + "123456789012-1234567890123-" + "AbCdEfGhIjKlMnOpQrStUvWx",
    "bearer": "Authorization: Bearer " + ("s3cr3tv4lue" * 3),
    "assignment": "api_key = " + '"' + ("z" * 32) + '"',
}

#: Ordinary transcript prose. Nothing in it is credential-shaped, and a scan
#: that returns anything for it is a scan that will withhold every transcript.
CLEAN_TEXT = (
    "the worker read the packet and edited two files\n"
    "pytest reported 563 passed in 27.10s\n"
    "the gate was green and the disposition is candidate\n"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_secretscan_subject", SCRIPTS / "dispatch_release.py")


def build_stdout(marker: str = MARKER, target_bytes: int = 0) -> str:
    """A worker transcript: JSONL step parts, with ``marker`` planted once.

    ``target_bytes`` of zero yields a short one. The bounded-body fixtures pass
    several megabytes, which is what the row is about: V5-M6a's receipt was
    165 515 bytes and a body is capped at 65 536.
    """
    filler = json.dumps({"part": {"type": "text", "text": "x" * 200}})
    lines = [json.dumps({"part": {"type": "step-start"}})]
    while sum(len(line) + 1 for line in lines) < target_bytes:
        lines.append(filler)
    lines.insert(len(lines) // 2, json.dumps({"part": {"type": "text", "text": marker}}))
    return "\n".join(lines) + "\n"


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd.

    ``exits`` is keyed by stage name, by ``gh``, and by the PR step names, so a
    fixture can fail exactly one of them. ``stdout`` is what the run stage's
    receipt carries as ``worker.stdout`` — the transcript M-10 has to move onto
    the branch. ``watch`` is a path whose existence is snapshotted before every
    command, which is how this oracle observes that the capture happened
    *before* the commit without running a real git.
    """

    def __init__(
        self,
        auditctl_bin: str,
        exits: dict[str, int] | None = None,
        disposition: str = "candidate",
        resolve_url: str | None = RESOLVED_URL,
        gate_extra: dict[str, Any] | None = None,
        stdout: str = "",
        receipt_extra: dict[str, Any] | None = None,
        watch: Path | None = None,
    ):
        self.auditctl_bin = auditctl_bin
        self.exits = exits or {}
        self.disposition = disposition
        self.resolve_url = resolve_url
        self.gate_extra = gate_extra if gate_extra is not None else {"gates": dict(GATES)}
        self.stdout = stdout
        self.receipt_extra = receipt_extra or {}
        self.watch = watch
        self.calls: list[tuple[list[str], Path | None]] = []
        self.watched: list[bool] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        self.watched.append(bool(self.watch is not None and self.watch.exists()))
        if cmd[0] == self.auditctl_bin:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(
                cmd, self.exits.get("pr-create", 0), "https://example/pr/1\n", "",
            )
        if cmd[0] == "git":
            return self._git(cmd)
        return self._stage(cmd)

    def _stage(self, cmd):
        step = cmd[-1]
        code = self.exits.get(step, 0)
        payload: dict[str, Any] = {
            "schema_version": "agentops-hybrid-receipt/v1",
            "stage": step,
            "task_id": TASK_ID,
        }
        if step == "run":
            # Exactly where hybrid_dispatch puts them: the transcript under
            # ``worker``, the spend beside it.
            payload["worker"] = {"exit_code": 0, "stdout": self.stdout, "stderr": ""}
            payload["spend"] = {
                "cost_usd": COST_USD, "tokens": TOKENS, "cost_reported": True,
                "within_cap": True, "within_hard_token_ceiling": True,
            }
        if step == "gate":
            payload["disposition"] = self.disposition
            payload["evidence"] = dict(self.gate_extra)
            payload["evidence"].setdefault("passed", True)
        if step == "receipt":
            payload.update(self.receipt_extra)
        return subprocess.CompletedProcess(cmd, code, json.dumps(payload), "boom" if code else "")

    def _git(self, cmd):
        if "commit" in cmd:
            code = self.exits.get("commit", 0)
            out = f"[{BRANCH} {COMMITTED_SHA[:7]}] committed\n" if not code else ""
            return subprocess.CompletedProcess(cmd, code, out, "boom" if code else "")
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, COMMITTED_SHA + "\n", "")
        if "remote" in cmd and "add" not in cmd:
            if self.resolve_url is None:
                return subprocess.CompletedProcess(cmd, 2, "", "error: No such remote 'origin'")
            return subprocess.CompletedProcess(cmd, 0, self.resolve_url + "\n", "")
        if "remote" in cmd and "add" in cmd:
            name = "remote-add"
        elif "push" in cmd:
            name = "push"
        elif "add" in cmd:
            name = "commit"
        else:
            name = "git"
        code = self.exits.get(name, 0)
        return subprocess.CompletedProcess(cmd, code, "", "boom" if code else "")

    def git_calls(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.calls if c[0] == "git"]

    def commits(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "commit" in c]

    def stages(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "add" in c and "remote" not in c]

    def remote_adds(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "remote" in c and "add" in c]

    def pushes(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "push" in c]

    def gh_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == "gh"]

    def audit_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == self.auditctl_bin]

    def index_of(self, predicate) -> int:
        for i, (cmd, cwd) in enumerate(self.calls):
            if predicate(cmd, cwd):
                return i
        return -1


class _DriverFixture(unittest.TestCase):
    """Temp dirs, a reachable auditctl path, and a packet — shared setUp."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()
        # A path that exists is all write_escalation needs to treat the sink as
        # reachable; the runner is fake, so nothing is ever executed.
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    # -- the guard ---------------------------------------------------------
    #
    # A fixture that asserts the capture did *not* happen proves nothing while
    # there is no capture step at all, and one that reads a generated body
    # errors on a missing key instead of failing on the absent behaviour. Every
    # test below pins what it is guarding first, the way M-9's oracle does.

    def _require_capture_step(self) -> None:
        self.assertEqual(
            driver.PR_STEP_NAMES[0], "receipt-capture",
            "the PR step has no receipt-capture to reach, skip or fail",
        )

    def _require_scan(self):
        self.assertTrue(
            hasattr(driver, SCAN_FUNCTION),
            f"the driver has no module-level {SCAN_FUNCTION}()",
        )
        return getattr(driver, SCAN_FUNCTION)

    def _captured(self, worktree: Path, relative: str) -> str:
        """The text of a captured file, or a legible failure instead of an
        IOError: "the capture never ran" is the behaviour being asserted."""
        path = worktree / relative
        self.assertTrue(path.is_file(), f"nothing was captured at {relative}")
        return path.read_text(encoding="utf-8")

    def _pr_receipt(self, report: dict[str, Any]) -> dict[str, Any]:
        self.assertIsInstance(report.get("pr"), dict, "report['pr'] is not a record")
        self.assertIn(
            "receipt", report["pr"],
            "report['pr'] does not say whether the receipt was captured or withheld",
        )
        return report["pr"]["receipt"]

    def _body_text(self, report: dict[str, Any]) -> str:
        self.assertIsInstance(report.get("pr"), dict, "report['pr'] is not a record")
        self.assertIn("body_file", report["pr"], "report['pr'] names no body file")
        body_file = Path(report["pr"]["body_file"])
        self.assertTrue(body_file.is_file(), f"the body file was not written: {body_file}")
        self.assertNotEqual(
            body_file.resolve(), Path(report["receipt_path"]).resolve(),
            "the body file is still the receipt; that is the bug this row removes",
        )
        # And never the captured copy either: the body is generated.
        self.assertNotEqual(body_file.name, "receipt.json")
        cmd = report["pr"]["command"]
        self.assertIn("--body-file", cmd, f"gh pr create carries no --body-file: {cmd}")
        self.assertEqual(
            Path(cmd[cmd.index("--body-file") + 1]).resolve(), body_file.resolve(),
            "gh pr create points somewhere other than the generated body",
        )
        return body_file.read_text(encoding="utf-8")

    # -- packets and driving ----------------------------------------------

    def _packet(self, **extra: Any) -> Path:
        packet = {
            "task_id": TASK_ID,
            "repo_id": "repo-x",
            "starting_commit": STARTING_COMMIT,
            "worktree": {"root": str(self.tmp / "wt"), "branch": BRANCH},
        }
        packet.update(extra)
        path = self.tmp / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def _worktree(self, packet_path: Path) -> Path:
        worktree = driver.worktree_path(json.loads(packet_path.read_text(encoding="utf-8")))
        worktree.mkdir(parents=True, exist_ok=True)
        return worktree

    def _runner(self, **kw) -> FakeRunner:
        return FakeRunner(str(self.auditctl), **kw)

    def _drive(self, packet_path: Path, runner, **kw):
        kw.setdefault("dry_run", False)
        kw.setdefault("base_branch", BASE_BRANCH)
        return driver.drive(
            packet_path, self.repo_root, runner=runner, auditctl_bin=str(self.auditctl), **kw,
        )


class SecretScanTests(_DriverFixture):
    """§2 — a module-level scan that names patterns and quotes nothing."""

    # 1. Every kind the spec enumerates is detected, and the finding names
    # never carry the matched text: the finding goes into a report that may be
    # read anywhere, so a scan that echoes the credential has leaked it.
    def test_scan_detects_each_kind_and_never_returns_the_matched_text(self):
        scan = self._require_scan()
        for kind, secret in SECRETS.items():
            with self.subTest(kind=kind):
                findings = scan(f"prelude\n{secret}\npostlude\n")
                self.assertIsInstance(findings, list, "the scan returns a list of names")
                self.assertTrue(findings, f"{kind} was not detected")
                for name in findings:
                    self.assertIsInstance(name, str)
                    self.assertNotIn(secret, name, f"the finding quotes the secret: {name!r}")
                    self.assertNotIn(
                        secret[-12:], name, f"the finding quotes the secret: {name!r}",
                    )

    # 2. The names have to tell the kinds apart, or "the pattern names" is just
    # a count with extra steps.
    def test_the_pattern_kinds_get_distinguishable_names(self):
        scan = self._require_scan()
        seen: dict[str, frozenset[str]] = {}
        for kind, secret in SECRETS.items():
            seen[kind] = frozenset(scan(f"prelude\n{secret}\npostlude\n"))
        for a in seen:
            for b in seen:
                if a < b:
                    self.assertNotEqual(
                        seen[a], seen[b], f"{a} and {b} report the same names: {seen[a]}",
                    )

    # 3. Ordinary transcript prose is clean. A scan that fires on it withholds
    # every transcript, which is the same as never capturing one.
    def test_clean_text_returns_no_findings(self):
        scan = self._require_scan()
        self.assertEqual(scan(CLEAN_TEXT), [])
        self.assertEqual(scan(build_stdout(target_bytes=64 * 1024)), [])


if __name__ == "__main__":
    unittest.main()
