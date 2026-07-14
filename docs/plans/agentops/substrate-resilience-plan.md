# substrate resilience plan

Failure taxonomy, recovery procedures, and identified gaps for the agent-ops substrate. Companion to `agent-ops-substrate-plan.md`. This plan does not change the substrate architecture; it identifies what breaks under each failure mode, what recovers automatically, and what requires new mechanisms or operator action.

## Backup posture (what is protected today)

### CNPG databases → Hetzner S3 (Barman)

Both agent-ops PostgreSQL clusters are backed up via CNPG Barman to Hetzner Object Storage:

| Cluster | Namespace | Schedule | Retention | Restore drill |
|---|---|---|---|---|
| `actionq-cnpg-main` | `vscode` | Daily ~02:25 | 30 days | Monthly CronJob |
| `sprintctl-cnpg-main` | `vscode` | Daily (staggered) | 30 days | Monthly CronJob |

WAL archiving is continuous; PITR within the retention window is available. Encryption is disabled at the Barman layer due to Hetzner S3 rejecting SSE-S3 headers — the S3 bucket itself provides at-rest protection. See `appservice/docs/backups-cnpg.md` for restore runbooks and drill commands.

This means the durable queue state (all actionq actions, events, coordinator emissions) and the remote-mode sprint state (all sprintctl sprints, items, events, takeup history across all remote repos) survive any CNPG pod or Longhorn volume failure and can be restored to any point within 30 days.

### Git repositories

All implementation repos push to GitHub (`bayleafwalker/`). The canonical copy of every repo's code, commit history, and plan docs is off-cluster. A full workspace rebuild from git is always possible.

### Workspace PVC (cluster-managed backup verified 2026-07-14)

The workspace PVC (`truenas-workspace-pvc`, namespace `vscode`) is an NFS-backed volume served by TrueNAS at `/mnt/storage_layer/projects`. It is mounted into the vscode-shell pod as `/projects/dev` and `/home/dev`.

An earlier revision of this plan claimed the workspace PVC had "no VolSync ReplicationSource or other cluster-managed backup". **That claim is stale.** Per the verified reconciliation in `ops-upgrade-reconciliation-2026-07.md` (facts 4 and the runtime-verified backup state section):

- **Implemented in GitOps:** `appservice/clusters/main/kubernetes/apps/vscode/app/workspace-backup.yaml` defines a daily Restic backup (03:55 UTC, with retention policy and excludes) plus a monthly restore drill with dedicated PVCs.
- **Deployed / runtime-verified (2026-07-14):** CronJobs `workspace-backup` and `workspace-restore-drill` exist in namespace `vscode` and are not suspended.
- **Last successful backup:** job `workspace-backup-29733355` completed 2026-07-14T03:56:19Z. Verified green.
- **Last successful restore drill: unknown for July.** Drill CronJobs last scheduled 2026-07-01, but the job history from that date was garbage-collected; the only surviving drill evidence is a manual `sprintctl-cnpg-restore-drill-remediation-20260712` job (completed 2026-07-12). Drill outcomes are **not durably observable**.

The remaining gap is therefore **drill observability/alerting and semantic restore validation, not backup existence**. Do not plan or backlog building a workspace backup — it exists and runs.

TrueNAS's own ZFS snapshot and replication practices remain an additional, independently managed layer. If both the Restic backup and TrueNAS snapshots fail to cover a loss window, the following would be lost without recovery path:

- Per-repo SQLite databases: `auditctl.db`, local-mode `sprintctl.db`, `kctl.db`
- NDJSON audit shards: `_artifacts/<repo>/audit/events-*.ndjson`
- kctl knowledge NDJSON: `_artifacts/<repo>/knowledge/*.ndjson`
- Agent session worktrees: `~/.local/state/actionq-dispatcher/worktrees/`
- The vscode-home subPath: tmux sessions, shell history, local tool installs in `~/.local/`

See **Open items** for the remaining drill-observability gap.

---

## Failure taxonomy

### Ring 1: Process death (pod restart, daemon crash, OOM)

**What happens:**

