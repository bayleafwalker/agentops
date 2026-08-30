"""A hook registered by bare path must be tracked executable, or it never runs.

Measured on 2026-08-30: `subagent-exit.sh` was registered on the workstation and had
written exactly two rows ever, both of them probes. The registration was correct and the
script was correct -- it was mode 644, so the harness's shell answered `Permission
denied` and exited 126 before the script read a byte of stdin.

That was invisible for two compounding reasons. `core.fileMode` is `false` in this
repository, so git never recorded that someone had chmod'd the working copy; the
workstation's hooks are 755 on disk and 644 in the index, and the difference does not
appear in `git status`. And devbox's `/projects/dev` is an independent clone, so it
received the *tracked* mode -- 644 -- for every one of them. Every hook there failed the
same way, which is why that host recorded nothing at all.

Verifying the script by running `bash <path>` hides exactly this: it proves the script
works and says nothing about whether the registration does. So the assertion here is on
the mode in the index, which is the thing that travels.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOKS = "templates/dispatch/hooks"

#: Hooks a settings file names as a command. These are executed, so they must carry the
#: bit. `auditctl-resolve.sh` is deliberately absent: it is *sourced* by its siblings,
#: never executed, and 644 is correct for it.
EXECUTED_HOOKS = (
    # Not registered as a hook: a CLI report, and `forge-context.sh` runs this one with
    # arguments and swallows the failure as "PROBE FAILED". Both are executed, so both
    # need the bit -- the seam is how a file is *used*, not whether a settings file
    # names it.
    "cost-summary.sh",
    "forge-credential.sh",
    "forge-context.sh",
    "forge-sandbox-detector.sh",
    "forge-sandbox-guard.sh",
    "gate-check.sh",
    "gate-log.sh",
    "log-session-cost.sh",
    "push-landed-check.sh",
    "session-binding.sh",
    "sprintctl-maintain-check.sh",
    "subagent-exit.sh",
)

SOURCED_NOT_EXECUTED = ("auditctl-resolve.sh",)


def _tracked_modes() -> dict[str, str]:
    out = subprocess.run(
        ["git", "ls-files", "-s", HOOKS],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    modes = {}
    for line in out.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) == 4:
            modes[Path(fields[3]).name] = fields[0]
    return modes


def test_every_executed_hook_is_tracked_executable() -> None:
    modes = _tracked_modes()
    missing = sorted(name for name in EXECUTED_HOOKS if modes.get(name) != "100755")
    assert not missing, (
        "these hooks are named as commands but are not tracked executable, so a fresh "
        f"clone runs them as 644 and the harness gets exit 126: {', '.join(missing)}. "
        "Fix with: git update-index --chmod=+x " + " ".join(f"{HOOKS}/{n}" for n in missing)
    )


def test_a_sourced_helper_is_not_required_to_be_executable() -> None:
    """The bit is a claim about how a file is used, not a tidiness rule.

    `auditctl-resolve.sh` is sourced into its callers' shells. Marking it executable
    would say something untrue about it, and this test exists so a later sweep does not
    "fix" it.
    """
    modes = _tracked_modes()
    for name in SOURCED_NOT_EXECUTED:
        assert modes.get(name) == "100644", f"{name} is sourced, not executed; 644 is correct"


def test_every_hook_this_test_names_actually_exists() -> None:
    """A list that drifts from the directory silently stops covering the new hook.

    `subagent-exit.sh` was the new hook, and it is the one that was broken.
    """
    present = {p.name for p in (ROOT / HOOKS).glob("*.sh")}
    named = set(EXECUTED_HOOKS) | set(SOURCED_NOT_EXECUTED)
    assert named <= present, f"named but absent: {sorted(named - present)}"
    unclassified = sorted(present - named)
    assert not unclassified, (
        "new hook script(s) not classified as executed or sourced: "
        f"{', '.join(unclassified)}. Add each to EXECUTED_HOOKS or SOURCED_NOT_EXECUTED."
    )
