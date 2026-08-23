"""Coordinator-authored oracle for spec row M-10 — a bounded PR body, and the
receipt on the branch.

Today the receipt file *is* the PR body. V5-M6a's receipt is 165 515 bytes and
GitHub caps a body at 65 536, so ``gh pr create`` fails on every candidate with
``GraphQL: Body is too long``. The receipt is that large because it carries the
worker's full stdout, which since the hand-pass is the only transcript there is.
M-10 puts that transcript on the packet branch, under a secret scan, and gives
the PR a generated, bounded body of its own.

Written against the M-10 spec only: the driver has no capture step, no secret
scan and no body generator today, so every test here fails.

Deliberately kept out of this file, because it is the packet's traced
``starts_red`` command: any real ``git``, any real subprocess with a foreign
cwd, and any network. The fake runner answers every command; everything on disk
lives in a ``TemporaryDirectory``. (This is the same split M-9 made when its
real-git proof moved to ``test_realgit_dispatch_commit.py``.)
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


driver = _load_module("dispatch_release_body_subject", SCRIPTS / "dispatch_release.py")


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


class CaptureTests(_DriverFixture):
    """§3 and the amendment — capture, split, or withhold."""

    # 4. The step vocabulary. M-10 supersedes the four names M-9 shipped: the
    # capture is a part of the PR step that can fail on its own, and it leads,
    # because the captured files have to be in the commit.
    def test_pr_step_names_lead_with_the_capture(self):
        self.assertEqual(driver.PR_STEP_NAMES, PR_STEP_NAMES)

    # 5. The two files land inside the worktree, under the already-ignored
    # evidence directory, and they are there before anything is staged --
    # otherwise the commit does not carry them and the push does not either.
    def test_clean_receipt_is_captured_into_the_worktree_before_the_commit(self):
        packet = self._packet()
        worktree = self._worktree(packet)
        runner = self._runner(
            stdout=build_stdout(), watch=worktree / CAPTURED_RECEIPT,
        )
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        self.assertTrue(
            (worktree / CAPTURED_RECEIPT).is_file(), f"no {CAPTURED_RECEIPT} in the worktree",
        )
        self.assertTrue(
            (worktree / CAPTURED_STDOUT).is_file(), f"no {CAPTURED_STDOUT} in the worktree",
        )
        i_stage = runner.index_of(
            lambda c, _: c[0] == "git" and "add" in c and "remote" not in c
        )
        self.assertGreaterEqual(i_stage, 0, "nothing was staged")
        self.assertTrue(
            runner.watched[i_stage],
            "the capture had not been written when the worktree was staged, so the "
            "commit cannot carry it",
        )

    # 6. report["pr"]["receipt"] says which of the two things happened, and
    # names the path a reader has to follow to find the transcript.
    def test_report_records_the_capture_and_its_repo_relative_path(self):
        packet = self._packet()
        self._worktree(packet)
        runner = self._runner(stdout=build_stdout())
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        record = self._pr_receipt(report)
        self.assertIs(record.get("captured"), True)
        self.assertEqual(
            str(record.get("path")).replace("\\", "/"), CAPTURED_RECEIPT,
            "the recorded path is not the repo-relative captured receipt",
        )

    # 7. The amendment's tightened clause: the worker's stdout never goes
    # inside JSON. Embedding it produced a 288 KB single line and broke
    # ripgrep's 64 KB record limit inside every worker's clone -- the defect
    # that cost V5-M9 three dispatches.
    def test_the_captured_receipt_carries_no_transcript_and_names_its_sidecar(self):
        stdout = build_stdout(target_bytes=3 * 1024 * 1024)
        packet = self._packet()
        worktree = self._worktree(packet)
        runner = self._runner(stdout=stdout)
        code, _ = self._drive(packet, runner)
        self.assertEqual(code, 0)
        raw = self._captured(worktree, CAPTURED_RECEIPT)
        self.assertNotIn(MARKER, raw, "the transcript is still inside the captured JSON")
        for line in raw.splitlines():
            self.assertLess(
                len(line.encode("utf-8")), 65536,
                "a line of the captured receipt is past ripgrep's 64 KB record limit",
            )
        # "removed" has to be distinguishable from "never captured": the marker
        # left behind names the sidecar and the byte count.
        self.assertIn(SIDECAR_NAME, raw, "the captured receipt does not name its sidecar")
        self.assertIn(
            str(len(stdout.encode("utf-8"))), raw,
            "the captured receipt does not carry the transcript's byte count",
        )
        # Every other field survives.
        captured = json.loads(raw)
        self.assertEqual(captured["task_id"], TASK_ID)
        self.assertIn("driver_steps", captured)
        self.assertIn(str(TOKENS), raw, "the spend did not survive the split")

    # 8. And the transcript itself lands beside it as text, where its own
    # newlines survive.
    def test_the_sidecar_is_the_transcript_with_its_newlines_intact(self):
        stdout = build_stdout(target_bytes=512 * 1024)
        packet = self._packet()
        worktree = self._worktree(packet)
        runner = self._runner(stdout=stdout)
        code, _ = self._drive(packet, runner)
        self.assertEqual(code, 0)
        text = self._captured(worktree, CAPTURED_STDOUT)
        self.assertEqual(
            text.splitlines(), stdout.splitlines(),
            "the sidecar is not the transcript, line for line",
        )

    # 9. "M-10 adds a copy inside the worktree, it does not move the original."
    # The receipt beside the worktree keeps its stdout: it is the coordinator's
    # own artifact and nothing in this row touches it.
    def test_the_receipt_beside_the_worktree_is_unchanged_and_keeps_its_stdout(self):
        self._require_capture_step()
        packet = self._packet()
        self._worktree(packet)
        runner = self._runner(stdout=build_stdout())
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        original = Path(report["receipt_path"])
        self.assertTrue(original.is_file())
        self.assertIn(
            MARKER, original.read_text(encoding="utf-8"),
            "the original receipt lost its stdout; the row adds a copy, it does not move it",
        )

    # 10. Fail closed. A withheld transcript costs a reader one hop; a leaked
    # credential costs a rotation. The scan runs over the receipt *and* the
    # stdout, so a secret in either withholds both files -- and the run still
    # finishes green, because a secret in a transcript must not turn a green
    # packet into a failed one.
    def test_a_secret_in_either_input_withholds_both_files_and_the_run_still_passes(self):
        # "neither file was written" is vacuously true while nothing is ever
        # written, so the capture has to exist for this to be a withholding.
        self._require_capture_step()
        for where in ("stdout", "receipt"):
            with self.subTest(where=where):
                secret = SECRETS["github"]
                packet = self._packet()
                worktree = self._worktree(packet)
                runner = self._runner(
                    stdout=build_stdout() + (secret + "\n" if where == "stdout" else ""),
                    receipt_extra={"note": secret} if where == "receipt" else None,
                )
                code, report = self._drive(packet, runner)
                self.assertEqual(code, 0, "a withheld transcript is not a failed packet")
                self.assertFalse(
                    (worktree / CAPTURED_RECEIPT).exists(), "the receipt was written anyway",
                )
                self.assertFalse(
                    (worktree / CAPTURED_STDOUT).exists(), "the sidecar was written anyway",
                )
                self.assertTrue(report["pr"]["opened"], "the PR was not opened")

    # 11. The withholding is recorded by name, and the record quotes nothing.
    def test_the_withholding_records_the_finding_names_and_never_the_secret(self):
        secret = SECRETS["slack"]
        packet = self._packet()
        self._worktree(packet)
        runner = self._runner(stdout=build_stdout() + secret + "\n")
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        record = self._pr_receipt(report)
        self.assertIs(record.get("captured"), False)
        findings = record.get("findings")
        self.assertIsInstance(findings, list, "the withholding names no patterns")
        self.assertTrue(findings, "the withholding names no patterns")
        self.assertNotIn(
            secret, json.dumps(report["pr"]),
            "report['pr'] quotes the secret it withheld the file for",
        )

    # 12. A failed capture is the hand-off failing: it names itself, escalates
    # once as the PR step, exits non-zero, and reaches neither the commit nor
    # anything after it. A file where the directory has to go is the cheapest
    # unwritable path there is, and needs no chmod to be one for root too.
    def test_a_failed_capture_names_itself_and_stops_before_the_commit(self):
        packet = self._packet()
        worktree = self._worktree(packet)
        (worktree / "docs").write_text("not a directory\n", encoding="utf-8")
        runner = self._runner(stdout=build_stdout())
        code, report = self._drive(packet, runner)
        self.assertNotEqual(
            code, 0, "an unwritable capture path was not a failure of the PR step",
        )
        self.assertEqual(report["pr"].get("failed_step"), "receipt-capture")
        self.assertEqual(runner.commits(), [])
        self.assertEqual(runner.stages(), [])
        self.assertEqual(runner.remote_adds(), [])
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])
        audit = runner.audit_calls()
        self.assertEqual(len(audit), 1, "the failure escalates exactly once")
        self.assertEqual(audit[0][1:4], ["add", "--type", "workflow.escalation"])
        self.assertEqual(report["escalation"]["metadata"]["step"], "pr")
        self.assertFalse(report["pr"]["opened"])

    # 13. A dry run is a rehearsal: it captures nothing, commits nothing,
    # pushes nothing, opens nothing -- and still reports the gh it would run.
    def test_dry_run_captures_nothing_and_still_reports_the_gh_it_would_run(self):
        self._require_capture_step()
        packet = self._packet()
        worktree = self._worktree(packet)
        runner = self._runner(stdout=build_stdout())
        code, report = self._drive(packet, runner, dry_run=True)
        self.assertEqual(code, 0)
        self.assertFalse((worktree / CAPTURE_DIR).exists(), "a dry run captured a receipt")
        self.assertEqual(runner.commits(), [])
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])
        self.assertTrue(report["pr"]["skipped"])
        self.assertEqual(report["pr"]["command"][:3], ["gh", "pr", "create"])

    # 14. A disposition the driver cannot vouch for is work that is not handed
    # onward, and a committed transcript on the packet branch is a hand-off.
    # Attempt 2 in the packet is what makes this a skip rather than the
    # gate-red-twice stop.
    def test_non_candidate_disposition_reaches_no_capture(self):
        self._require_capture_step()
        packet = self._packet(attempt=2)
        worktree = self._worktree(packet)
        runner = self._runner(
            exits={"gate": 2}, disposition="coordinator_review_required",
            stdout=build_stdout(),
        )
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        self.assertTrue(report["pr"]["skipped"])
        self.assertFalse((worktree / CAPTURE_DIR).exists())

    # 15. Every L-2 stop condition means the driver hands nothing onward.
    def test_every_stop_condition_reaches_no_capture(self):
        self._require_capture_step()
        cases = {
            "release-boundary": ({"release_boundary": True}, {}),
            "command-not-allowed": (
                {"allowed_command_ids": ["pytest"], "oracle": {"starts_red": "curl-the-internet"}},
                {},
            ),
            "path-outside-writable": (
                {"writable_patch_paths": ["src/**"]},
                {"touched_paths": ["src/a.py", "infra/prod.tf"]},
            ),
        }
        for condition, (extra, gate_extra) in cases.items():
            with self.subTest(condition=condition):
                packet = self._packet(**extra)
                worktree = self._worktree(packet)
                runner = self._runner(gate_extra=gate_extra, stdout=build_stdout())
                code, report = self._drive(packet, runner)
                self.assertEqual(report["stop"]["condition"], condition)
                self.assertNotEqual(code, 0)
                self.assertFalse((worktree / CAPTURE_DIR).exists())

    def test_gate_red_twice_reaches_no_capture(self):
        self._require_capture_step()
        packet = self._packet()
        worktree = self._worktree(packet)
        for _ in range(2):
            runner = self._runner(
                exits={"gate": 2}, disposition="coordinator_review_required",
                stdout=build_stdout(),
            )
            code, report = self._drive(packet, runner)
        self.assertEqual(report["stop"]["condition"], "gate-red-twice")
        self.assertNotEqual(code, 0)
        self.assertFalse((worktree / CAPTURE_DIR).exists())


class BodyTests(_DriverFixture):
    """§4 — the generated body, and the two properties that matter most."""

    def _drive_with_stdout(self, stdout: str, **kw):
        packet = self._packet()
        self._worktree(packet)
        runner = self._runner(stdout=stdout)
        code, report = self._drive(packet, runner, **kw)
        self.assertEqual(code, 0)
        return report

    # 16. The whole row in one assertion: V5-M6a's receipt was 165 515 bytes
    # and every candidate died on "GraphQL: Body is too long". The fixture
    # feeds a receipt far past the limit -- a three-megabyte transcript, twenty
    # times the receipt that broke it -- and the body still has to fit.
    def test_the_body_is_under_the_github_limit_against_an_enormous_receipt(self):
        stdout = build_stdout(target_bytes=3 * 1024 * 1024)
        report = self._drive_with_stdout(stdout)
        original = Path(report["receipt_path"]).read_text(encoding="utf-8")
        self.assertGreater(
            len(original.encode("utf-8")), BODY_LIMIT,
            "the fixture is not feeding an oversized receipt; it proves nothing",
        )
        body = self._body_text(report)
        self.assertLess(
            len(body.encode("utf-8")), BODY_LIMIT,
            f"the body is {len(body.encode('utf-8'))} bytes; gh caps it at {BODY_LIMIT}",
        )

    # 17. The repo is public; no transcript in a PR body, ever. The marker is
    # planted in the middle of the worker's stdout, so a body that carries any
    # window of the transcript wide enough to matter carries it too.
    def test_the_body_contains_no_transcript(self):
        stdout = build_stdout(target_bytes=3 * 1024 * 1024)
        report = self._drive_with_stdout(stdout)
        body = self._body_text(report)
        self.assertNotIn(MARKER, body, "the worker's transcript is in the PR body")

    # 18. What the body is *for*. A bounded body that says nothing is bounded
    # and useless: the six things in §4 are what a reviewer opens the PR to see.
    def test_the_body_carries_task_commit_disposition_gates_cost_and_receipt_path(self):
        report = self._drive_with_stdout(build_stdout())
        body = self._body_text(report)
        flat = body.replace(",", "")
        self.assertIn(TASK_ID, body, "the body does not name the task")
        self.assertTrue(
            STARTING_COMMIT in body or STARTING_COMMIT[:12] in body,
            "the body does not carry the packet's starting_commit",
        )
        self.assertIn("candidate", body, "the body does not carry the disposition")
        self.assertIn(str(TOKENS), flat, "the body does not carry the token spend")
        self.assertIn(f"{COST_USD:.2f}"[:4], flat, "the body does not carry the cost")
        self.assertIn(
            CAPTURED_RECEIPT, body.replace("\\", "/"),
            "the body does not point at the captured receipt",
        )
        # The gate table: every gate name, each rendered with its own boolean,
        # and true rendered differently from false.
        for name, value in GATES.items():
            rows = [line for line in body.splitlines() if name in line]
            self.assertTrue(rows, f"the gate table has no row for {name}")
            row = rows[0].lower()
            wanted, unwanted = (
                (TRUE_WORDS, FALSE_WORDS) if value else (FALSE_WORDS, TRUE_WORDS)
            )
            self.assertTrue(
                any(word in row for word in wanted),
                f"the {name} row does not render {value}: {rows[0]!r}",
            )
            self.assertFalse(
                any(word in row for word in unwanted),
                f"the {name} row renders {not value}: {rows[0]!r}",
            )

    # 19. When the scan fires there is no path to point at, so the body says so
    # rather than pointing at a file that was never written -- and it does not
    # become the place the secret leaks instead.
    def test_a_withheld_transcript_is_said_so_in_the_body(self):
        secret = SECRETS["aws"]
        report = self._drive_with_stdout(build_stdout() + secret + "\n")
        body = self._body_text(report)
        self.assertIn("withheld", body.lower(), "the body does not note the withholding")
        self.assertNotIn(secret, body, "the withheld secret is in the PR body")
        self.assertNotIn(CAPTURED_RECEIPT, body.replace("\\", "/"))


class SubStepNameTests(_DriverFixture):
    """The amendment's extra property, learned from M-9.

    M-9's sub-steps indexed ``PR_STEP_NAMES`` positionally. When the tuple
    gained a leading entry, every one of them reported the step *before* it: a
    failed push said ``remote-add`` and a failed ``gh`` said ``push``, which is
    exactly the confusion ``failed_step`` exists to prevent. Driving each of the
    five in turn is the fixture that would have caught it.
    """

    def _fail(self, failing: str):
        packet = self._packet()
        worktree = self._worktree(packet)
        exits: dict[str, int] = {}
        if failing == "receipt-capture":
            # An unwritable capture path: a file where the directory must go.
            (worktree / "docs").write_text("not a directory\n", encoding="utf-8")
        else:
            exits[failing] = 128
        runner = self._runner(exits=exits, stdout=build_stdout())
        return self._drive(packet, runner, ) + (runner,)

    def test_each_pr_sub_step_failure_reports_its_own_name(self):
        self._require_capture_step()
        for failing in PR_STEP_NAMES:
            with self.subTest(failing=failing):
                code, report, runner = self._fail(failing)
                self.assertNotEqual(code, 0, f"a failed {failing} exited zero")
                self.assertEqual(
                    report["pr"].get("failed_step"), failing,
                    f"a failed {failing} reported {report['pr'].get('failed_step')!r}",
                )
                self.assertFalse(report["pr"]["opened"])
                audit = runner.audit_calls()
                self.assertEqual(len(audit), 1, "the failure escalates exactly once")
                self.assertEqual(report["escalation"]["metadata"]["step"], "pr")

    def test_a_failure_stops_every_sub_step_after_it(self):
        self._require_capture_step()
        reached = {
            "receipt-capture": lambda r: bool(r.stages() or r.commits()),
            "commit": lambda r: bool(r.remote_adds()),
            "remote-add": lambda r: bool(r.pushes()),
            "push": lambda r: bool(r.gh_calls()),
        }
        for failing, went_further in reached.items():
            with self.subTest(failing=failing):
                _code, _report, runner = self._fail(failing)
                self.assertFalse(
                    went_further(runner), f"the PR step carried on past a failed {failing}",
                )


if __name__ == "__main__":
    unittest.main()
