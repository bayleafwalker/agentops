# OpenCode admission check

Status: a repeatable sanity check, not an attestation framework. There is no
promotion, no "qualified" state, and no one-shot ceremony. Rerun it any time.

## What this answers

Two questions, cheaply and repeatably:

1. **Is this provider/model actually routable right now?** Proven by a real
   contained OpenCode call plus an independently fetched sanitized export
   that must agree on provider, model, and completion.
2. **Does it produce a reasonable output for its cost?** Proven by
   bound-checked usage/cost accounting (positive baseline, cost and token
   ceilings, output-to-input ratio capped at 2x).

That is the whole scope. It is not a promotion gate, not a signed record, not
a one-time-use ledger, and not subject to independent review before or after
running. Ongoing trust in a provider/model for a given role is a separate,
rolling mechanism — role-scoped continuous fitness and routing evidence
collected over hundreds of real runs (agentops#2143, backlog, not this
check) — not a one-shot decision made here.

## Why this changed

This item drifted into a "provider-qualified" attestation framework: an
Ed25519-signed execution record, a permanent one-shot ledger sentinel, and
two independent-human-review gates, around a check whose own code could
never actually promote anything (`qualification_eligible` was hardcoded
`False` in every code path, always). The operator reframed the goal
mid-investigation:

> The whole point of qualification isn't to keep adding barriers, simply
> answer the simplest questions like: can this model be used (is it actually
> routable now), does it look to be doing what it's meant to be doing (in a
> very general sense, do we get reasonable outputs for input cost). There's
> no grand "qualified" sense like a five stage hiring process with an IQ test
> on top.

Two live attempts under the old design burned real spend chasing what turned
out to be the same root cause: `_provider_event()` hard-required a
provider-issued request identifier that no real OpenCode 1.18.4 output for
`opencode-go` ever produces (confirmed against seven live captures, and
against the sanitized export). The gate failed closed on every real run,
unconditionally — not a security property, just a permanently broken check
that happened to fail in the safe direction. The permanent ledger sentinel
meant each of those trivial-infra-bug discoveries required a full fresh
review cycle to even retry. That is the direct evidence behind removing it.

Full traceability: sprintctl events #2357–#2379 on agentops#2142; auditctl
refs `ad:01KZV9ANHE819T26BK95MHFPJ5` (root-cause correction),
`ad:01KZV9KAYH82ZBKVG2X9N7SNJE` (first simplification design pass),
`ad:01KZVB1MBQ9PPTNCVX352BAJ83` (this design, as implemented).

## What was deleted, and why

- **Ed25519 signing** (`runner.key`/`runner.pub`/`allowed_signers`, the
  signed execution record). No downstream logic depended on signed-ness
  distinct from the plaintext fields the signature re-derived.
- **The permanent one-shot ledger sentinel.** This was the mechanism that
  burned a packet forever on *any* failure, including a trivial infra bug —
  directly at odds with "cheap, repeatable sanity check." Replaced with an
  optional, `--force`-overridable cooldown against accidental loop-spend,
  which is directory hygiene, not a security gate.
- **Both independent-review gates**, before and after. Nothing was ever
  promoted or committed by this check, so nothing needs commitment-grade
  review.
- **~400 lines of pinned-executable / resolved-parent-chain / Nix-store-mount
  fingerprinting**, and the root-owned digest-pinned install tree for the
  corpus/profile/policy/manifest/runner bytes themselves. Attestation-grade
  supply-chain ceremony unrelated to routability or cost.
- **The optional, non-gating provider-request-ID plumbing** from the interim
  fix. Dead weight — trivial to re-add if a future OpenCode version ever
  actually emits one.

## What was kept, and shrunk

- **`_provider_usage()` bound-checks** (positive baseline, finite cost, ratio
  ≤ 2× baseline) — the real "reasonable for cost" answer.
- **`_parse_sanitized_export()`** cross-check of `providerID`/`modelID`/
  `finish` from a separately fetched `opencode export --sanitize` call — the
  real "routable" answer, independent of the live event stream. The exact
  `part_types == ["text", "step-finish"]` grammar match is loosened to "a
  completion (`step-finish`) part occurred somewhere" — the exact match was
  over-fit to one harness snapshot.
- **"At least one clean completion event, sanity-bound all of them"**,
  replacing "exactly one, hard-fail on any other count." That exact-count
  strictness is the same over-fit-security-gate pattern that produced a
  false diagnosis earlier in this investigation (a genuine multi-step
  tool-use response legitimately emits more than one step-finish).
- **Cost/token/wall-clock ceilings** ($3, 500k/1M tokens, 120s) — cheap
  insurance, unchanged.
- **The worker-boundary/containment probe** — cheap, mechanical, answers a
  distinct question ("not obviously dangerous to assign this worker role").
  Only its dependency on the deleted pinned-executable-chain machinery was
  trimmed; it now calls configured binary paths directly.
- **Credential provisioning/scrub discipline** (`0400`, disposable per-run
  copy, wipe-and-scan-after) — unchanged. This is the one thing that still
  needs real protection, explicitly separated from the deleted
  non-repudiation ceremony.

No harness abstraction layer was built. Only one implementation
(`opencode`/`opencode-go`) exists; a plugin/adapter layer is speculative
until a second harness family actually shows up. What's already
harness-agnostic (the usage-bound-check shape, the containment-probe
pattern, the credential-scrub pattern, the two-question shape itself) versus
OpenCode-specific (the export format, the event-stream shape, the pinned
executable paths, the `1.18.4` version check) is worth knowing if that day
comes, but nothing was pre-built for it.

## Files

- `templates/dispatch/scripts/check_opencode_admission.py` — the check
  itself. Runs directly as the operator; no privileged install step.
- `templates/dispatch/scripts/validate_opencode_qualification.py` — offline
  sanity/privacy check of the config and, optionally, a result file. Not a
  promotion gate.
- `templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json`
  — plain config: reviewed route, budgets, containment identity. Not
  digest-pinned; edit and rerun against it like any other config file.

## Usage

```bash
python templates/dispatch/scripts/check_opencode_admission.py \
  --provider opencode-go --model deepseek-v4-flash --agent ao-mechanical-bulk
```

- One contained OpenCode call, with the same hard-wall/cost/token ceilings
  enforced live.
- One JSON result to stdout: routability, cost-sanity, containment result,
  pass/fail.
- The same JSON is written as a plain, non-privileged, unsigned run-report
  log entry under `docs/dispatch/admission-runs/<provider>-<model>-<date>.json`
  — a note for the next operator, not evidence infrastructure.
- On failure: fix, rerun immediately. `--force` bypasses the accidental-loop
  cooldown; there is no ledger to reset and no review cycle to restart.

Validate the config (and, optionally, a result) offline:

```bash
python templates/dispatch/scripts/validate_opencode_qualification.py \
  --result docs/dispatch/admission-runs/opencode-go-deepseek-v4-flash-2026-08-12.json
```

## What this does not do

Does not deploy, does not touch gitops-nixos/devbox configuration, does not
mark a provider "qualified" in any promotable sense, and does not feed
routing decisions directly — those are agentops#2143's job, built from many
runs over time, not a single check like this one.
