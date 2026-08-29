# The durable home for the operative position — 2026-08-29

Extends `docs/assessments/shard-authority-in-fact-2026-08-29.md` (commit `df07a44`).
That assessment stated the problem correctly and got two of its supporting
measurements wrong. Both corrections shrink the problem by orders of magnitude and
change which option is right.

---

## 1. What is true today (measured 2026-08-29)

### 1.1 The operative position is 9 files, ~5 KB

`/projects/dev/_artifacts/*/model/` contains, in total:

| Scope | Records |
|---|---|
| `agentops` | 3 claims (`human-judgment-perpendicular`, `land-work-in-main`, `measure-before-writing`), 4 observations |
| `vuoro` | 2 claims (`narrow-boundary`, `vuoro-non-goals`) |

Nine JSON files. No other scope has a `model/` directory. The thing that answers
"what is this workspace doing and what has it ruled out" is five kilobytes.

### 1.2 The audit shards are ~966 events, not 10,575

| Measure | Count |
|---|---|
| `.ndjson` lines under `_artifacts/**` | 10,578 |
| …under a `<scope>/audit/` directory (auditctl shards) | **966**, in 46 files, 15 scopes |
| …everywhere else | 9,612, in 449 files |
| `audit_event` rows across all 8 `.auditctl/auditctl.db` indexes | 920 |

The 9,612 are not audit events. Sample line from an outctl capture:

```json
{"length":69,"monotonic_ns":47532085650497,"offset":0,"seq":0,"stream":"stderr"}
```

These are outctl terminal capture streams — byte offsets on stdout/stderr. **No
`outctl-*` directory contains an `audit/` subdirectory at all.**

Consequence: the outctl scopes need no audit disposition because they hold no audit
records.

### 1.3 The served substrate is deployed and migrated

`df07a44` states the substrate is "built but not deployed". The default kubecontext
on this workstation is `kind-bindery`, a local kind cluster. The real cluster is
reached only through `/projects/dev/appservice/clusters/.kube/config`.

Against the real cluster, in database `vuoro` on `vuoro-postgres-1`:

| Schema | Tables | Migrations applied | Principals | Rows |
|---|---|---|---|---|
| `audit` | 5 (`ingest_observation`, `ingest_receipt`, `ingest_stream`, `schema_migration`, `schema_principal`) | 2 | 2 | **0** |
| `knowledge` | 5 | 3 | 2 | **0** |
| `execution` | 18 | — | — | — |
| `work` | 18 | — | — | — |

`ScheduledBackup vuoro-shared-postgres-daily`, CNPG Barman → Hetzner `hel1`, 30d
retention, continuous WAL. A restore drill completed 5 days ago.

The substrate is deployed, migrated, principal-provisioned, off-site backed up, and
its restore path is rehearsed. It has zero rows because **nothing writes to it**.

Note the table names: `ingest_receipt`, `ingest_observation`, `ingest_stream`. The
schema is shaped as a receipt envelope — precisely what `vuoro-non-goals` permits
("auditctl owns the receipt envelope") and distinct from what it forbids
("no centralized evidence ownership in auditctl").

### 1.4 The missing piece is a client, not a deployment

- `auditctl --help` → `add`, `list`, `rebuild`, `render`. No submit path.
- `auditctl/vuoro_adapter.py` is **server-side**: `register()` binds operation
  handlers into a catalog registry supplied by a Vuoro service.
- `auditctl/pyproject.toml` depends on `vuoro-adapter-kit` and
  `vuoro-schema-runtime`. There is no `vuoro-client` dependency.

"Deploy the served substrate" is not the remaining work. The remaining work is a
client, and none exists.

### 1.5 `metanarrative.py publish` — the one documented durability path — is broken

`model/README.md` already settles ownership: *"kctl is the claims store… `publish`
hands a claim over as a knowledge entry. No parallel knowledge store is introduced."*
That path does not work on this host, for two independent reasons.