The vscode-shell pod uses `strategy: Recreate`. When the pod restarts, all running processes are killed. The workspace PVC (TrueNAS NFS) and its contents survive. CNPG clusters are unaffected.

Specific consequences:

| What died | Immediate effect | Auto-recovery | Requires action |
|---|---|---|---|
| vscode-shell pod | SSH sessions drop; all foreground processes die | Pod restarts via Deployment controller | Reconnect via SSH |
| actionq-daemon | In-flight sessions orphaned; no more heartbeats or audit emission | `actionctl sweep` requeues timed-out actions after `claim_deadline` | See **daemon startup recovery** |
| Agent harness (claude/codex) | Session exits; worktree preserved on PVC | None automatic | Inspect worktree; re-dispatch or abandon |
| sprintctl takeup | Sprint remains "taken up" with no liveness signal | None (no TTL on takeup) | See **takeup sweep** |

**Claim deadline and sweep.** Every actionq action has a `claim_deadline`. `actionctl sweep` requeues any action whose deadline has passed. If sweep runs regularly (via cron or daemon startup), orphaned actions re-enter the queue without operator intervention. The gap is the window between pod restart and the next sweep run — actions claimed during that window stay "claimed" until swept.

**Worktree fate.** Worktrees are on the workspace PVC. They survive pod restart. A requeued action will create a new worktree on re-dispatch; the old worktree is left for inspection per existing runbook guidance.

---

### Ring 2: SSH connectivity loss

**Intermittent loss (seconds to minutes).** tmux sessions survive. Any agent harness running inside tmux continues. The operator reconnects and reattaches. No substrate state is affected.

**Extended loss or tty-death without tmux.** The foreground process (interactive session, or an agent running directly in the SSH shell) dies with the controlling tty. The actionq-daemon, if running in the foreground without tmux, also dies — returning to the Ring 1 scenario above.

**Operational invariant:** the daemon and any long-running agent session must be started inside a named tmux session. This is not enforced by the current infrastructure. See **tmux enforcement** below.

---

### Ring 3: PostgreSQL unavailability

**sprintctl remote-mode:** all sprint operations fail with a clear error. No local queue, no silent fallback. Sessions holding takeup must be re-acquired on recovery via `sprintctl takeup take --force`. This is the defined behavior from the substrate plan.

**actionq:** all queue operations fail. The daemon cannot claim new work. In-flight sessions whose claims are already held continue until their `claim_deadline`; after that, `sweep` requeues them once pg is back.

**Cockpit:** degrades gracefully per the workstream E plan. The pg-down degraded state hides sprint panes; audit NDJSON and actionq session reads remain available independently.

**Recovery:** CNPG self-heals via its operator. If the Longhorn volume is lost, restore from Barman S3 backup using the runbook in `appservice/docs/backups-cnpg.md`. PITR to the last WAL position is available within the 30-day retention window.

---

### Ring 4: NFS / workspace PVC unavailability

**What happens:** `/projects/dev` is unreachable. All repo checkouts, SQLite databases, NDJSON shards, and worktrees are inaccessible. CNPG data is unaffected. The vscode-shell pod will likely restart (or become unhealthy) if the NFS mount hangs rather than returning an error.

**Recovery:** wait for TrueNAS NFS to recover. All git-tracked data is recoverable from remotes. SQLite databases for local-mode tools must be reconstructed:
- `auditctl.db`: `auditctl rebuild --from-ndjson <path>` if NDJSON shards are intact; otherwise lost.
- `kctl.db`: re-extract from sprintctl events (`kctl extract`).
- Local-mode `sprintctl.db`: unrecoverable without the file (remote-mode repos are not affected; local-mode repos lose sprint history not reflected in git commits).

**NDJSON shard loss:** if TrueNAS data is lost (not just temporarily unavailable), audit shards in `_artifacts/` are gone. They are not reconstructible from CNPG data alone — audit events are emitted asynchronously and are not stored in pg. The recovery path is the daily Restic workspace backup (see backup posture above) or a TrueNAS ZFS snapshot. See **Open items: workspace backup** for the drill-observability gap.

---

## New mechanisms required

### 1. Daemon startup recovery

