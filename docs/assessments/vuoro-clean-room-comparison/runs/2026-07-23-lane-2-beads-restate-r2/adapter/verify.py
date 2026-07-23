import hashlib
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("RESTATE_BASE", "http://127.0.0.1:18080") + "/WorkItemClaim/BATCH-02"


def call(method, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(f"{BASE}/{method}", data=data, method="POST")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")


def demand(ok, label, detail):
    if not ok:
        raise AssertionError(f"{label}: {detail}")


status, first = call("acquire", {"owner": "actor-a"})
demand(status == 200 and first["accepted"], "acquire", first)
proof_a = first["proof"]
status, no_proof = call("mutate", {"mutation": "untrusted-delegated-write"})
demand(status == 200 and not no_proof["accepted"], "proofless mutation", no_proof)
status, transferred = call("transfer", {"proof": proof_a, "new_owner": "actor-b"})
demand(status == 200 and transferred["accepted"], "transfer", transferred)
proof_b = transferred["proof"]
demand(proof_a != proof_b, "proof rotation", "proof was reused")
status, stale_transfer = call("mutate", {"proof": proof_a, "mutation": "stale-owner-write"})
demand(status == 200 and not stale_transfer["accepted"], "old proof after transfer", stale_transfer)
status, current_mutation = call("mutate", {"proof": proof_b, "mutation": "current-owner-write"})
demand(status == 200 and current_mutation["accepted"], "current proof mutation", current_mutation)
status, recovered = call("recover", {"recovery_key": os.environ["RECOVERY_KEY"], "new_owner": "operator-recovered"})
demand(status == 200 and recovered["accepted"], "operator recovery", recovered)
proof_c = recovered["proof"]
demand(proof_b != proof_c, "recovery proof rotation", "proof was reused")
status, stale_recovery = call("mutate", {"proof": proof_b, "mutation": "pre-recovery-write"})
demand(status == 200 and not stale_recovery["accepted"], "old proof after recovery", stale_recovery)
status, inspected = call("inspect")
demand(status == 200 and inspected["owner"] == "operator-recovered" and inspected["revision"] == 4, "final state", inspected)
print(json.dumps({"acquire": "passed", "current_proof_mutation": "passed", "delegated_mutation_without_proof": "rejected", "final_owner": inspected["owner"], "final_revision": inspected["revision"], "old_proof_after_recovery": "rejected", "old_proof_after_transfer": "rejected", "operator_recovery_rotates_proof": "passed", "proof_digest_prefixes": [hashlib.sha256(proof_a.encode()).hexdigest()[:12], hashlib.sha256(proof_b.encode()).hexdigest()[:12], hashlib.sha256(proof_c.encode()).hexdigest()[:12]], "transfer_rotates_proof": "passed"}, sort_keys=True))