`scripts/metanarrative.py:224–247` invokes
`kctl publish --title <id> --body <…> --category <tenet|direction|decision>`.

1. **Category rejected.** Installed kctl has
   `VALID_CATEGORIES = {"decision", "pattern", "lesson", "risk", "reference"}`.
2. **`--id` omitted.** Installed `kctl publish` requires `--id INTEGER` — it
   *promotes an approved candidate*; it does not create an entry from nothing.

(1) is stale-install drift: kctl `main` carries `d1ee773 feat(knowledge): admit tenet
and direction as knowledge categories`. A `uv tool install` refresh fixes it. (2) is
a genuine API mismatch requiring code: a claim is not a candidate.

Both repo and installed tool report version `0.1.3`, so version strings do not reveal
the drift.

### 1.6 kctl is not served either — same defect, second instance

`AGENTS.md` classifies kctl "Durable, authoritative | Served". `kctl/README.md` says
of itself: *"Local-first: SQLite on disk, convergence through committed markdown"* and
*"Not a hosted service or remote knowledge store"*. Measured: five per-repo
`.kctl/kctl.db` files. Nothing served.

But kctl **does** have a working durability path, in use:
`homelab-analytics/docs/knowledge/knowledge-base.md` (1010 lines) and
`aligned-equity/docs/knowledge/knowledge-base.md` are committed renders.

`agentops` — the scope holding 7 of the 9 operative records — has **no `.kctl`
directory and no `docs/knowledge/`**. `vuoro` has neither `.kctl` nor `.auditctl`.

### 1.7 sprintctl's row is true

`sprintctl-cnpg-main` healthy, daily ScheduledBackup to Hetzner S3, 30d retention,
monthly restore drill; every `.sprintctl/backend.json` sampled reads `"served"`. Of
the three "Durable, authoritative | Served" rows, exactly one is true.

### 1.8 The recovery policy is same-device and has gaps

- `/projects` → `/dev/nvme0n1p1[/@projects]`, btrfs.
- Snapshot timers run and succeed.
- Snapshots land in `/projects-snapshots` → **the same physical device.** Device loss
  loses both.
- Retention is not continuous: `daily-2026-08-24`, `daily-2026-08-27` and
  `weekly-2026-W33` are absent.
- The TrueNAS copy is **not** a replica: a different filesystem, `_artifacts/` stale
  since 2026-08-15 and `_artifacts/agentops/` since 2026-07-13. A migration remnant.
- No restic/borg/rsync unit covers `/projects`.

### 1.9 In-repo artifact roots already exist and are already committed

| Repo | Committed under `_artifacts/` |
|---|---|
| `agentops` | 20 tracked files — session notes, acceptance candidates/reports |
| `homelab-analytics` | `_artifacts/homelab-analytics/audit/events-2026-08-29.ndjson` |

Neither repo's `.envrc` sets `AUDITCTL_ARTIFACTS_ROOT`. Six repos do, all to
`/projects/dev`. The fallback is `templates/dispatch/artifacts-root.default`, tracked,
contents `/projects/dev`.

`metanarrative.py:50` stores model records at
`_artifacts_root()/_artifacts/<scope>/model` — the same root auditctl uses. Model
records and audit shards move together by construction.

### 1.10 The observation record is itself unmeasured

`observation-evidence-is-semi-ephemeral.json` asserts "deployed nowhere" and "10,575
events across 43 scopes". Both are false per §1.2 and §1.3. The record corroborating
`measure-before-writing` was written without measurement. The failure mode reproduces
inside the mechanism built to catch it.

---

## 2. The decision frame

Three questions, kept apart because conflating them is the original defect.

**Durability** — will the bytes survive loss of this workstation's NVMe device?
**Availability** — can another host read them without a manual copy?
**Authority** — which record is the one you are allowed to believe?