**Gap:** the daemon starts fresh with no memory of sessions that were in-flight when it last ran. It cannot distinguish "that session is still running" from "that session died when I did."

**Mechanism:** on startup, before claiming any new work, the daemon executes a recovery sweep:

```
for each session in actionctl sessions --active:
    if pid is alive (os.kill(pid, 0)):
        log "re-adopting session <id>"; add to session table; restart heartbeat ticker
    else:
        emit session.exited (exit_code=null, reason="daemon-restart-recovery")
        auditctl add --type session.exit --summary "Session <id> exit inferred at daemon restart"
        sprintctl takeup release <sprint-id> --force (if session had a takeup)
        # actionctl sweep will requeue the action after claim_deadline; no immediate requeue
```

This requires the daemon to know the PID of each session it previously spawned. The `session.started` coordinator event payload already carries `pid`. The daemon reads this from the actionq event log on startup.

**Who implements:** `actionq-dispatcher` (or `actionq-daemon` once that's the canonical name).

---

### 2. Takeup sweep

**Gap:** sprintctl sprint takeup has no TTL or automatic expiry. A sprint stays "taken up" indefinitely if the session that took it up dies without releasing.

**Mechanism:** `sprintctl takeup sweep [--stale-after <seconds>]` cross-references actionq session state. For each active takeup:

1. Extract `runtime_session_id` from the `sprint-taken-up` event payload.
2. Look up the session in `actionctl sessions` output.
3. If the session has `status: exited` or is absent from the session list: release the takeup with `actor=sweep` and `reason=session-not-active`.
4. If `--stale-after N` is provided: additionally release any takeup whose `sprint-taken-up` event is older than N seconds and has no corresponding session at all (handles the case where the session was taken up before the actionq integration existed).

Run automatically by the daemon on startup (after daemon startup recovery runs), and expose as a standalone CLI command for manual use.

**Who implements:** `sprintctl` (new verb in the `takeup` group).

---

### 3. tmux enforcement

**Gap:** there is no enforcement that daemon or agent sessions run inside tmux. An SSH disconnect kills them.

**Mechanism:** operational guidance only — no code enforcement.

The daemon startup script must check for a tmux session and refuse to start outside one:

```bash
if [ -z "$TMUX" ]; then
  echo "daemon must run inside a tmux session; start with: tmux new-session -s daemon"
  exit 1
fi
```

The vscode-shell AGENTS.md should document this as a mandatory precondition. The daemon can be further wrapped in a shell alias or script that opens a tmux window if one doesn't exist.

---

### 4. meta-dispatch orphan recovery

**Gap:** if `dispatcher-meta` dies between child A completing and child B starting, the parent action remains claimed until `claim_deadline`. On re-dispatch after sweep requeues it, the parent would attempt to fan out from scratch — but child A is already completed.

**Mechanism:** on startup, dispatcher-meta checks parent actions in `claimed` state. For each, it reads the work spec from the action payload and the child action states from actionq. Children already in `completed` state are skipped; dispatcher-meta resumes from the first non-completed child. This is a natural consequence of the daemon startup recovery sweep: if the parent action is in the session table (still claimed), recovery re-adopts it and resumes.

No additional code path is required beyond daemon startup recovery; this is a property of reading child action states from the event log rather than from daemon memory.

---

## Operator recovery runbook

### After a pod restart (Ring 1)

```bash
# 1. Reconnect
ssh dev@<shell-ip>

# 2. Reattach tmux (if the daemon was running in tmux before the restart)
tmux attach -t daemon
# If tmux session is gone (pod was killed before detach): proceed to step 3.

# 3. Run sweep to requeue any timed-out claims
actionctl sweep

# 4. Check for stale takeups
sprintctl takeup list --active
sprintctl takeup sweep  # releases takeups whose sessions are no longer active

# 5. Inspect orphaned worktrees (optional; these are safe to leave)
ls ~/.local/state/actionq-dispatcher/worktrees/

# 6. Restart the daemon inside tmux
tmux new-session -s daemon -d
tmux send-keys -t daemon 'dispatcher-once --config /path/to/config.toml' Enter
# or for the long-running daemon:
tmux send-keys -t daemon 'actionq-daemon --config /path/to/config.toml' Enter
```

### After PostgreSQL goes down and recovers (Ring 3)

```bash
# pg recovers automatically via CNPG operator; wait for the cluster to be Ready:
kubectl -n vscode get cluster actionq-cnpg-main sprintctl-cnpg-main

# If a sprint was "taken up" during the outage and the session released cleanly, nothing to do.
# If the session died during the outage:
sprintctl takeup sweep

# Verify queue state:
actionctl ls --status pending
actionctl ls --status claimed
actionctl sweep  # requeue any actions whose claim_deadline passed during the outage
```

### After NFS unavailability and recovery (Ring 4)

```bash
# Wait for TrueNAS NFS to recover and the pod to stabilise.
# Verify the mount is back:
ls /projects/dev

# Reconstruct auditctl index from NDJSON shards if the sqlite file is corrupt:
auditctl rebuild --from-ndjson /projects/dev/_artifacts/<repo-id>/audit

# Reconstruct kctl index from sprintctl events:
kctl extract --sprint-id <id>

# Local-mode sprintctl.db: if the file is corrupt, it is not reconstructible from NDJSON.
# Verify WAL mode is intact:
sqlite3 /projects/dev/<repo>/.sprintctl/sprintctl.db "PRAGMA integrity_check;"
```

---

## Open items

### Workspace backup: drill observability and semantic restore validation

**Resolved (2026-07-14):** the previously described backup gap is closed. A daily Restic backup (03:55 UTC) and monthly restore drill are implemented in GitOps (`appservice/.../vscode/app/workspace-backup.yaml`) and runtime-verified — see the backup posture section above and `ops-upgrade-reconciliation-2026-07.md`. Do not re-propose building the backup.

**Remaining gap:** restore-drill outcomes are not durably observable. The July 1 drill job history was garbage-collected before anyone could confirm success, and a manual `sprintctl-cnpg-restore-drill-remediation-20260712` job indicates the July sprintctl CNPG drill required manual remediation.

**Recommended actions (in priority order):**

1. **Make drill outcomes durable and alerting.** Persist drill success/failure beyond job garbage collection (durable record or push-gateway metric) and alert on drill failure or absence.

2. **Add semantic restore validation.** A drill that only proves files restore is weaker than one that proves the restored data is usable — validate restored SQLite integrity and NDJSON shard parseability, not just file presence.

3. **Verify TrueNAS ZFS snapshot schedule** for `/mnt/storage_layer/projects` and document it explicitly, as the independent second layer of protection.

The critical data on the workspace that is not recoverable from git or CNPG: `_artifacts/` NDJSON shards and local SQLite databases. These are small in total size and high in recovery value.

### `actionq_smoke` schema in production

The vscode-shell pod injects `ACTIONQ_SCHEMA=actionq_smoke`. This was a smoke-test default and appears to be in active use for real dispatch. Before the substrate matures, clarify whether this schema should be promoted to the production schema name (`actionq`) or remain `actionq_smoke` with a documented rationale.

### takeup sweep requires sprintctl + actionq co-location

`sprintctl takeup sweep` needs to call `actionctl sessions` to cross-reference liveness. This creates an implicit dependency: sprintctl must be able to invoke actionctl (or its equivalent API). In the daemon-first deployment (pre actionq-server), both tools are available in the same pod. In a cluster-service deployment, the sweep command would need the actionq-server read API. Flag for workstream C planning.

### Partial NDJSON shard handling

An `auditctl add` that dies mid-write may leave a truncated JSON line at the end of today's shard. `auditctl rebuild` skips malformed lines by design. The sqlite database is the authoritative index; if the shard line is truncated, the sqlite record is intact (dual-write rolls back the sqlite write if the NDJSON write fails, but the reverse — sqlite written, then crash mid-NDJSON-write — can leave a partial line). Add a `auditctl fsck` command that validates today's shard against sqlite and truncates/repairs any partial tail line. This is a low-priority quality-of-life item; `rebuild` already handles it at the cost of a full re-parse.
