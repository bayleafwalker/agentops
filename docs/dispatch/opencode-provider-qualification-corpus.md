# OpenCode provider-qualification corpus

Status: candidate gate only. The checked-in profile remains
`preflight_observed`; this corpus does not qualify a provider, change routing,
or authorize a live run.

The executable contract is
`templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json`,
validated by `validate_opencode_qualification.py`. It builds on the reviewed
lifecycle probe at `47e6de6`: fake and contained lifecycle evidence remain
offline/host evidence and are never treated as provider qualification.

## Historical basis

The earlier worker-route observation (`366f63e`) measured the wrong boundary,
and the first contained run (`389551d`) was explicitly ineligible because it
used a model override. The retained Vuoro pilot receipts are evidence for the
named mechanical-bulk pilot only; they do not promote this implementation
profile. The corpus therefore requires a fresh run on the exact configured
route, without `--worker-model` or any other override.

## Deterministic routine gates

- The repository must explicitly opt into hybrid dispatch, the
  `mechanical_bulk` route, registered commands, allowed roots, and protected
  paths.
- The profile, root config, route, effective worker model, provider ID, and
  model ID must agree exactly. A fallback, alias, diagnostic model, or missing
  observed provider/model pair fails closed.
- The worker is exactly `agentworker`; the coordinator checkout must be
  kernel-proven unwritable, the worker workspace must be writable, and the
  workspace check must round-trip in both directions with exactly the reviewed
  `agentworker`/`agentdispatch` groups. Reads remain uncontained and are not
  silently claimed to be isolated.
- Provider workspace opt-in is an explicit receipt fact, never inherited from
  an environment default. Usage accounting names its denominator: positive
  provider-reported baseline units, observed units, and their ratio. The ratio
  must be finite, internally consistent, and no greater than 2. Missing,
  negative, non-finite, reset, or contradictory accounting fails closed.
- One attempt is allowed. `$3.00`, 500,000 soft tokens, and 1,000,000 hard
  tokens are post-hoc acceptance limits: the receipt is rejected if any is
  exceeded, but they are not provider-side spend caps. The runner retains a
  120-second hard wall and stops on observed token/cost overrun when evidence
  arrives; only a real provider-side cap could make spend prevention
  authoritative. These controls do not substitute for the 2x usage gate.
- Receipts retain structural evidence only: byte-hashed JSON artifacts,
  digests, counts, booleans, exact identity, and immutable references. The
  validator parses each artifact and compares it with the receipt, including
  the provider-reported usage denominator and the generated session overlay.
  Prompts, transcripts, raw output,
  credentials, claim proof, environment, and absolute worktree paths are
  rejected. Raw transcript capture is a separate, explicit private-artifact
  decision and is not part of this corpus.
- Candidate admission requires the concrete one-shot packet in the corpus, a
  runner-issued nonce, a fresh sealed `0400` execution record authenticated by
  the externally provisioned key whose fingerprint is pinned in the corpus,
  and an atomic consumption marker. A missing,
  stale, forged, or already-consumed record cannot produce `candidate_ready`.
- Provider origin is carried by the authenticated runner record: the exact
  sanitized OpenCode export digest and exact provider/model pair must match
  the structural artifact. A receipt's source labels are never trusted by
  themselves.

The offline command is intentionally blocked on provider qualification:

```bash
python templates/dispatch/scripts/validate_opencode_qualification.py
```

A receipt is not a candidate merely because its JSON is structurally valid. The
admission command must call the fixed-path
`agentops-opencode-qualification-verify-consume` helper with only receipt,
evidence-root, and record paths. The helper verifies the signed runner record
with pinned public-key/allowed-signers material, cannot access the private key,
and atomically consumes the nonce, so a replay fails. Even after that gate, the result retains
`qualification_eligible: false` and `qualification_state: preflight_observed`,
requiring independent review and human acceptance. The corpus has no command
that performs profile promotion.

## Privileged workstation installation and runbook handoff

