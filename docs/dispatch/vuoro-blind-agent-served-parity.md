# Vuoro blind-agent served parity matrix

Status: **current deployed/source inventory, 2026-07-26**. This is the P0
inventory required by the blind-agent parity handoff; it is not a claim that
the listed unsupported operations already fail cleanly.

The contract is deliberately narrow. A command is **served** only when the
guidance can use it against the selected Vuoro profile without opening a
Sprintctl store. **Unsupported** means it is part of the blind-agent loop but
has no established served equivalent; it must be rejected before store
creation with `served-operation-unavailable`-class guidance. **Recovery-only**
means it deliberately needs local/direct state and must not be offered as the
normal served workflow. Do not treat an existing PostgreSQL/SQLite fall-through
as either served or recovery authorization.

Source evidence is the checked-in guidance named in the first column, the
Sprintctl served route table at
`/projects/dev/sprintctl/sprintctl/served_routes.py`, and the recorded deployed
assessment at
[`../../.agents/sessions/2026-07-26-vuoro-blind-agent-parity-next-devbox.md`](../../.agents/sessions/2026-07-26-vuoro-blind-agent-parity-next-devbox.md).
The latter records the production image verdict, rather than extrapolating
from a newer local checkout. `sprintctl` source references below identify the
guard or route that supports the classification; they are not acceptance
evidence for an untested future deployment.

## Orientation and selection

| Guidance source | Prescribed command or operation | Status | Evidence and required disposition |
| --- | --- | --- | --- |
| workspace `AGENTS.md` / devbox start | `sprintctl doctor --json` | served | Recorded as a successful served read in the handoff; catalog probing is part of `doctor`. |
| `task-pickup` step 1 | `sprintctl sprint list --active --json` | served | `sprint.list` routes to `work.read.sprints`; its served implementation forwards `active_only` (`cli.py:sprint_list`). |
| `task-pickup` step 1 | `sprintctl sprint list --include-backlog --json` | served | Same `work.read.sprints` route; the served implementation forwards `include_backlog`. Project-wide `--project` is separately unsupported. |
| `task-pickup` step 3; `sprint-resume` step 3 | `sprintctl claim list-sprint --sprint-id <sprint-id> --json` | unsupported (P0) | No `claim.list-sprint` entry in `SERVED_COMMAND_ROUTES`; the handoff observed a direct PostgreSQL fall-through and misleading `psycopg` advice. Add a pre-store refusal first, then a catalog read. |
| `task-pickup` step 4 | `sprintctl next-work --sprint-id <sprint-id> --json --explain` | unsupported (P1 decision) | Basic `next-work` has `work.read.next-work`, but the handoff and `cli.py:next_work_cmd` distinguish `--explain` as an unserved aggregate. Implement a catalog aggregate, compose honestly from served reads, or remove it from guidance. |
| `task-pickup` step 6; `sprint-resume` step 3 | `sprintctl item show --id <item-id> --json` | served | `item.show` routes to `work.read.item`; served output includes events, active claims, refs, and dependency fields (`cli.py:item_show`). |
| `task-pickup` step 6 | `sprintctl item ref list --id <item-id> --json` | unsupported (P0) | No `item.ref.list` served route; the handoff observed direct-store fall-through. Item-show's embedded refs are not a replacement for the explicit list contract. |
| `task-pickup` step 6 | `sprintctl item dep list --id <item-id> --json` | unsupported (P0) | No `item.dep.list` served route. Add a served inspection route or replace the guidance with a tested item-show composition. |
| `task-pickup` step 7; `sprint-resume` step 4 | `sprintctl claim start --item-id <item-id> ... --json` | served | `claim.start` routes to `work.claim.start`; the deployed verdict includes claim start. |
| shared/project orientation | `sprintctl usage --context --sprint-id <id> --json` | unsupported (P0) | No served route; the handoff records direct PostgreSQL fall-through and integer-only scope. It needs a served context aggregate and `repo#id` support where scope is ambiguous. |
| shared/project orientation | `sprintctl usage --context --project --json` | unsupported (P1 decision) | The project composition in `cli.py:usage_cmd` opens project stores. No catalog aggregate has been established. |
| project orientation | `sprintctl sprint list --project ... --json` | unsupported (P1 decision) | `SERVED_COMMAND_ROUTES` explicitly excludes project-scoped sprint lists and `cli.py:sprint_list` rejects it in served mode. |
| project orientation | `sprintctl sprint show --detail --json` | unsupported (P1 decision) | `cli.py:sprint_show` explicitly rejects served `--detail`: health/track aggregation has no catalog operation. |

## Inspect, claim, resume, and iterate

