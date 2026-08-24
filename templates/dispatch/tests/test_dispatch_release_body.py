"""Coordinator-authored oracle for spec row M-10b - the bounded PR body.

Today the receipt file *is* the PR body. V5-M6a's receipt is 165 515 bytes and
GitHub caps a body at 65 536, so gh pr create fails on every candidate with
"GraphQL: Body is too long". M-10b gives the PR a generated, bounded body of
its own and points --body-file at it.

Depends on M-10a and M-10c: the body has to point at the captured receipt and
has to say so when the scan withheld the transcript. It is therefore the last
of the three packets M-10 was split into, not the second.

Written against the M-10 spec only: the driver has no body generator today, so
every test here fails.
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
            # The gate NAME is read out of the row before the boolean words
            # are looked for, because three of the five names contain one:
            # "diff-nonempty" holds "no", "registered-commands-green" holds
            # "green", and "worktree-state-captured" holds "red". Scanning the
            # whole row makes those three unsatisfiable -- no rendering that
            # puts a name and its boolean on one line can pass -- so this
            # fixture would have failed every correct implementation.
            rendered = rows[0].lower().replace(name.lower(), "")
            wanted, unwanted = (
                (TRUE_WORDS, FALSE_WORDS) if value else (FALSE_WORDS, TRUE_WORDS)
            )
            self.assertTrue(
                any(word in rendered for word in wanted),
                f"the {name} row does not render {value}: {rows[0]!r}",
            )
            self.assertFalse(
                any(word in rendered for word in unwanted),
                f"the {name} row renders {not value}: {rows[0]!r}",
            )

    # 18b. The gate runs over the worker's commit; acceptance happens over the
    # merged PR, and the coordinator routinely adds commits to the branch after
    # the gate has run -- oracle reconciliations, evidence, and on one occasion
    # a change to a protected path. PR #74's gate table truthfully reported
    # protected-paths-untouched while that PR modified a protected path. The
    # body must therefore name the commit the table was computed over, and say
    # that later commits were not covered. Widening the gate is the wrong fix:
    # the coordinator's commits are legitimately outside writable_patch_paths.
    def test_the_body_names_the_commit_the_gate_covered_and_scopes_it(self):
        report = self._drive_with_stdout(build_stdout())
        body = self._body_text(report)
        self.assertIn(
            COMMITTED_SHA[:12], body,
            "the body does not name the worker commit the gate ran over",
        )
        lowered = body.lower()
        self.assertTrue(
            "not gated" in lowered or "were not covered" in lowered
            or "not covered" in lowered,
            "the body does not say that later commits on the branch were not gated",
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


if __name__ == "__main__":
    unittest.main()
