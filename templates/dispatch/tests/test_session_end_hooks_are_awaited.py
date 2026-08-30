"""A session-end hook registered `async: true` is never awaited, so headless work loses it.

Measured 2026-08-30, on this host, with `claude -p "Reply with exactly: OK"`:

    --settings <file registering Stop -> log-session-cost.sh>              row written
    --settings <the same file, plus "async": true>                         no row
    no --settings, user settings carrying "async": true                    no row
    no --settings, after removing "async" from the user settings           row written

Same hook, same prompt, same directory; the only variable is the flag. The harness does
not wait for an async hook, and a headless process exits as soon as the turn ends, so the
write loses the race. An interactive session outlives its own hook and always wins it,
which is why 83 rows a day arrived from sessions a person was sitting in front of and
none at all from either headless host.

The predecessor's reading of this was that `Stop` does not fire headlessly and that no
publisher fix could recover unattended sessions. It fires. What did not happen was the
awaiting, and the fix is one key.

`SubagentStop` is included because it has the same shape at the same seam: it survives
today only because a subagent ends mid-session, with a parent still running to keep the
process alive. The last subagent of a headless run has no such parent.

`PostToolUse` is deliberately absent. It fires mid-session with the process guaranteed to
outlive it, and it is the one place where async is buying something real.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

#: Settings files this workspace declares. Absent ones are skipped, never silently
#: passed: on a machine that has none of them the assertion has no subject, and saying
#: so is the point of the whole session that produced this test.
CANDIDATES = (
    Path("/projects/dev/gitops-nixos/modules/system/hybrid-dispatch/claude-settings.json"),
    Path("/projects/dev/agentops/.claude/settings.local.json"),
    Path("/projects/dev/.claude/settings.json"),
    Path.home() / ".claude" / "settings.json",
)

AWAITED_EVENTS = ("Stop", "SubagentStop", "SessionEnd")


class SessionEndHooksAreAwaited(unittest.TestCase):
    def test_no_session_end_hook_is_registered_async(self):
        checked, offenders = [], []
        for path in CANDIDATES:
            if not path.is_file():
                continue
            try:
                settings = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:  # a broken settings file is its own defect
                offenders.append(f"{path}: unparseable ({exc})")
                continue
            checked.append(path)
            for event in AWAITED_EVENTS:
                for group in settings.get("hooks", {}).get(event, []):
                    for hook in group.get("hooks", []):
                        if hook.get("async"):
                            offenders.append(f"{path}: {event} -> {hook.get('command')}")
        if not checked:
            self.skipTest("no declared settings file present on this host")
        self.assertEqual(offenders, [], f"checked {len(checked)} settings files")


class CostRowWaitsForTheTurnToLand(unittest.TestCase):
    """Registering the hook synchronously exposed the other half of the same defect.

    At `Stop` the assistant turn is not on disk yet -- measured at 109 ms behind the
    hook in a headless run. The first four synchronous runs therefore wrote
    `assistant_msgs: 0, in: 0, out: 0, cost_usd: 0`: a row that exists and says
    nothing, which is the async loss wearing the opposite mask. A row nobody can tell
    apart from a free session is not a cheaper kind of record.

    So the hook waits, bounded, for the last conversational record to be a *closed*
    assistant turn. This test writes the transcript the way the harness does -- user
    first, assistant afterwards, late -- and requires the row to carry the turn.
    """

    HOOK = Path(__file__).parents[3] / "templates/dispatch/hooks/log-session-cost.sh"

    def test_row_carries_the_turn_that_lands_after_the_hook_starts(self):
        import os
        import subprocess
        import tempfile
        import textwrap
        import threading
        import time

        tmp = Path(tempfile.mkdtemp())
        try:
            transcript = tmp / "session.jsonl"
            transcript.write_text(json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "Reply with exactly: OK"},
                "timestamp": "2026-08-30T19:15:20.000Z",
            }) + "\n", encoding="utf-8")

            assistant = json.dumps({
                "type": "assistant",
                "timestamp": "2026-08-30T19:15:21.000Z",
                "message": {"role": "assistant", "model": "claude-fable-5",
                            "content": [{"type": "text", "text": "OK"}],
                            "usage": {"input_tokens": 2, "output_tokens": 4,
                                      "cache_creation_input_tokens": 0,
                                      "cache_read_input_tokens": 0}},
            })

            def append_late():
                time.sleep(0.3)
                with transcript.open("a", encoding="utf-8") as fh:
                    fh.write(assistant + "\n")

            writer = threading.Thread(target=append_late)
            log = tmp / "session-costs.jsonl"
            env = dict(os.environ, AGENTOPS_COST_LOG=str(log),
                       AGENTOPS_GATE_LOG_DIR=str(tmp / "state"), AUDITCTL_BIN="")
            event = json.dumps({"session_id": "probe", "transcript_path": str(transcript),
                                "cwd": "/projects/dev/agentops"})
            writer.start()
            subprocess.run(["bash", str(self.HOOK)], input=event, text=True, env=env,
                           check=True, capture_output=True)
            writer.join()

            row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(row["assistant_msgs"], 1, row)
            self.assertEqual(row["out"], 4, row)
            self.assertGreater(row["cost_usd"], 0, row)
            self.assertEqual(row["model"], "claude-fable-5", row)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