| Record class | Bytes | Durable today? | Reconstructible from? | Needs durable | Needs cross-host |
|---|---|---|---|---|---|
| Metanarrative claims + observations | ~5 KB | **No** | nothing | **Yes** | Weak — git pull suffices |
| auditctl NDJSON shards | ~1.5 MB | **No** | nothing | **Yes** | No — append-only, host-origin |
| auditctl sqlite index | 500 KB | No | shards, via `rebuild` | No | No |
| kctl entries (per-repo sqlite) | small | Partly | rendered markdown where render ran | Yes | Via git |
| Rendered `knowledge-base.md` | — | **Yes** (git) | — | already | already |
| sprintctl work state | — | **Yes** (CNPG + S3 + drill) | — | already | already |
| Session notes | small | Partly | transcripts (lossy) | Medium | No |
| Acceptance candidates/reports | — | **Yes** (committed) | re-runnable | already | via git |
| outctl run captures | ~270 MB | No | nothing | **No** — superseded experiments | No |

**Everything that must survive host loss to reconstruct the operative position is
~1.5 MB.**

### The ownership tension dissolves under measurement

Every model record carries a `scope`, and both extant scopes — `agentops`, `vuoro` —
are repositories with remotes. The `dev` scope has audit events and **zero** model
records. No new home is needed, so **no non-goal is engaged**: the two repos being
enabled are the two that already hold records.

### The load-bearing observation

`model/README.md` places records "beside the audit shards, not in the repository
working tree", and its stated reason is that model records are evidence-adjacent.
**That reason survives; only the conclusion was contingent.** It assumed the shards
were somewhere durable. If the shards move into the repository, "beside the audit
shards" and "in the repository working tree" become the same location. The rule is
preserved verbatim and the defect disappears — which is why the recommendation does
not require amending `model/README.md`.

---

## 3. Options

### A — Root artifacts at the repository

Set `AUDITCTL_ARTIFACTS_ROOT="$PWD"` per repo; shards and model records land under
`<repo>/_artifacts/<scope>/` and are committed.

- **For:** precedent already committed in two repos. Satisfies `vuoro-non-goals`
  literally — repo shards become actual repo shards. One `.envrc` line per repo.
  Per-repo and reversible. Replication is the same push that carries the code.
- **Against:** splits history at a cutover date. Cross-scope `auditctl list` is lost —
  `_orchestration` roots at `/projects/dev` deliberately for that. Committed shards
  become rebasable: a force-push can rewrite records whose whole value is being
  append-only. `rebuild` becomes per-root.

### B — Build a served client

- **For:** the only option delivering cross-host availability, which git does not. The
  server half is done, deployed, migrated and backed up. Writing to `ingest_receipt`
  is expressly inside `vuoro-non-goals`.
- **Against:** no client exists and none is a small change. Nothing currently *needs*
  cross-host reads — three trees exist, one is active. Building it now is the
  "federation schema on speculation" shape.

### C — Replicate `_artifacts/` off-host

- **Against:** `AGENTS.md` already settles this — *"`_artifacts/` content can be copied
  to every host without becoming authoritative"*. C buys durability while
  institutionalizing the durability/authority conflation this plan exists to remove.
  Also drags ~270 MB of dead outctl captures. **Reject.**

### D — Fix `publish` and render the position to committed markdown

- **For:** already the decided design. Small: a `uv tool install` refresh plus a
  candidate-creation step. Proven pipeline.
- **Against:** publishing is a **projection**, not durability of the record. Render
  flattens `state`, `established_by`, `basis_for`, `validity` into prose. D makes the
  position *readable* after host loss; it does not make it *recoverable*.

---

## 4. Recommendation: A now, D alongside, B deferred, C rejected

**A** is the only option that makes the authoritative record durable rather than a
lossy projection of it, costs six `.envrc` lines and two commits, satisfies
`vuoro-non-goals` on its own terms, and preserves `model/README.md` unamended.

**D** runs alongside because a rendered position is what a session actually reads, and
because fixing `publish` is a prerequisite for `model/README.md` being true rather
than aspirational. D is not a substitute for A.

