# V6 — making skipped checks visible, and checking the other repos

Sprint item `agentops#2254`, reservation #29. Four rows, worked from the `debt:` lines the v5.9
pass produced. Freeze shape, oracle discipline and L-2a/L-2b validation unchanged; see
`handover-2026-08-23-metanarrative-v5.md` §§2–4 if resuming cold.

## Rows

| Row | What | PR | Billed | Oracle |
|---|---|---|---|---|
| V6-A | `assess_worker_workspace_write`: six statuses, `probed` only when the probe ran; carried into the prepare receipt | #106 (hand-pass) | — | 22 tests |
| V6-B | `build_scorecard` accepts any iterable of escalations | #107 | $0.010523 | 28 tests |
| V6-C | `audit_schema`: every unenforceable construct, not just the first | #108 | $0.042271 | 29 tests |
| V6-D | `validate_dispatch_manifest.py`: the CLI other repos run | #109 | $0.042108 | 40 tests |

Three worker rows, three first-attempt greens, **$0.094902 billed**, 1,821,773 tokens, zero
escalations, zero retries. Main 1041 → **1160 tests**.

## V6-A had to be a hand-pass, and the gate is why

`validate` refused it: *"writable path templates/dispatch/scripts/hybrid_dispatch.py intersects a
protected path"*. `hybrid_dispatch.py` is protected in `agentops.dispatch.json` at the **manifest**
level, not merely per packet, so no packet can make it writable. That is the containment working
as designed — the loop's own engine is not worker-writable — and the row was landed by hand with
its packet and reference kept as evidence.

## What V6-D found on its first real run

Pointed at every `*.dispatch.json` in `/projects/dev`, the new validator reports drift in **nine
repos**: `aligned-equity`, `appservice`, `bindery-core`, `homelab-analytics`, `local-inference`,
`outctl`, `scribectl`, `sprintctl`, `vuoro-bounded-output-starter`.

The commonest kinds:

- `routing.default_harness: "caller"` in `sprintctl` and `scribectl` — the schema's enum admits
  only `claude`, `codex`, `opencode`.
- `verification.command_families` carrying `security`, `process-semantics`, `package` in `outctl`
  and its starter — again outside the enum.
- `local-inference.dispatch.json` is a different shape entirely: missing `routing`, `skills`,
  `verification`, `hooks` and `instruction_set`, and carrying six properties the schema forbids.

None of these are this tract's to fix — they belong to their repos, and some may be the schema
being wrong rather than the manifest. What matters is that they are now findable by a command
instead of by nobody.

## The withheld receipt, and what it costs the scorecard

V6-D's receipt was **withheld**. The PR body says so in as many words: `receipt: withheld (the
transcript was not captured)`. The secret scanner matched `secret_assignment` on this, from a file
the worker read:

```python
TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
```

A regex constant named `TOKEN` assigned a value over twenty characters. A false positive, and the
scanner failing closed on it is the right default — but it has a consequence nobody had looked at:

**`worker_totals` cannot see a receipt that was never written.** The V6 scorecard reports 2 tasks
and $0.052794 for a tract that ran 3 and cost $0.094902 — it is short by a third, and it reports
`cost_reported: true` while being short, because that flag means "every contributing receipt
reported its spend", and a receipt that never arrived contributes nothing to contradict. The
`cost_unreported_tasks` list is empty for the same reason.

This is the units/scope/names family again: the number is arithmetically correct and answers a
different question than the one a reader asks it. The fix is not obvious and is not attempted
here — the scorecard would need to know how many tasks it *should* have found, which means
reading the packets or the driver reports rather than only the receipts. It is a `debt:` line.

Second, smaller line: `SECRET_PATTERNS["secret_assignment"]` matches an identifier ending in
`token` bound to any 20+ character value, which a regex constant satisfies. Loosening a secret
scanner is a judgement call with an obvious failure mode, so it is recorded rather than done.

## Debt this tract closed

- `build_scorecard`'s `len(escalations)` — closed by V6-B.
- The first-defect-only audit — closed by V6-C.
- "Nothing checks the other repos' manifests" — closed by V6-D, which found nine.
- "A skipped writability probe reports the same as a passed one" — closed by V6-A. Note the
  related fact this rests on: `--worker-user` defaults to `$AGENTOPS_WORKER_USER`, exported in
  devbox's agent shell and unset on the workstation, so the probe runs on one host and not the
  other even though both have `agentworker` and both have passwordless sudo to it.

## Debt this tract opened

- A withheld receipt silently shrinks the worker half of a scorecard, and `cost_reported` stays
  `true`.
- `secret_assignment` flags regex constants named `TOKEN`.
- Parallel freezes collide on `agentops.dispatch.json`: all three worker rows registered a command
  id in the same file and the three-way merge conflicted, resolved by taking the union. The L-6
  design predicted exactly this as a blocker for fan-out; it is now observed rather than
  predicted, on three packets rather than eight.
