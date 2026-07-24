"""Experimental Beads mutation bridge; not production integration code."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request


def call_restate(base: str, item_id: str, method: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}/WorkItemClaim/{item_id}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"accepted": False, "reason": f"restate-http-{error.code}"}


def run_bd(command: list[str], env: dict[str, str], cwd: str) -> dict:
    completed = subprocess.run(command, env=env, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode:
        return {
            "accepted": False,
            "reason": "beads-mutation-failed",
            "detail": completed.stderr.strip()[-500:],
        }
    return {"accepted": True}


def transition(
    *,
    restate_base: str,
    beads_binary: str,
    beads_dir: str,
    dolt_root: str,
    item_id: str,
    owner: str,
    proof: str,
    status: str = "in_progress",
) -> dict:
    """Require an accepted Restate decision before the real Beads mutation."""
    receipt = call_restate(
        restate_base,
        item_id,
        "mutate",
        {"proof": proof, "mutation": f"planner-status:{status}"},
    )
    if not receipt.get("accepted"):
        return {"accepted": False, "reason": "adapter-proof-rejected"}
    environment = {**os.environ, "DOLT_ROOT_PATH": dolt_root}
    # `BEADS_DIR` is this harness's workspace variable, whereas Beads expects
    # it to name the `.beads` directory itself. Resolve through `cwd` instead.
    environment.pop("BEADS_DIR", None)
    applied = run_bd(
        [
            beads_binary,
            "update",
            item_id,
            "--assignee",
            owner,
            "--status",
            status,
            "--json",
        ],
        environment,
        beads_dir,
    )
    if not applied["accepted"]:
        return {
            "accepted": False,
            "reason": applied["reason"],
            "detail": applied.get("detail", ""),
            "reconciliation_required": True,
            "receipt_revision": receipt["revision"],
        }
    return {
        "accepted": True,
        "receipt_revision": receipt["revision"],
        "owner": receipt["owner"],
    }