**B** is deferred, not rejected. It answers availability and A does not. Reopen it by
a *consumer* — the first time a second host must read the operative position without
a `git pull`.

### Failure modes

- **Committed evidence is mutable evidence.** A rebase or force-push can silently
  rewrite an append-only record. Git gives durability and takes away immutability.
  Mitigation is a protected-path or pre-push check on `_artifacts/**/audit/`, and that
  check does not exist. This is the strongest argument against A.
- **Split history.** "What happened in scope X" requires reading two roots.
- **Loss of the cross-repo view.** `_orchestration` roots at `/projects/dev` on purpose.
- **Repo bloat if volume grows.** 966 events is nothing; 100k with `events.db`
  binaries committed alongside is not. No declared threshold.
- **A is wrong in six months if** the served client lands (B), at which point committed
  shards become a redundant second copy with weaker immutability than the store that
  supersedes them — and un-committing evidence is harder than committing it.
- **`vuoro` is not on `main`** (branch `e8-principal-subject`), and `land-work-in-main`
  is a current claim.

---

## 5. First slice

1. **Correct the record before acting on it.** Amend `df07a44`'s counts and its
   "deployed nowhere" claim, and supersede `observation-evidence-is-semi-ephemeral`
   with a measured replacement. Every later step cites those numbers.
2. **Refresh the kctl install** from `main` (`d1ee773`). Verify positively:
   `kctl publish --help` must list `tenet` and `direction`.
3. **Root `agentops` at itself.** `AUDITCTL_ARTIFACTS_ROOT="$PWD"` in `agentops/.envrc`
   (and track the file — currently untracked). Copy the model records and shards into
   `agentops/_artifacts/agentops/`, commit to `main`. Verify `auditctl rebuild`
   reproduces the index from the committed shards.
4. **Root `vuoro` at itself** — after its branch lands, per `land-work-in-main`.
5. **Fix `metanarrative.py publish`** to create a kctl candidate and promote it, then
   render `agentops/docs/knowledge/knowledge-base.md`.
6. **Correct `AGENTS.md`'s storage table.** `auditctl` → `host-persistent`, becoming
   `cross-host-replicated` per scope as repos are rooted. `kctl` → durable through
   committed render, **not** served. `sprintctl` unchanged.
7. **Add the pre-push guard** on `_artifacts/**/audit/` before step 3's precedent
   spreads. `templates/dispatch/scripts/check_protected_paths.py` is the natural home.

### On detection

**A separate scenario, plus one addition to the existing one.**

`align-and-converge`'s subject is repository participation. Durability-class drift is
a different subject — whether a store's *declared* durability class matches its
*measured* one. Bolting it on blurs a scenario whose value is a sharp subject.

Two things found here **are** in align-and-converge's declared scope and should join
its `drift_cases_that_must_be_detected`:

- A stale installed tool whose version string matches the repo's while its behaviour
  does not — `per-host-state-compared` plus "a documented instruction that no longer
  works is reported as drift".
- A default kubecontext pointing at a different cluster than the one a claim is about
  — the sharpest instance of "empty is not absent" here, and squarely "state outside
  the repository is compared, not assumed".

The new scenario should generalize what this investigation did by hand: for every row
of the `AGENTS.md` storage table, a probe with a **positive control** that proves the
claimed durability class. Written to fail.

---

## 6. What this plan deliberately does not decide

- **Whether to build the served client (B).** Deferred to a consumer, not a date.
- **Disposition of the `dev` scope** and the throwaway scopes (`l2b`, `l2b-overlay`,
  `p3-driver`, `wt-*`, `V6-K-human-turns`). No repository to be rooted at.
- **Whether pre-cutover shards migrate.** Step 3 copies agentops's; nothing else.
- **The outctl captures** — ~270 MB holding zero audit records. A space question, not
  a durability one. Do not migrate.
- **Whether `_orchestration` keeps its `/projects/dev` root.** It has a real reason to.
- **`model/README.md` is not amended.** Under A its rule stays true as written.