This is an installation contract, not an instruction to contact the provider.
The live runner must be installed and operated by root on the intended
workstation. Admission callers must not receive its private key or be able to
write any trust material, records, or ledger entries.

Before independent review, the workstation owner must provision this fixed
layout under `/var/lib/agentops/opencode-qualification`:

The root-owned installation also freezes the reviewed packet and root config
at `/etc/agentops/opencode-qualification/corpus.json` and
`/etc/agentops/opencode-qualification/opencode.hybrid.json`. The launcher has
no repository-relative fallback and accepts no alternate corpus/config path;
the installed corpus must be byte-for-byte the reviewed candidate before the
single run.

The same installation freezes the reviewed `profile.json`,
`hybrid-dispatch.v1.json`, `agentops.dispatch.json`, and the four root-owned
`0400` preflight artifacts under `preflight-evidence/` (`capability.json`,
`lifecycle.json`, `overlay.json`, and `workspace.json`). Their bytes are
checked against the checked-in `templates/dispatch/provider-qualification/preflight-evidence/`
bytes and pinned digests before the packet sentinel is created.
The installation root itself is `root:root` mode `0700`; every parent and
installed file is a non-symlink regular object with the specified owner and
mode. The five pinned system executable inputs (`opencode`, `runuser`, `touch`,
`mkdir`, and `ssh-keygen`) are the deliberate portability exception: their
configured paths may be Nix-style symlinks, but the runner resolves each final
target and requires a root-owned regular executable with no group/world write
bits. It then `lstat`s every parent of the resolved target. Resolved parents
must be root-owned directories without group/world write bits, except for the
exact `/nix/store` directory on this host: root-owned, sticky mode `01775`,
and on a read-only filesystem. That exact mount rule prevents even the root
runner identity from replacing a store entry; arbitrary sticky or writable
directories are rejected. The parent metadata and read-only mount condition
are rechecked before each execution. The runner verifies the worker's actual
UID, exact supplementary groups, workspace round-trip, coordinator write
denial, and OpenCode `1.18.4` version before issuing the provider-facing
command.

| Path | Owner and mode | Purpose |
| --- | --- | --- |
| `runner.key` | `root:root`, `0400` | Ed25519 private signing key; never passed to admission or receipt validation |
| `provider-auth.json` | `root:root`, `0400` | Fixed bounded OpenCode provider credential source; copied only into the fresh worker HOME |
| `corpus.sha256` | `root:root`, `0400` | Final installed corpus byte pin |
| `runner.pub` | `root:root`, `0444` | Pinned public key used for signature verification |
| `allowed_signers` | `root:root`, `0444` | OpenSSH allowed-signers entry restricted to the runner identity and qualification namespace |
| `records/` | `root:root`, `0700` | Exact immutable execution-record root |
| `ledger/` | `root:root`, `0700` | Exact one-time nonce-consumption ledger root |
| `evidence/` | `root:root`, `0700` | Structural evidence output; no raw transcript or provider secret |
| `workspaces/` | `root:root`, `0711` | Non-listable/searchable parent for fresh per-run directories; each child is `agentworker:agentworker`, `0700` |

During a run, the worker-owned child contains only the native auth path
`$HOME/.local/share/opencode/`, with `.local`, `share`, and `opencode` each
`agentworker:agentworker` mode `0700`; `auth.json` is `agentworker:agentworker`
mode `0400`. The root runner creates and verifies this tree, then removes the
credential on every post-run path and scans the disposable workspace to prove
the credential value did not enter a regular runtime file. OpenCode's
non-secret `opencode-stable.db`, WAL, logs, and `repos/` state may remain inside
that private per-run workspace for bounded diagnostics; they are never copied
to evidence or read by admission. If provisioning fails before OpenCode starts,
the pristine auth tree is rolled back completely, including its directories.

