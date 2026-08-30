"""A terminal reason is read off the transcript's terminal record, never off its prose.

`subagent-exit.sh` shipped on 2026-08-29 classifying by matching "session limit" /
"rate limit" / "timed out" / "cancelled" against the last three assistant text blocks,
on the stated grounds that a usage limit reaches the agent only as a localized
wall-clock string. That is false at the artifact. The terminating record carries
`isApiErrorMessage: true`, `apiErrorStatus: 429`, `error: "rate_limit"`, and -- in
transcripts written since roughly 2026-08 -- a `quotaLimits` object whose `resetsAt` is
the exact epoch second the localized string renders.

Measured 2026-08-30 over all 353 subagent transcripts on this host: the text match
returned 76 non-`completed` verdicts against 19 real ones. All 38 of its `timeout`
verdicts, all 5 of its `cancelled` verdicts and 14 of its 33 `usage-limit` verdicts were
spurious, and every one of them came from a subagent that *completed* and whose final
report discussed rate limiting, timeouts or cancellation. Prose about a failure is
indistinguishable from the failure, so this is structural and not a tuning problem.
There were no false negatives in either direction, so reading the record costs nothing.

The false-positive cases below are therefore the point of this file, not padding: the
happy path passed both before and after.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
HOOK = ROOT / "templates/dispatch/hooks/subagent-exit.sh"
CORPUS = Path.home() / ".claude" / "projects"

#: Verified 2026-08-28 against agent-a5d642b86112f09ec.jsonl: this instant is what the
#: transcript's own text rendered as "resets 12:30am (Europe/Helsinki)".
RESETS_AT_EPOCH = 1787952600
RESETS_AT_ISO = "2026-08-28T21:30:00Z"


def _assistant(text: str, **extra) -> str:
    rec = {
        "type": "assistant",
        "isSidechain": True,
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }
    rec.update(extra)
    return json.dumps(rec)


def _quota_death(text: str, quota: dict | None) -> str:
    """The shape a 429 termination actually has on disk."""
    extra = {
        "isApiErrorMessage": True,
        "apiErrorStatus": 429,
        "error": "rate_limit",
        "message": {"role": "assistant", "model": "<synthetic>",
                    "content": [{"type": "text", "text": text}]},
    }
    if quota is not None:
        extra["quotaLimits"] = quota
    return _assistant(text, **extra)


class SubagentExitTerminalReason(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.capture = self.tmp / "capture.jsonl"
        stub = self.tmp / "auditctl"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            "while [[ $# -gt 0 ]]; do\n"
            '  case "$1" in --metadata) printf %s\\\\n "$2" >> "$CAPTURE"; shift 2;; *) shift;; esac\n'
            "done\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        self.stub = stub

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lines: list[str] | None, *, transcript_present: bool = True) -> dict:
        path = self.tmp / "agent-probe.jsonl"
        if transcript_present:
            path.write_text("\n".join(lines or []) + "\n", encoding="utf-8")
        env = dict(os.environ, AUDITCTL_BIN=str(self.stub), CAPTURE=str(self.capture))
        event = json.dumps({"session_id": "probe", "transcript_path": str(path),
                            "cwd": "/projects/dev/agentops"})
        subprocess.run(["bash", str(HOOK)], input=event, text=True, env=env, check=True,
                       capture_output=True)
        rows = self.capture.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 1, "the hook must publish exactly one row")
        return json.loads(rows[0])

    # -- the case the producer exists for -------------------------------------------

    def test_quota_rejection_is_usage_limit_and_carries_the_reset_instant(self):
        row = self._run([
            _assistant("Working on the manifest survey."),
            _quota_death(
                "You've hit your session limit · resets 12:30am (Europe/Helsinki)",
                {"status": "rejected", "resetsAt": RESETS_AT_EPOCH,
                 "rateLimitType": "five_hour"},
            ),
        ])
        self.assertEqual(row["terminal_reason"], "usage-limit")
        self.assertEqual(row["reset_at"], RESETS_AT_ISO)
        self.assertEqual(row["reset_source"], "quotaLimits.resetsAt")

    def test_older_429_without_quota_limits_says_so_rather_than_guessing(self):
        """Transcripts before ~2026-08 carry the 429 and no `quotaLimits`.

        Seven of this host's nineteen recorded limit deaths are of this shape. The
        reason is still certain; only the instant is not, and the record says which.
        """
        row = self._run([
            _quota_death("You've hit your session limit · resets 1:20pm (Europe/Helsinki)", None),
        ])
        self.assertEqual(row["terminal_reason"], "usage-limit")
        self.assertIsNone(row["reset_at"])
        self.assertEqual(row["reset_source"], "unparsed-local-string")

    # -- the false positives that motivated the rewrite ------------------------------

    def test_a_completed_report_about_rate_limiting_is_not_a_usage_limit(self):
        row = self._run([
            _assistant(
                "**WAF/rate limiting:** no Cloudflare WAF rules are recorded in the repo. "
                "Rate limiting is in-application and DB-backed."
            ),
        ])
        self.assertEqual(row["terminal_reason"], "completed")
        self.assertIsNone(row["reset_source"])

    def test_a_completed_report_about_timeouts_is_not_a_timeout(self):
        row = self._run([
            _assistant("Retries, concurrency limits and per-call timeout handling are covered."),
        ])
        self.assertEqual(row["terminal_reason"], "completed")

    def test_a_completed_report_about_cancellation_is_not_a_cancellation(self):
        row = self._run([
            _assistant("Cancellation mid-stream must not leave the container wedged."),
        ])
        self.assertEqual(row["terminal_reason"], "completed")

    # -- the rest of the vocabulary ---------------------------------------------------

    def test_user_interrupt_marker_is_cancelled(self):
        """No subagent transcript on this host ends this way; the marker is structural."""
        row = self._run([
            _assistant("Reading the manifest now."),
            json.dumps({"type": "user", "message": {"role": "user",
                                                    "content": "[Request interrupted by user]"}}),
        ])
        self.assertEqual(row["terminal_reason"], "cancelled")

    def test_non_quota_api_error_is_process_exit(self):
        row = self._run([
            _assistant("Overloaded", isApiErrorMessage=True, apiErrorStatus=529,
                       error="overloaded_error"),
        ])
        self.assertEqual(row["terminal_reason"], "process-exit")

    def test_missing_transcript_is_crash_inferred(self):
        row = self._run(None, transcript_present=False)
        self.assertEqual(row["terminal_reason"], "crash-inferred")

    def test_harness_bookkeeping_after_the_terminal_record_does_not_hide_it(self):
        """A parent's file-history-snapshot / queue-operation rows follow the last turn.

        Selecting the literal last line would read one of those and see nothing wrong.
        """
        row = self._run([
            _quota_death("You've hit your session limit · resets 12:30am (Europe/Helsinki)",
                         {"status": "rejected", "resetsAt": RESETS_AT_EPOCH}),
            json.dumps({"type": "file-history-snapshot", "messageId": "x"}),
            json.dumps({"type": "queue-operation", "operation": "drain"}),
        ])
        self.assertEqual(row["terminal_reason"], "usage-limit")


class AgainstThisHostsTranscripts(unittest.TestCase):
    """The fixtures above are shaped like production; these *are* production.

    A contract whose only instances are its own committed fixtures is the defect class
    this producer was built to close, so the assertion runs against every real subagent
    transcript on the host and is skipped -- never silently passed -- where there is
    none. On the workstation, 2026-08-30, that is 353 transcripts and 19 limit deaths.
    """

    @staticmethod
    def _structured_reason(lines: list[str]) -> str:
        for line in reversed(lines[-12:]):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") not in ("assistant", "user"):
                continue
            if rec.get("isApiErrorMessage"):
                quota = rec.get("quotaLimits") or {}
                if (rec.get("apiErrorStatus") == 429 or rec.get("error") == "rate_limit"
                        or quota.get("status") == "rejected"):
                    return "usage-limit"
                return "process-exit"
            return "completed"
        return "completed"

    def test_hook_verdicts_equal_the_records(self):
        transcripts = sorted(CORPUS.glob("*/*/subagents/*.jsonl")) if CORPUS.is_dir() else []
        if not transcripts:
            self.skipTest(f"no subagent transcripts under {CORPUS}")
        tmp = Path(tempfile.mkdtemp())
        try:
            capture = tmp / "capture.jsonl"
            stub = tmp / "auditctl"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                "while [[ $# -gt 0 ]]; do\n"
                '  case "$1" in --metadata) printf %s\\\\n "$2" >> "$CAPTURE"; shift 2;; *) shift;; esac\n'
                "done\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            env = dict(os.environ, AUDITCTL_BIN=str(stub), CAPTURE=str(capture))
            mismatches = []
            for path in transcripts:
                capture.write_text("", encoding="utf-8")
                event = json.dumps({"session_id": "probe", "transcript_path": str(path),
                                    "cwd": "/projects/dev/agentops"})
                subprocess.run(["bash", str(HOOK)], input=event, text=True, env=env,
                               check=True, capture_output=True)
                got = json.loads(capture.read_text(encoding="utf-8").splitlines()[0])
                want = self._structured_reason(
                    path.read_text(errors="replace").splitlines())
                if got["terminal_reason"] != want:
                    mismatches.append((path.name, got["terminal_reason"], want))
            self.assertEqual(mismatches, [], f"over {len(transcripts)} real transcripts")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