| Guidance source | Prescribed command or operation | Status | Evidence and required disposition |
| --- | --- | --- | --- |
| `sprint-resume` step 3 | `sprintctl sprint show --json` | served | `sprint.show` routes to `work.read.sprint`; basic show is in the deployed happy path. Use `--id repo#id` when a scoped identifier is needed. |
| `sprint-resume` step 3 | `sprintctl item list --sprint-id <id> --json` | unsupported (P0) | No `item.list` served route; the handoff observed direct PostgreSQL fall-through. |
| `sprint-resume` step 3 | `sprintctl claim list --item-id <item-id> --json` | unsupported (P0) | No `claim.list` served route. |
| `sprint-resume` step 3 | `sprintctl claim resume --instance-id <id>` / `--runtime-session-id <id>` | unsupported (P0) | No `claim.resume` served route. This is a blind-agent recovery requirement, not permission to inspect a direct store. |
| `sprint-resume` step 4 | `sprintctl claim heartbeat --claim-id ... --claim-token ...` | served | `claim.heartbeat` routes to `work.claim.arbitrate`; deployed happy-path evidence includes heartbeat. |
| `sprint-resume` step 5 | `sprintctl agent-protocol --json` | served (static) | Local command-shape help only; it neither opens a store nor establishes server state. Keep its examples aligned with served command contracts. |
| `sprint-resume` step 7; `item-done` step 2 | `sprintctl event add --sprint-id <id> --item-id <item-id> ...` | served | `event.add` routes to `work.event.add`; the deployed verdict includes event creation. |
| blind-agent shaping requirement | `sprintctl item ref add` / `item ref remove` | unsupported (P0) | No served routes. Required before a served agent can create fully shaped work. |
| blind-agent shaping requirement | `sprintctl item dep add` / `item dep remove` | unsupported (P0) | No served routes. Required before a served agent can establish dependency state. |
| `sprint-resume` step 8 | `sprintctl claim handoff --claim-id ... --claim-token ...` | served | `claim.handoff` routes to `work.claim.arbitrate`; deployed happy-path evidence includes handoff. |
| `sprint-resume` step 8; workspace switching guidance | `sprintctl handoff --sprint-id <id> --output <path>` | unsupported (P0) | No served route; the handoff records integer-only direct behavior. Implement tracker handoff (including `repo#id`) before prescribing it to a served blind agent. |
| `sprint-resume` step 9; `item-done` step 4 | `sprintctl item done-from-claim --id <id> --claim-id ... --claim-token ...` | unsupported (P0) | No `item.done-from-claim` served route. The currently served `item status` route is not an ownership-proof replacement. |
| close/release part of the loop | `sprintctl claim release --claim-id ... --claim-token ...` | served | `claim.release` routes to `work.claim.arbitrate`; deployed happy-path evidence includes release. |
| `sprint-resume` steps 4 and 9 | `.sprintctl/claims/claim-<item-id>.token` | recovery-only | Local proof persistence is a crash-recovery aid. It must never be inferred as server truth and must not be passed to agents. |
| `sprint-resume` step 10 / `item-done` step 5 | `sprint-snapshot` | recovery-only | Repository-generated projection/snapshot workflow, not a Vuoro served authority operation. It cannot substitute for tracker reads or handoff. |

## Knowledge handoff and preflight

| Guidance source | Prescribed command or operation | Status | Evidence and required disposition |
| --- | --- | --- | --- |
| `kctl-extract` step 2 | `kctl preflight --sprint-id <id>` | unsupported (P1 decision) | `kctl/extract.py:run_preflight_for_source` explicitly reports that served Sprintctl lacks a `maintain.check` equivalent. It must report that stable served-unavailable result, not a database-install hint. |
| `kctl-extract` step 2 | `sprintctl maintain check --sprint-id <id>` | recovery-only | Direct-store diagnostic with no served equivalent; retain only for separately authorized recovery, not normal blind-agent execution. |
| `kctl-extract` steps 4–9 | `kctl extract`, `kctl review list/show/approve/reject`, `kctl status` | unsupported | Only the Sprintctl **event source** for `kctl extract` is evidenced as served in the deployed verdict. The checked-in kctl CLI still opens its own local knowledge store for extraction/review/status; no complete served CLI acceptance has been recorded. Do not claim four-domain parity until these commands are either served and tested or the guidance gives an approved composition. |
| `kctl-extract` step 10 | `kctl publish`, `kctl render` | unsupported | Publication/render remain kctl-owned persistence/output operations in the checked-in CLI. No served blind-agent acceptance evidence exists; keep them outside the normal loop pending an explicit domain decision. |

## Implementation queue implied by this inventory

P0 served work is: `usage --context`; `item list`; ref/dependency list and
mutations; claim list/list-sprint/show/resume; tracker `handoff`; and
`item done-from-claim` (or a documented ownership-proof equivalent). Every
one must fail closed before `_get_store` until its route and direct tests land.

P1 decisions are: `next-work --explain`, project-wide orientation, sprint
detail, and kctl preflight/knowledge CLI composition. The matrix intentionally
does not turn these into direct-mode instructions.