Install the admission helper separately as a root-owned, non-writable
executable at
`/usr/local/libexec/agentops-opencode-qualification-verify-consume`. It must be
the reviewed helper bytes, and its only caller inputs are `<receipt>
<evidence-root> <runner-record>`; public verification material and trust roots
remain compiled/configured in the helper, not caller arguments.

The installed boundary is fixed, with no repository-relative fallback:

```text
/etc/agentops/opencode-qualification/corpus.json
/etc/agentops/opencode-qualification/verify-consume.sha256
/usr/local/libexec/agentops-opencode-qualification-verify-consume
/usr/local/libexec/agentops-opencode-qualification-validator.py
/usr/local/libexec/agentops-opencode-qualification-profile-validator.py
/usr/local/libexec/agentops-opencode-qualification-hybrid-validator.py
/usr/local/libexec/agentops-opencode-qualification-hybrid-dispatch.py
```

The helper verifies the root-owned modes and hashes of this package before it
loads the installed validator. The workstation must grant only this exact
helper through a sudoers or service boundary, for example:

```text
agentops-admission ALL=(root) NOPASSWD: /usr/local/libexec/agentops-opencode-qualification-verify-consume /var/lib/agentops/opencode-qualification/evidence/*/receipt.json /var/lib/agentops/opencode-qualification/evidence/* /var/lib/agentops/opencode-qualification/records/run-*.json
Defaults!/usr/local/libexec/agentops-opencode-qualification-verify-consume env_reset,secure_path=/run/current-system/sw/bin
```

The admission identity receives no permission on `runner.key`; the privileged
helper reads only public verification material, records, evidence, and the
ledger. It has no general shell, path-selection, corpus-selection, or private
key authority.

The corpus and validator must pin the public-key and allowed-signers
fingerprints as well as these exact absolute paths:

```text
/var/lib/agentops/opencode-qualification/runner.pub
/var/lib/agentops/opencode-qualification/allowed_signers
/var/lib/agentops/opencode-qualification/records
/var/lib/agentops/opencode-qualification/ledger
```

The privileged launcher must reject substitutions, symlinks, non-regular
files, wrong owners, group/world-writable parents, and mode mismatches for
trust material, state, installed artifacts, and the runner. The five pinned
system executable paths named above are the sole symlink exception; their
resolved final targets are checked for root ownership, regular-file type,
execute permission, and absence of group/world write bits. Every resolved
parent is checked with the narrow `/nix/store` read-only `01775` exception
described above, and stable metadata fingerprints cover both the target and
the complete resolved parent chain through use. The CLI accepts the exact
`--verify-installation` option only; abbreviation such as `--verify-i` is
rejected. The exact verification mode is side-effect-free and contacts no
provider.
Completed records and detached signatures are `root:root` mode `0400`; nonce
consumption markers are also `root:root` mode `0400`. Admission verification
uses only the pinned public key and allowed-signers material. An HMAC, shared
secret, self-authored source label, caller-selected key, or caller-selected
record or ledger root is not trusted evidence. If the installed validator asks
an admission caller for `runner.key`, stop and leave qualification blocked.

The root-only one-shot handoff is:

1. Freeze the reviewed corpus and independently review the packet, exact
   route/model, workspace opt-in, containment facts, privacy schema, and both
   token ceilings. Run the offline validator and confirm
   `qualification_eligible: false`, `qualification_state: preflight_observed`,
   and no provider contact.
2. As the unprivileged admission identity, run the side-effect-free installation
   check first:

   ```bash
   sudo -n /usr/local/sbin/agentops-opencode-qualification-runner --verify-installation
   ```

   It must report `side_effects: false`; it creates no workspace, sentinel,
   ledger entry, or provider process. Then, after independent approval, as
   root invoke the installed runner with no path or packet overrides. It
   first creates a unique empty `workspaces/<run-id>` owned by
   `agentworker:agentworker` and proves it has no prior state. It then creates
   the root-owned O_EXCL `ledger/packet.attempted` sentinel, permanently
   reserving this packet before any provider-facing process. It atomically
   issues one fresh nonce, binds the exact request to the packet, and refuses
   an existing sentinel, stale packet, second attempt, or replay; the sentinel
   remains after failure.
