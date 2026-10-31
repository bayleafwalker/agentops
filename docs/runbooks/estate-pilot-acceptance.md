# Estate pilot acceptance drivers

These source-only drivers implement the protected check and independent review
for the public AgentOps maintenance freshness defect selected as Work 2873.
They do not start or accept Work, qualify a deployment, approve an output, or
publish a candidate. The real task remains unfixed on canonical main.

The permitted candidate changes exactly two ordinary files:
`scripts/estate_status.py` and `scripts/tests/test_estate_maintenance.py`.
The source change excludes JSON booleans from the finite positive numeric
`max_age_hours` validation. All other source AST and existing test AST must
remain unchanged. New focused regression methods use a closed grammar; each
must pass on the candidate and assertion-fail on the original defect, without
errors or skips. Each method is checked separately, including its subtests.

The protected semantic baseline is
`dcb137a42c5bd135415515c8d750ec8c5b1b1660`. The constructor separately requires
an actual Work base. Both base-file blobs must equal the protected baseline;
the candidate must descend from the exact supplied Work base. A later canonical
commit can therefore carry the drivers without silently changing the task.

Gitops exposes `lib.estatePilotAcceptance { agentopsSource; workBase; }`.
Supply reviewed immutable AgentOps source and the actual Work base. The package
contains distinct check and review launchers and `driver-pins.json`. Consumer
configuration must use the resolved launcher paths and hashes from that file,
with the recorded 135-second timeout. The collection's `bin` entries are
symlinks. The generated pins explicitly say `qualified: false`.

Each invocation receives only a clean checkout, exact base SHA and candidate
SHA. Sanitized existing Git helpers validate ancestry, the two modified paths,
ordinary file modes and exact baseline blobs. A finite JSON payload enters a
fixed initramfs member. A fresh KVM-only diskless microvm has one vCPU, 1536 MiB,
loopback only, no block devices, network interface or host filesystem shares.
Only the explicit public Python source closure, interpreter and protected
baseline enter its image; profiles and live state are excluded.

The root guest supervisor stages read-only inputs, then drops groups and runs
the oracle as UID/GID 1000 with no-new-privileges and bounded processes, files,
CPU, output and lifetime. Both modes admit the side-effect-free source change
before importing candidate code. The check exercises 17 behavioral cases and
109 protected baseline tests. Review additionally admits candidate test syntax
and runs each new method against separate candidate and baseline trees.

The unprivileged oracle must fail to read a positively created synthetic parent
secret and PID 1 environment, write PID 1 stdout or either serial device, or
reach a nonloopback address. The supervisor quiesces remaining UID 1000
processes before emitting its root-only serial receipt. Host validation binds
that receipt to a fresh challenge, payload digest, base, candidate, mode, boot
UUID and closed metrics/reason fields. Check and review use different boots.
Parent death kills QEMU. A missing or interrupted receipt exits 124; only a
completed definite failure exits 1 and is eligible for the existing consumer's
repair-evidence rules. Neither result itself grants repair authority.

Reproduce the local synthetic controls after building the constructor for the
protected baseline:

```sh
python scripts/qualification/verify_estate_acceptance.py \
  /nix/store/ACTUAL-estate-pilot-protected-acceptance \
  /absolute/local/public-agentops-checkout /tmp/estate-acceptance-proof.json
```

The harness makes temporary local clones and synthetic commits, calls no model
or owner, and never edits the real Work checkout. The committed
`docs/verification/estate-acceptance/2026-10-31.synthetic-proof.json` records nine
passing controls: separate positive check/review, original defect and unrelated
source changes refused in both modes, an ineffective added regression refused,
launcher death stopping QEMU, and QEMU death returning unknown. Its package
contains the final reviewed source admission and per-method differential fixes.
Earlier prototype receipts and the initial incomplete package import are not
evidence for this version.

These local controls do not qualify a production host or a real candidate.
Commissioning must bind the final released runtime/contract/consumer tuple,
actual driver closure and Work base, caller/Workspace/executor identities,
current authority, retained candidate and publication path, and the installed
owner image's measured isolation. A new deployment or base needs those exact
bindings before the pilot runs. No source proof grants a human review,
qualification signature, billing settlement, or Work acceptance.
