# Handoff 2026-09-23-program-long-goal-handler.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Hold the long goal across sessions: E1 reaches first use and agentops#2514 closes, while every orphan follow-up is taken to landed and verified at the artifact. Immediately: finish the operator-signed vuoro-cloud promotion v0.1.0-poc.36.

**Next action.** Confirm vuoro-cloud PR #91 (release/poc36-promotion-candidate, head 8d335a8…, full sha via `git -C /projects/dev/vuoro-cloud rev-parse origin/release/poc36-promotion-candidate`) has all four CI checks green, get the operator's merge approval, fast-forward merge it with credctl, then: fj actions dispatch promote-deployment v0.1.0-poc.36 --repo bayleaf/vuoro-cloud --host git.apps.kotona.app -I deployment_tag=v0.1.0-poc.36 -I image_digest=sha256:3503dddde2f6d4e59eecc320e26a5985cde3f6a775827dd1d8bd294703652ef5 ; then the separate commit pinning the 3 vuoro-cloud images in apps/*/deployment.yaml to ghcr.io/bayleafwalker/vuoro-cloud@sha256:3503…, run scripts/validate-deployment-distribution.py, land it, and verify the running pods' imageIDs.

## Predecessor

- harness: claude-code
- session: 93862d02-be4d-4942-8361-d862b3765ec8
- model: claude-opus-5-5
- context used: 60.0%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-program-long-goal-handler.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Merges: this session had the operator's explicit merge approval 'for this whole session'. It does NOT transfer to a successor: ask the operator again before merging anything.
- Merge only after every CI check reports pass (read the checks; a watch that exits on UNKNOWN is not a pass). appservice: gh pr merge --match-head-commit <FULL 40-char sha>. Forgejo (vuoro-cloud, fast-forward-only): credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr N --head-sha <full sha> --style fast-forward-only --forgejo-url https://git.apps.kotona.app
- Never dereference Secret or SOPS values into your session, a file or a variable (a hook enforces this). Digests (| sha256sum), counts (| grep -c) and key names are allowed. Anything that needs a value runs INSIDE the cluster (a Job with envFrom) or in the operator's own terminal.
- YubiKey signing (vuoro-cloud promotions) is the operator's: PIN once plus two touches, run in their own terminal (pinentry needs a TTY; `!` does not work).
- Every guard is forced into its failure case before it is trusted. Verify at the artifact (live cluster, registry, S3), never at the report.
- Do not arm the Kubernetes upgrade phase while any Talos phase is armed (upgradesettings.yaml). Never overlap.
- Claude memory holds only communication preferences; durable guidance goes in agentops/templates/workspace/AGENTS.agentops.md, rendered with scripts/render_workspace_agents.py --apply from a clean origin/main worktree.
- Work in scratchpad worktrees off origin/main; never pull or edit the shared main checkouts (other sessions' untracked files live there). Never bare git stash (the stack is shared).
- Workers: launch with NO isolation and tell them to `git -C /projects/dev/<repo> worktree add` themselves. isolation:worktree breaks git: the operator's worktree-isolation hook refuses every git command wrapped by `snip`.

## Decisions

- **vuoro-cloud poc.36 promotes main e2e6bc6 = #87 gateway config guards, #88 migrate_tenant re-apply/unique Job name/tenant_schema_version + tenant-controller vuoro-compatibility mount, #89 connector per-operation authority (fail closed), #90 legacy-domain inventory + Secret pruning** — all four merged green (unit + integration under nix postgresql); image digest sha256:3503dddde2f6d4e59eecc320e26a5985cde3f6a775827dd1d8bd294703652ef5 read from publish-image run 626 job 1689 log ('pushing manifest for ...:sha-e2e6bc6...@sha256:3503...')
- **Operator signed: candidate commit 8d335a8, tag v0.1.0-poc.36, branch release/poc36-promotion-candidate, Forgejo PR #91** — scripts/promote-release.sh run by the operator 2026-09-23 22:25 local
- **ghcr digest will equal the Forgejo digest** — promote-deployment.yaml skopeo copy --all to ghcr.io/bayleafwalker/vuoro-cloud and verifies source==replica digest; apps/ pull from ghcr
- **Langfuse landed durable (appservice #1712/#1716/#1717/#1719/#1720/#1722/#1723): ClickHouse on longhorn-static + volsync (PVCs clickhouse-storage-volume-langfuse-clickhouse-0-0-0 / -keeper-0-0), Valkey unbacked (queue), headless init (org appservice, project harness-evidence, user operator@kotona.app; creds in langfuse-init.secret.yaml via sops -d by the operator), 30-day retention = daily TTL CronJob + S3 lifecycle rule langfuse-expire-30d** — verified live: API key pair 200 / wrong key 401, TTL present on 5 tables (job idempotent), both ClickHouse backups Successful
- **Music and Creative-vault restic repos moved to -v2 (appservice #1721, #1724)** — 2026-09-16 repos were split-brain (source + new restore drill ran restic init the same minute: two keys at 18:24; config and data from different inits). NOT a password problem: VOLSYNC_RESTIC_PASSWORD digest d8f159f01e54 unchanged in git and live. -v2 repos have exactly one key each and one snapshot each (Music 32.9 GB); vault drill restored its snapshot 18:50 UTC
- **VolSyncReplicationSourceStale weekly branch now requires a day-of-week value (#1721)** — old regex matched every daily schedule -> 8-day window; Music sat 7 days unbacked silently. Evaluated on live Prometheus: old fired on nothing, new fired on exactly media/media-music
- **flux-substitution-guard in appservice validate (#1725), flux2 installed in CI** — #1722's CronJob shell vars froze the langfuse Kustomization (strict envsubst); guard proven on that file, confirmed running in CI logs
- **hostproto preserved on Forgejo bayleaf/hostproto, on hold (Wave 1 landed, main 0f27836); not registered with cred-broker** — operator choice; GitHub copy archived 2026-08-28 and split into six successors; registration buys agent creds for a frozen repo

## Rejected

- **Deriving connector authority from connector capabilities** — capabilities are placement data; the owner catalog's required_authority is the source (gateway.py ~1122)
- **Dropping legacy execution/knowledge schemas or roles** — irreversible; no destructive migration exists; direction is design-for-use. Inventory + inert credentials only; drop is an oracle/owner decision
- **Holding a volsync drill with trigger.manual** — a manual value != status.lastManualSync IS a pending trigger; it runs at once. To keep a new repo's drill from racing its source, add the drill in a later commit
- **Creating a new restic repo's ReplicationSource and restore-drill ReplicationDestination in one commit** — both init concurrently -> split-brain repo (the Music/vault failure)
- **Recovering the old Music/vault repos with the operator's other restic passwords (B2/Hetzner operational/recovery)** — not a password issue; the repos are split-brain and unrecoverable as a whole; sources were intact so re-upload was the fix
- **Trusting kustomize build / validate alone for chart values** — #1719 put additionalEnvFrom at langfuse.web (ignored by chart 2.1.0; real key langfuse.web.pod.additionalEnvFrom). Render with helm template before PR
- **Using the static backup-coverage-guard to catch a wrong sourcePVC** — it compares mechanisms to the baseline, not PVC existence; the live alert VolSyncReplicationSourceMissingSuccessfulSync is the backstop (went pending for the wrong Langfuse names)
- **Reading registry digests via ghcr or Forgejo registry API with the workstation token** — 403/401 (no read:packages / registry scope); read the digest from the publish job log instead

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `f457df2baa05` | yes | 0 | `f8d8b7c7802b4a5a…` |
| `/projects/dev/appservice` | main | `ad201c478b66` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud` | main | `8d335a8987e1` | no | 1 | `e3b0c44298fc1c14…` |
| `/projects/dev/hostproto` | main | `0f27836a2bf3` | yes | 0 | `eec7c952b2c1a5c4…` |

**Running:**

- In-cluster Jobs media/restic-verify-music (restic check --read-data-subset=5%) and obsidian/restic-verify-vault (--read-data); ttlSecondsAfterFinished 86400. Read with kubectl logs job/<name>.
- Music restore drill: media/media-music-restore-drill has a live spec.trigger.manual=prove-<epoch> set by kubectl patch. It MUST be removed after status.lastManualSync matches (kubectl -n media patch replicationdestination media-music-restore-drill --type=json -p '[{"op":"remove","path":"/spec/trigger/manual"}]'), or its monthly schedule stays ignored. A trap in the predecessor's background job removes it; confirm it is gone.

## Unresolved

- E1 first use + branch sweep has no live owner: the E1 successor (handoff 2026-09-23-e1-first-use-and-branch-sweep.v2, acked by deb100ae) has ended; it was paused awaiting the operator's --no-tree-check answer. Relaunching needs a new handoff version (the ack guard names the dead session).
- Talos v1.14.1 rollout has no live owner: session b2ec1d19 ended, paused on operator decisions for the worker-2 window, all gates disarmed at appservice ad201c47. The Kubernetes phase drift (kubelets v1.36.4 vs pin v1.37.0) waits on that rollout finishing; checkback now reports both as ATTEND.
- Old unusable restic prefixes volsync/media/media-music-nfs-pvc/ (32.9 GB) and volsync/obsidian/obsidian-vaults/ on Hetzner: delete only on the operator's yes.
- Legacy-role NOLOGIN on vuoro-cloud tenant DBs: after poc.36 deploys, run scripts/legacy-domain-inventory.py IN-CLUSTER (admin URL is a secret) and give the printed ALTER ROLE ... NOLOGIN statements to the operator.
- The Creative vault export (obsidian-vaults-nfs-pvc-v2) holds ~7 KB; where the real Creative content lives is an open question from e5a3f54a.
- #87 deploy note: control/gateway now refuse to start if their gateway private/public key files disagree; the tenant-shipped PEM is never cross-checked in prod (controller has only the PEM).

## Evidence

- artifact: `docs/dispatch/handoffs/2026-09-23-program-long-goal-handler.v1.json`
- artifact: `docs/dispatch/handoffs/2026-09-23-e1-first-use-and-branch-sweep.v2.json`
- artifact: `docs/dispatch/handoffs/2026-09-23-talos-1-14-1-fleet-rollout.v1.json`
- artifact: `/projects/dev/vuoro-cloud/CLAUDE.md (promotion: lines ~91-110)`
- sprintctl: `agentops#2514 note 3599; agentops#2394`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: (unacknowledged)
- acknowledged: —
