# Are the shards authoritative in fact? — 2026-08-29

**Sequence:** cross-repo dogfood plan §5, R1 bullet 2 — *"Make shards authoritative in
fact: the publisher appends to the shard before indexing, and `rebuild` fails on
index-only, duplicate or corrupt events."*

The bullet's own wording concedes they are not authoritative in fact yet. This records
what is actually true, because the answer is not the one the bullet anticipates.

## The two halves the bullet names are done

**Publisher ordering** is already correct. `auditctl add` appends inside the sqlite
transaction and rolls back on failure, so an event cannot reach the index without reaching
the shard. The 25 index-only events found on 2026-08-28 were **not** a publisher fault —
all 25 ids are in `.auditctl/archive/auditctl-retired-2026-08-26.db`, artifacts of the
ledger retirement.

**`rebuild` refusing index-only events** landed on auditctl `main` as `d88a34c`
("rebuild reported success while dropping events no shard carries"), with tests.

## The half the bullet does not name, and it is the load-bearing one

**Nothing that auditctl writes is durable-authoritative today, and the shards are not repo
shards.**

`/projects/dev/AGENTS.md` classifies storage explicitly:

| Storage | Durability | Cross-host |
|---|---|---|
| `auditctl` | **Durable, authoritative** | **Served** |
| `/projects/dev/_artifacts/` | **Semi-ephemeral** | **Host-local unless explicitly copied** |

Those two rows describe the same bytes. Every `auditctl add` on this workstation writes a
host-local sqlite index plus an NDJSON shard under `/projects/dev/_artifacts/<scope>/audit/`,
and **that directory is in no git repository** (`git rev-parse` there: *not a repository*).
So the row claiming durable-authoritative and the row claiming semi-ephemeral both apply,
and the second one is the true one.

The served-audit substrate is **built but not deployed**. `auditctl.vuoro_adapter.
VuoroAuditAdapter` registers submit, receipt, bounded-read, stream-status and compatibility
operations when a Vuoro service supplies a catalog registry — and the README is careful to
say "the optional served-audit substrate remains separate from local capture" and "normal
`auditctl` startup never connects to the central schema". A cluster-wide deployment query
returns no audit workload. There is nothing serving it.

### What is actually at stake

| Scope | Events | Shards |
|---|---|---|
| agentops | 974 | 14 |
| outctl (all A/B run scopes) | ~7,900 | ~400 |
| dev | 191 | 7 |
| bindery-core | 42 | 3 |
| scribectl | 52 | 5 |
| sprintctl | 46 | 7 |
| homelab-analytics | 17 | 5 |
| others | ~150 | ~20 |
| **Total** | **10,575** | — |

Ten and a half thousand events whose stated recovery policy is the workstation's local
Btrfs snapshots — 7 daily, 4 weekly (`AGENTS.md`, Shared workspace). No off-host copy, no
replication, and by the same document's own vocabulary they may not be described as
"durable".

### The sharper case: the operative position lives there too

`templates/dispatch/model/README.md` places metanarrative records beside the audit shards
— *"they belong beside the audit shards, not in the repository working tree"* — so
`/projects/dev/_artifacts/<scope>/model/` holds every claim and observation. As of today
that includes the claims that state what this workspace is currently doing:

- `agentops`: `land-work-in-main`, `measure-before-writing`, `human-judgment-perpendicular`,
  and three observations.
- `vuoro`: `narrow-boundary` and `vuoro-non-goals` — the operative direction and the nine
  binding non-goals, recorded 2026-08-29.

The model's governing rule is that *current claims describe the operative position*. Those
claims are the answer to "what is this workspace doing and what has it ruled out", they are
consulted by `realign` before work starts, and they exist in exactly one semi-ephemeral
place on one host.

## The finding, stated plainly

This is not a bug in auditctl. It is a **conflict between two authoritative documents**,
and each is internally consistent:

- `AGENTS.md` says auditctl is durable-authoritative and served. True of the *design*.
- `AGENTS.md` says `_artifacts/` is semi-ephemeral and host-local. True of the *storage*.
- `model/README.md` says model records belong beside the audit shards. True, and it makes
  the operative position inherit the shards' durability class.

The design assumed the served substrate would be deployed. It is not, so the durable
column describes an intention and the semi-ephemeral column describes the filesystem.

## Recommendation

Two options, and they are not equivalent.

1. **Deploy the served-audit substrate.** This is what every document already assumes and
   what makes the `AGENTS.md` table true as written. It is also the larger piece of work,
   and `auditctl` 0.1.3 is still unreleased because its release contract binds a
   verification-packet digest to a tree including `pyproject.toml`, needing a central
   verification run that requires PostgreSQL binaries the workstation lacks.
2. **Make the shards genuinely repo shards** by rooting `AUDITCTL_ARTIFACTS_ROOT` at each
   repository rather than at `/projects/dev`, so evidence is versioned and replicated by
   the same Git that carries the code it describes. `homelab-analytics` already works this
   way as of 2026-08-29 — its shard is committed at
   `_artifacts/homelab-analytics/audit/events-2026-08-29.ndjson`. This costs nothing to
   start, is per-repo and reversible, and matches the operative non-goal that *repo shards
   stay authoritative*.

Option 2 is not a substitute for option 1 — a served substrate answers cross-host
availability, which Git does not. But option 2 removes the single-host durability exposure
today, and the two compose.

**This is an architecture decision and belongs to the owner**, not because a human must
approve it, but because it changes a storage contract that three documents depend on and
would move ten thousand existing events. Recorded here rather than decided.

## Consequence for R1's gate

R1's gate is *D1, D2, D3, D6(interrupt) hold for scribectl*. **D3 (rebuild) holds** — the
mechanism works and is tested. What does not hold is the premise underneath D2's receipts:
a receipt is evidence that something happened, and a receipt whose only copy is
semi-ephemeral and host-local is not yet the durable reference the settlement path assumes.

R1 can proceed. The gate should be read as *"the rebuild mechanism is correct"*, not as
*"evidence is durable"*, and that distinction should be stated when the gate is claimed.
