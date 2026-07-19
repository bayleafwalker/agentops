---
doc_id: ecosystem-backlog-review-2026-07-17
status: reviewed
supersedes: null
---

# AgentOps ecosystem and backlog review — 2026-07-17

This is a read-and-refine pass over the AgentOps plans, the checked-out
implementation repositories, and the remote sprintctl tool backlogs, with a
follow-up verification pass on 2026-07-18. It is a planning record, not a
claim that unverified GitOps runtime state is healthy.

## Evidence used

- Remote sprintctl backend: schema current; repositories and backlog sprints
  were read on 2026-07-17 and re-read on 2026-07-18.
- Checked-out `main` branches for `agentops`, `sprintctl`, `kctl`, `auditctl`,
  `actionq`, and `actionq-dispatch`.
- Focused verification in this workspace:
  - `agentops/apps/web`: `npm test` — 72 passed.
  - `auditctl`: `uv run --extra dev pytest -q` — 22 passed.
  - `actionq`: `uv run --extra dev pytest -q` — 8 passed, 3 PostgreSQL
    integration tests skipped without their disposable test backend.
  - `kctl`: `uv run --extra dev pytest -q` — 95 passed in 61 seconds on the
    2026-07-18 follow-up. This supersedes the initial non-completion finding.
  - `actionq-dispatch`: `uv run --extra dev pytest -q` — 18 passed.
  - `sprintctl`: focused bootstrap and doctor tests — 10 passed. The full
    867-test suite did not finish inside the 90-second review window. Two
    apparent backend-mode failures were host-test contamination from a
    `/tmp/.git`; the affected file passes 13 tests under `TMPDIR=/var/tmp`.
    This is focused green evidence, not a full-suite result.

`appservice` is not present in this workspace and cluster access is blocked by
the current firewall posture. The operator reported on 2026-07-18 that the
cockpit is deployed. This review accepts that deployment fact as operator
attestation, but does not independently claim the image tag, configuration,
or smoke results.

## Current ecosystem state

| Owner | Verified state | Planning consequence |
| --- | --- | --- |
| `sprintctl` | Remote backend is reachable and schema-compatible. The new owner-correct backlog is sprint #407; the old mixed sprint #374 is archived. `main` contains the remote schema-bootstrap advisory-lock fix and its focused tests pass. Two concurrent reads through the installed packaged 0.2.0 CLI still deadlocked on 2026-07-18, confirming that version equality is not sufficient provenance for the fix. | Treat #407, not #374, as the current sprintctl backlog. Reinstall the CLI from the intended fixed revision before parallel operator runs and keep CLI access sequential until then; keep projection/authority work behind its stated evidence gates. |
| `agentops` | The cockpit has the session/reconciliation surfaces, sprintctl-owned activation route, and kctl `knowledge-artifact/v1` read surface. The web test suite passes. The operator reports that the cockpit is deployed; runtime access is firewalled from this machine. | Treat the deployment gate as satisfied by operator attestation. Retain image/config/smoke capture as operational evidence, not as a reason to block owner-correct follow-on work. |
| `kctl` | `knowledge-artifact/v1` contract, atomic exporter, remote sprintctl reader, and the existing JSON status/review interfaces are present on `main`; 95 tests pass under Python 3.14. | Treat the three evidence-complete backlog records as historical completion after normal claim workflow; retain only bounded synthesis/export work. |
| `auditctl` | Core SQLite + locked, fsynced NDJSON dual-write/rebuild implementation and verification contract are present; the focused suite passes. | Do not duplicate core dual-write work. Remaining work is publisher rollout, artifact operations, and the additive outbox/session-observation alignment. |
| `actionq` | The PostgreSQL queue and `actionq-server` v1 façade (`/health`, `/sessions`, `/dispatches`, `/dispatch`) are present and tested. | The daemon plan is stale: current `main` has no daemon, runner adapters, takeup client, or audit client. Keep those items open and shape them as real implementation work. |
| `actionq-dispatch` | The older one-shot dispatcher remains a separate, lightly updated repository; its 18-test suite passes, but it contains no long-running daemon modules claimed by the actionq plan. | First decide whether to absorb it or preserve it as a compatibility surface; do not claim the daemon is already shipped. |

## Plan corrections

1. `actionq/docs/plans/actionq-server-daemon-workstream-c-plan.md` formerly
   labelled steps 1–5 complete even though checked-out source contains no
   daemon implementation. The plan is corrected, actionq ownership decision
   #968 is complete, and the remaining steps point to open implementation
   records.
2. The agent-cockpit handoff now carries an operator deployment attestation.
   The source contains the post-`0.1.13` changes; exact image tag, config, and
   runtime smoke remain unverified from this firewalled machine.
3. The old agentops blocked records #947 and #948 were reconciled through
   normal claim/evidence history and are complete. Appservice #977 retains the
   cluster-owned secret-rotation procedure.
4. `kctl` #957, #958, and #960 were pending even though their source/docs/test
   coverage exists. They were reconciled to done through normal claims with
   durable verification notes.

## Backlog filling rules applied

Every open item refined in this pass now names its owner, reason, bounded
scope, explicit non-scope, dependency or gate, and verification evidence.
Where current source contradicts an old status, the record carries a durable
review note with evidence or is left open with the missing implementation
stated plainly. This pass does not fabricate claim history merely to rewrite
a legacy terminal status.

The initial 2026-07-18 inventory found 37 non-terminal records across five
owner backlogs. Remediation closed stale evidence-complete records in
agentops, sprintctl, actionq, auditctl, kctl, and appservice through normal
claim history; fully shaped all eleven previously empty appservice records;
and created agentops #1172/#1173/#1174 for the missing trigger, proposal
execution, and live dogfood gates. The resulting inventory is 40 actionable
non-terminal records: 3 in agentops, 8 in sprintctl, 1 in kctl, 7 in
auditctl, 11 in actionq, and 10 in appservice. None has an empty description.

The priority sequence remains:

```text
cockpit deployed (operator-attested) ──► config hardening + smoke capture
actionq daemon + capsule producer ──► trigger wiring ──► cutover evidence
audit publisher/outbox alignment ────► real cross-tool session observations
```

No new meta-repository implementation backlog was created. Work stays in the
domain owner’s remote backlog; this repository owns the sequencing and this
review record.

## Follow-up gates

- Appservice/operator: record the deployed image tag, artifacts root, write
  token configuration, and Tranche A smoke result when firewall-permitted
  access is available.
- Actionq owner: start from the ratified ownership decision and fake-runner
  daemon minimum (#969), then produce real Tier-0 capsules.
- Backlog owners: promote owner-local work into gated execution sprints
  without duplicating these refined backlog records.
- Sprintctl operator: the updated install now matches source capabilities and
  passed a concurrent-read smoke; retain provenance checks in normal upgrades.
- Operators: keep `auditctl` hook rollout and publisher integration explicit;
  neither follows automatically from the shipped ledger core.
