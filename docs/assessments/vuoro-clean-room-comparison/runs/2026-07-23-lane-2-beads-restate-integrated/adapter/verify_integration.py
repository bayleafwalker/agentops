"""Run the composed Beads-to-Restate mutation-boundary experiment."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request

from planner_bridge import transition


BASE = os.environ["RESTATE_BASE"]
BEADS = os.environ["BEADS_BINARY"]
BEADS_DIR = os.environ["BEADS_DIR"]
DOLT_ROOT = os.environ["DOLT_ROOT_PATH"]
RECOVERY_KEY = os.environ["RECOVERY_KEY"]
# `cr-689` is the generated Beads-native realization of the locked corpus
# obligation `CR-02`; it is the matching Restate object key for this run.
ITEM_KEY = "cr-689"


def call(method: str, payload: dict | None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{BASE}/WorkItemClaim/{ITEM_KEY}/{method}",
        data=data,
        headers={} if data is None else {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"accepted": False, "reason": f"restate-http-{error.code}"}


def demand(condition: bool, label: str, detail: object) -> None:
    if not condition:
        raise AssertionError(f"{label}: {detail}")


def bd(*args: str) -> object:
    completed = subprocess.run(
        [BEADS, *args, "--json"],
        cwd=BEADS_DIR,
        env={key: value for key, value in {**os.environ, "DOLT_ROOT_PATH": DOLT_ROOT}.items() if key != "BEADS_DIR"},
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


acquires: list[dict] = []


def acquire(actor: str) -> None:
    acquires.append(call("acquire", {"owner": actor}))


workers = [threading.Thread(target=acquire, args=(f"worker-{number:02}",)) for number in range(1, 3)]
for worker in workers:
    worker.start()
for worker in workers:
    worker.join()
accepted_acquires = [entry for entry in acquires if entry.get("accepted")]
demand(len(accepted_acquires) == 1, "concurrent acquire", acquires)
first = accepted_acquires[0]
proof_a = first["proof"]

proofless = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner="delegated-worker",
    proof="",
)
demand(not proofless["accepted"], "proofless delegated mutation", proofless)

first_transition = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner=first["owner"],
    proof=proof_a,
)
demand(first_transition["accepted"], "current owner transition", first_transition)

transferred = call("transfer", {"proof": proof_a, "new_owner": "worker-10"})
demand(transferred.get("accepted"), "handoff", transferred)
proof_b = transferred["proof"]
demand(proof_a != proof_b, "handoff proof rotation", "proof reused")

stale_transfer = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner="worker-01",
    proof=proof_a,
)
demand(not stale_transfer["accepted"], "stale proof after handoff", stale_transfer)

current_transition = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner="worker-10",
    proof=proof_b,
)
demand(current_transition["accepted"], "new owner transition", current_transition)

recovered = call("recover", {"recovery_key": RECOVERY_KEY, "new_owner": "operator-recovered"})
demand(recovered.get("accepted"), "controlled recovery", recovered)
proof_c = recovered["proof"]
demand(proof_b != proof_c, "recovery proof rotation", "proof reused")

stale_recovery = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner="worker-10",
    proof=proof_b,
)
demand(not stale_recovery["accepted"], "stale proof after recovery", stale_recovery)

recovered_transition = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner="operator-recovered",
    proof=proof_c,
)
demand(recovered_transition["accepted"], "recovered owner transition", recovered_transition)

authoritative = call("inspect", None)
demand(authoritative["owner"] == "operator-recovered", "authoritative owner", authoritative)

# This intentionally bypasses the bridge and exercises Beads' native update.
# Its success is the decisive authority-count result for this composition.
bypass = bd("update", ITEM_KEY, "--assignee", "untrusted-bypass", "--status", "in_progress")
demand(bypass, "native Beads bypass", bypass)

repair = transition(
    restate_base=BASE,
    beads_binary=BEADS,
    beads_dir=BEADS_DIR,
    dolt_root=DOLT_ROOT,
    item_id=ITEM_KEY,
    owner="operator-recovered",
    proof=proof_c,
)
demand(repair["accepted"], "reconciliation repair", repair)

print(
    json.dumps(
        {
            "adapter_gated_mutations": "passed",
            "authoritative_owner": authoritative["owner"],
            "concurrent_acquire": {"accepted": 1, "rejected": 1},
            "native_beads_bypass": "accepted",
            "planner_item": ITEM_KEY,
            "proofless_delegated_mutation": "rejected",
            "reconciliation_repair": "passed-but-bypass-remains",
            "recovery_stale_proof": "rejected",
            "stale_handoff_proof": "rejected",
            "proof_digest_prefixes": [
                hashlib.sha256(proof_a.encode()).hexdigest()[:12],
                hashlib.sha256(proof_b.encode()).hexdigest()[:12],
                hashlib.sha256(proof_c.encode()).hexdigest()[:12],
            ],
        },
        sort_keys=True,
    )
)