3. The runner invokes the contained OpenCode lifecycle exactly once and keeps
   the 120-second hard wall. `$3/500k/1m` are post-hoc acceptance limits because
   no provider-side spend cap is claimed; observed token/cost overruns stop the
   run when possible and any over-limit receipt is rejected. A failed or
   interrupted attempt is not candidate-ready.
4. On successful completion only, the runner writes the `0400` immutable
   record and one-time ledger marker, records provider-origin and
   provider-reported usage evidence, and signs the record with `runner.key`.
   The signature is verified with the pinned public/allowed-signers material;
   the private key is never part of the receipt, evidence bundle, admission
   process, or command arguments.
5. After the independent reviewer authorizes this single bounded run, invoke
   the fixed-path verifier/consume helper to validate the signed receipt and
   evidence bundle against the exact configured roots and atomically consume
   the nonce. A second validation or replay must fail closed. The result
   remains a candidate for human qualification only; it never promotes the
   profile automatically.

The workstation installation handoff is explicit and must be performed by the
root operator outside this repository: provision the pinned Ed25519 public key
and matching private key through the workstation's approved secret process,
write the allowed-signers line for identity
`agentops-opencode-qualification-runner/v1` and namespace
`agentops-opencode-qualification`, create the fixed directories above, then
install the reviewed runner with root ownership and mode `0755` at the
workstation's approved system path. The only invocation is equivalent to:

```bash
sudo /usr/local/sbin/agentops-opencode-qualification-runner
```

Provision the fixed auth source at
`/var/lib/agentops/opencode-qualification/provider-auth.json` as `root:root`
mode `0400`, with only the bounded object
`{"opencode-go":{"type":"api","key":"<approved credential>"}}`.
This is the native OpenCode auth shape. The runner copies it into the fresh
worker HOME at `$HOME/.local/share/opencode/auth.json`, sets
`XDG_DATA_HOME=$HOME/.local/share`, and passes the same bounded native JSON
through `OPENCODE_AUTH_CONTENT` in the scrubbed environment. It never sets
`OPENCODE_AUTH_FILE`. The disposable native auth file is removed on success or
failure. The credential is never logged, hashed into the receipt, or inherited
from the operator environment.

The launcher accepts no packet, key, record-root, ledger-root, workspace, or
OpenCode-path overrides. If provider authentication is required, provision
only the named runner/worker auth input through the workstation's approved
secret mechanism; do not inherit the operator's environment or a broad secret
set, and never write auth values to evidence. The private key is read only by
that root-owned launcher. Admission invokes the installed verifier/consume
helper with receipt, evidence-root, and record paths only; the helper supplies
the pinned corpus/public-key/allowed-signers paths itself. Passing a private-key
path, arbitrary root, or copied corpus is an immediate fail-closed condition. These are
handoff commands only; this change does not install keys, alter workstation
permissions, invoke the launcher, or contact the provider.

The only permitted privileged invocation is the installed one-shot runner for
this packet. Do not use an interactive OpenCode session, a retry loop, a
different workspace, a different key, or a copied corpus. No installation,
key generation, live invocation, provider spend, deployment, or Sprintctl
mutation is performed by this change.

## The single bounded live run after review

After independent review of this candidate, the operator may run exactly one
contained, disposable, docs-only qualification action on the intended devbox:
`agentworker`, the explicitly opted-in workspace, pinned profile
`opencode-nixpkgs-devbox-1.18.4`, and exact
`opencode-go/deepseek-v4-flash`, with no model override. Use cold pre-gates and
post-gates, retain the sanitized receipt and usage accounting, and stop on any
containment, model, privacy, budget, or usage failure. Do not retry or promote
from this candidate. A failed run leaves the profile preflight and requires a
new review decision; it does not authorize a second attempt.

No live provider run is part of this change.
