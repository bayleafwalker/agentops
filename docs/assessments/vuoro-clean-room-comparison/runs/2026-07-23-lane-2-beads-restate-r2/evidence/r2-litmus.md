# Lane 2 — Minimal Restate Claim Adapter R2 Litmus

This is a disposable isolated run against the locked sprintctl corpus contract,
using `BATCH-02` as the object key. It deliberately proves only the proposed
claim authority adapter; it does not claim that Beads itself has been adapted.

## Locked implementation

- Restate server image:
  `docker.restate.dev/restatedev/restate@sha256:53b245bcd64318233128c49ce56577737c888fcfacd5dbe8e7c88deb12753681`
- Restate Python SDK: `1.0.2`
- Adapter image:
  `vuoro-clean-room-lane2-adapter@sha256:13816d72ba84dc2df76bb624a4c27de283c505aad4c2b44f0a23466cbbfcdb9d`
- Adapter source SHA-256:
  `121abfa6e47eeceab3d711ebafa12876e4813e67fb6069f3e19ba22c44606f7b`

Both containers ran on a new disposable Docker network. The only published
ports were loopback `127.0.0.1:18080`, `:19070`, and `:19071`; no workspace,
production endpoint, or production credential was mounted or used. The
operator recovery key was a one-run generated environment value and is neither
recorded nor emitted below.

## Redacted result

```json
{"acquire":"passed","current_proof_mutation":"passed","delegated_mutation_without_proof":"rejected","final_owner":"operator-recovered","final_revision":4,"old_proof_after_recovery":"rejected","old_proof_after_transfer":"rejected","operator_recovery_rotates_proof":"passed","proof_digest_prefixes":["67c83e91a875","bce5e223d7f7","4b1fbae97a9d"],"transfer_rotates_proof":"passed"}
```

The adapter persisted only SHA-256 proof digests. It returned the raw proof to
the immediate acquire, transfer, or recovery caller, but the test output stores
only digest prefixes. Failed proof checks returned explicit `accepted: false`
receipts; the first attempt used exceptions, which Restate retried, so that
attempt was discarded and the final run started from a new server state.

## R2 verdict and limit

The adapter satisfies the R2 litmus in isolation: a proofless delegated actor
could not mutate; old proof could not mutate after transfer; and old proof
could not mutate after controlled recovery. Transfer and recovery each produced
different proof-digest prefixes, while the final owner and revision were
authoritative in the virtual object.

This does **not** yet prove the Lane 2 hypothesis. A Beads operation could
still mutate Beads state without first obtaining an adapter decision, creating
two competing authorities. The next Lane 2 work must wire a real Beads mutation
boundary through this adapter and measure reconciliation and carrying cost.
