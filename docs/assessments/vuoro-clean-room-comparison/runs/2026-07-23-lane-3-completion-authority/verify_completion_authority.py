"""Functional contract for a retained claim-gated completion callback."""

from __future__ import annotations

import hashlib
import json
import secrets


class CompletionAuthority:
    def __init__(self) -> None:
        self.owner = "worker-01"
        self.revision = 1
        self.proof = secrets.token_urlsafe(24)
        self.accepted: set[str] = set()

    def rotate(self, owner: str) -> str:
        self.owner = owner
        self.revision += 1
        self.proof = secrets.token_urlsafe(24)
        return self.proof

    def complete(self, execution_id: str, proof: str, revision: int, verified: bool) -> str:
        if execution_id in self.accepted:
            return "duplicate-rejected"
        if proof != self.proof or revision != self.revision:
            return "stale-rejected"
        if not verified:
            return "verification-failed-rejected"
        self.accepted.add(execution_id)
        return "accepted"


authority = CompletionAuthority()
proof_a = authority.proof
accepted = authority.complete("windmill-job-1", proof_a, 1, True)
duplicate = authority.complete("windmill-job-1", proof_a, 1, True)
proof_b = authority.rotate("worker-10")
stale_after_transfer = authority.complete("windmill-job-2", proof_a, 1, True)
verification_failure = authority.complete("windmill-job-3", proof_b, 2, False)
proof_c = authority.rotate("operator-recovered")
stale_after_recovery = authority.complete("windmill-job-4", proof_b, 2, True)

assert accepted == "accepted"
assert duplicate == "duplicate-rejected"
assert stale_after_transfer == "stale-rejected"
assert verification_failure == "verification-failed-rejected"
assert stale_after_recovery == "stale-rejected"
print(
    json.dumps(
        {
            "accepted_once": accepted,
            "duplicate": duplicate,
            "stale_after_transfer": stale_after_transfer,
            "verification_failure": verification_failure,
            "stale_after_recovery": stale_after_recovery,
            "proof_digest_prefixes": [
                hashlib.sha256(proof_a.encode()).hexdigest()[:12],
                hashlib.sha256(proof_b.encode()).hexdigest()[:12],
                hashlib.sha256(proof_c.encode()).hexdigest()[:12],
            ],
        },
        sort_keys=True,
    )
)
