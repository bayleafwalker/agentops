---
status: reference
owner: operator-designated coordinator (default-assigned 2026-11-07)
last_verified: 2026-11-07
---

# Landscape review: closing the "unverified" items (2026-11-07)

The 2026-11-07 landscape alignment review
(`/projects/dev/_artifacts/deep-research/reports/Agentic substrate landscape alignment.md`,
section "What this review did not verify") left three groups of facts
unobserved. This page records what read-only checks established on
2026-11-07, between about 13:40Z and 14:00Z. It is an observation record, not a plan,
and it decides nothing. [silent-drop-check.md](../../plans/silent-drop-check.md)
was the starting list.

Method, all read-only unless noted:

- PR #255 (the split-horizon direction; it is a PR, not an issue) was read
  with `gh pr view 255 -R bayleafwalker/agentops --json body,comments`.
  The decisions themselves are in
  `docs/architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md` §6 and §7
  on `origin/main` (97cc969).
- Served sprintctl was queried the way the silent-drop check did it:
  `sprintctl item list --project . --json` (909 items) and
  `sprintctl item show --id N --json`, run from the agentops repo with
  `SPRINTCTL_BACKEND=served` and the workstation `vuoro-shared` profile.
- Two items were **created** in sprint 559 (maintenance-lane) through the same
  served tooling, using `sprintctl item add`. These were the only writes.
- Code and plans were read on each repository's fetched `origin/main`:
  agentops 97cc969, vuoro-cloud a1ce9e9, cred-broker e3696ec, and gitops-nixos
  and sovite at their 2026-11-07 tips.
- Live state came from the agentops-estate MCP `estate_status` (13:51Z),
  `kubectl get` with the appservice kubeconfig the estate report already uses,
  the user-unit journal on the workstation, and a GET on the Forgejo
  actions API.

## 1. PR #255 decisions: carried, partially carried or dropped

| Decision | Verdict | Evidence | Tracker |
|---|---|---|---|
| **Q1** Local harnesses move to vuoro.cloud as primary endpoint after the Authorization fix and E2. Transitional PAT, then a local identity/token flow. No dual-write. | **partially carried**: tracked but not scheduled. Both preconditions are met. The move has not started. | The Authorization fix is vuoro 553d807 "fix(vuoro-client): authenticate handshake and catalog" (#125). E2 is agentops#2466, done 2026-09-27. This workstation still runs `SPRINTCTL_BACKEND=served` with profile `environment-record/profiles/workstation-vuoro-shared.json`. No Oct-Nov plan or programme names #2536; it appears only in Sept handoffs and `docs/decisions/INDEX.md`. | agentops#2536 **pending**, unchanged since 2026-09-27 |
| Q1(b) cutover (§7: one named cutover, record family → store mapping checked before and after) | **partially carried**: listed in §7 only | No item names the cutover. #2536's description does not mention the mapping check. | none (fold into #2536 when it is scheduled) |
| **Q2** Admin identity, modified (c): separate Authentik operator identity, step-up for freeze | **carried, mostly open** | Design: `docs/plans/2026-09-27-admin-identity-and-vuoro-cli-design.md`. Of the "vuoro-cloud admin" items, 3 are done and 5 are pending: 2583 (2.3 retire pipeline), 2584 (2.4), 2585 (R), 2586 (O.1 public operator OIDC) and 2587 (O.2 freeze step-up). | agentops#2583-#2587 |
| **Q3** vuoro-shared is a protected substrate plus emergency coordination island. Outage-epoch state machine. | **carried, not started** | §3.3. The item is referenced in `docs/architecture/2026-10-18-estate-first-consumer-contracts.json`. | agentops#2537 **pending** (2026-09-27) |
| **Q4 (a)** `credctl accept` binds the canonical intent digest, from the workstation only | **carried (source)** | cred-broker `docs/intent-acceptance.md` (contract for #2535), `src/cred_broker/intent_acceptance.py`, CLI `accept` in `src/cred_broker/cli.py`, and the synthetic tests named in `docs/protected-intent-cli.md`. That doc states the tests "do not prove deployed reachability or real hardware signing". Effect-intent lifecycle with digest-bound acceptance: agentops#2541, done. | agentops#2535 **active** (2026-10-18) |
| **Q4 (c)** Auto-accept for boring classes, `forge_comment_pr` first canary, after the audit prerequisite | **partially carried**: one sentence in #2535 | #2535's description carries the step and the canary. `docs/protected-intent-cli.md` says "No command here ... enables auto-accept". No code anywhere implements an auto-accept policy. `forge_comment_pr` appears only in plans: `2026-09-26-trusted-service-boundary-design.md` §7 and `2026-09-26-cloud-enablement-plan.md` slice 1. | none separate. Draft below, to be split off when #2535 closes (per silent-drop check) |
| **Q5** WireGuard packet-level closure (AllowedIPs `10.44.0.1/32`; drop VPS-originated connections) | **carried; tracker stale** | gitops-nixos `modules/system/networking.nix:32-41` inserts `-i vuoro-cloud-wg -m conntrack --ctstate NEW -j DROP` on the workstation. The appservice-peer half (F-3 amendment) was not checked. | agentops#2532 still **pending** (2026-09-27). Reconcile: close it, or narrow it to the appservice peer. |
| **Q6** Repair hook → auditctl capture; "last successful authoritative event age" as a hard health metric | **carried; producer live; capture failures open** | Producer: `scripts/audit_freshness.py` emits `agentops_audit_last_authoritative_event_age_seconds{repo=...}`. Schedule: gitops-nixos `modules/home/bayleaf/audit-shards.nix` (`audit-freshness`, every 6 h, desktop notification per incident; runbook `docs/runbooks/audit-persistence.md`). Last run observed 2026-11-07 12:24Z (journal) emitted 24 gauges. It reported **capture failure** for two active repos: `gitops-nixos` (last durable event 238036 s ago, commit 85292 s ago) and `sprintctl` (last event 2060422 s ≈ 23.8 days ago, commit 55221 s ago). The metric feeds a desktop notification. No Prometheus alert rule was found. | agentops#2533 **done** (producer). The live failures belong to agentops#2547 **pending** ("repair capture in active repos"), not a new item. |
| **Q7** Doc drift, one cleanup PR per owning repo | **carried, not started as such** | Landscape recommendation 10 restates it. | agentops#2534 **pending** (2026-09-27) |
| Docs and knowledge library owner (EE-07 successor for the knowledge-base prose store; not a #255 decision) | **dropped → now tracked** | `docs/decisions/INDEX.md` lists knowledge-base as "held/dormant; successor store undecided". No open item matched "knowledge library", "docs library" or "knowledge base". | **created agentops#2875** (pending, track target-state-path) |
| blocker12-canary retirement path (vuoro-cloud; not a #255 decision) | **dropped → now tracked** | vuoro-cloud `IMPLEMENTATION-STATUS.md` (blocker 12, 2026-08-29 trial) records workspace `blocker12-canary` `01M14W25EYKCEX0BTYK1WHJAAK`. Live rollout status (estate report 13:51Z) shows it READY in maintenance mode since 2026-09-11. #2584 names only the owner reclassify. The retire pipeline is #2583, pending. The desired `vuoro-retire-worker` image is the all-zero placeholder digest. | **created agentops#2876** (pending, track vuoro-cloud-admin; depends on #2583, #2584) |

Summary: of the seven #255 decisions, none is dropped. Q2, Q3, Q4(a), Q5 and
Q6 are carried. Q1 and Q4(c) are only partially carried: Q1 is tracked but no
programme schedules it, and Q4(c) is a sentence inside an active item. The
two non-#255 candidates were not tracked at all, and they now are.

### Draft item text, not created: Q4(c) auto-accept canary

Per the silent-drop check, this is split out of #2535 when #2535 closes. It is
not created now, so the same scope is not tracked twice.

> **Trusted-side auto-accept for `forge_comment_pr` (Q4 c, first canary).**
> After digest-bound `credctl accept` (#2535) and the tamper-evident audit
> prerequisite (#255 Q4, "#10"), add a trusted-side policy that auto-accepts
> intents of type `forge_comment_pr`. The policy must hold the constraints in
> `docs/plans/2026-09-26-trusted-service-boundary-design.md` §7:
> - the repository is allowlisted and in `assertion.repo_ids`;
> - the PR is open;
> - the body is at most 8 KiB, with no foreign `@`-mentions and no
>   off-allowlist URLs;
> - a per-repo rate limit applies.
>
> The policy approves the same canonical digest a human `credctl accept`
> would, and it writes the same acceptance record with the policy id as the
> acceptor. There is no devbox step-up.
>
> Acceptance:
> - a synthetic suite proves that refusal paths stay human-gated;
> - one live canary comment on an allowlisted repo, with its acceptance
>   receipt;
> - a kill switch that reverts to human-only acceptance.
>
> Owner: cred-broker.

### Follow-ups for existing items (no new item needed)

- #2532: the workstation half is on gitops-nixos main. Close the item, or narrow
  it to the appservice peer.
- #2547: add the 2026-11-07 capture failures (`gitops-nixos`, `sprintctl`) as
  evidence.
- [silent-drop-check.md](../../plans/silent-drop-check.md): point its
  knowledge-library row at #2875 and its blocker12 row at #2876. The plan's
  owner makes that edit; this change does not touch the file.

## 2. vuoro-cloud `v0.1.0-poc.81`: promoted and published, deployment not observed

| Fact | Value | Source |
|---|---|---|
| Tag | `v0.1.0-poc.81`: tag object `67c5709`, commit `0733b42` "Release v0.1.0-poc.81 promotion candidate" (2026-10-29 16:49:31Z), `OCI-Digest: sha256:e2c6b8d2…0505`, generation 81 | `git cat-file -p 67c5709` |
| Signatures | tag **and** commit GOODSIG/VALIDSIG `AB73C1C5617B5098038CDA953AF95EDEB8243BE7` (trusted promoter) | `git verify-tag --raw` / `git verify-commit --raw` against `config/trusted-promoters.openpgp.asc`, imported into a throwaway GNUPGHOME |
| Promotion run | Forgejo `promote-deployment` run 4522 for `v0.1.0-poc.81`: **success**, 2026-10-29T17:34:14Z (poc.80 was run 4486, 13:13Z) | `GET /api/v1/repos/bayleaf/vuoro-cloud/actions/tasks` |
| Published to the Flux source | GitHub `refs/tags/v0.1.0-poc.81` = `67c5709`; GitHub `main` = `0733b42`; no poc.82 | `gh api …/git/ref/tags/…`; estate `desired.deploying_repo_main_sha`, `predicted_release_tag` |
| Flux selection rule | `GitRepository vuoro-cloud`, `ref.semver: ">=0.1.0-0 <0.2.0-0"`, `verify.mode: TagAndHEAD`, interval 1m | `clusters/bootstrap/poc/resources.yaml` at 0733b42 |
| Desired images | control, control-admin, gateway and tenant-controller pinned to `sha256:e2c6b8d2…0505` | estate `desired.deployments` |
| Running images, Flux status | **unknown**: the operator tunnel `vuoro-cloud-wg` is down | estate `running.*` reasons |
| Live API | the rollout/status API is reachable. Fleet generation 3 is converged. Four tenants are in maintenance (since 09-11 to 10-09). `runtime_image` is null. The API does not reveal the control-plane image. | estate `usable.fleet_rollout` |
| Repo's own statement | "`v0.1.0-poc.81` exists as a signed tag … Whether it is deployed is unconfirmed". The "Verified state, 29 October" header checked poc.80 at 15:59Z, **before** the poc.81 tag (16:49Z) and its promotion (17:34Z). | `IMPLEMENTATION-STATUS.md:16-55` |

**Verdict:** poc.81 was promoted correctly and published to the source Flux
watches. Per the selection rule, Flux should have reconciled to it within
minutes of 2026-10-29T17:34Z. That makes "deployed" the strong expectation,
but it has **not been observed**. A suspended or failing GitRepository would
leave poc.80 serving, and nothing read today rules that out. The poc.80 →
poc.81 diff is CLI-only (`vuoro_cloud_cli/operator_requests.py`) plus the image
pin. No server route changed, so no unauthenticated probe can tell the two
apart. The observation is packaged for the operator as
[vuoro-cloud-live-state-read](../operator-gates/vuoro-cloud-live-state-read.v1.json).

## 3. Live cluster state

### appservice (Talos, 6 nodes): observed, healthy

Read with `kubectl get` (context `admin@main`, the kubeconfig the estate report
uses), 2026-11-07 ~13:55Z:

- Nodes: 6/6 Ready, Kubernetes v1.37.2, Talos v1.14.5.
- Flux: 99 Kustomizations, all Ready, none suspended. 57 HelmReleases, all
  Ready.
- vuoro-shared: estate gate `none` ("desired == running and usable"); service
  `sha256:b4efdf41…`; recovery class `image-revert`. Leftover failed Jobs from
  the 2026-10-31 v31 attempt are still present: `vuoro-work-{preflight,migrate,grants,postcheck}-v31-oct31-a`.
- Failed pgdump Job pods: `cnpg-pgdump-age` pods in Error in analytics,
  authentik, nextcloud and cred-broker (Init:Error), and a failed
  `flux-orphan-scan` pod. Not investigated here; candidates for #2823 and the
  backup-observability owner.
- infra host: maintenance health `healthy` (talos-etcd-backup succeeded
  2026-11-07 02:12Z).

### Sovite: observed live on appservice (supersedes the 2026-10-19 last observation)

- Namespace `sovite`, Helm chart `sovite-0.1.23`. Running:
  - `sovite-control` 1/1;
  - `sovite-worker` 2/2;
  - `sovite-native-harness` 1/1;
  - `sovite-ollama` 1/1;
  - postgres and garage StatefulSets 1/1.
- `sovite-remote-worker` is scaled 0/0. The control image is
  `sovite-platform@sha256:27ee7ac9…cd54`.
- `sovite-control` has restarted 4 times. The last termination was
  **OOMKilled** at 2026-11-01T07:18:57Z, and it has run since 07:19:44Z.
- Four namespaces left over from 2026-10-31 are still present:
  - `sovite-inspect-20261031`: empty;
  - `sovite-pre23-restore-20261031`: postgres 1/2 NotReady;
  - `sovite-probe-target-20261031`;
  - `sovite-upgrade-20261031`: postgres 1/2 NotReady.

  They are cleanup candidates for the Sovite owner (programme 05).

### vuoro-cloud (single-node k3s, Hetzner): not observable read-only

The estate report has every `running.*` and `held.*` fact unknown because the
operator tunnel is down. No read-only route exists that does not activate the
operator tunnel and use the PoC admin kubeconfig, so the observation is the
operator package
[vuoro-cloud-live-state-read](../operator-gates/vuoro-cloud-live-state-read.v1.json),
status `ready`. In short, from `/projects/dev/agentops`:

```sh
nmcli connection up vuoro-cloud-operator && ip -br addr show vuoro-cloud-wg
KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml kubectl -n flux-system get gitrepository vuoro-cloud -o jsonpath='{.spec.suspend} {.status.artifact.revision}{"\n"}'
KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml kubectl -n vuoro-system get deployments -o jsonpath='{range .items[*]}{.metadata.name} {.spec.template.spec.containers[0].image}{"\n"}{end}'
nmcli connection down vuoro-cloud-operator
```

Expected: revision `v0.1.0-poc.81@sha1:0733b420…` and images
`sha256:e2c6b8d2…0505`. The package has the full steps, the send-back list and
the rollback.

## Not verified here

- Whether the audit-freshness desktop notification actually fired for the
  gitops-nixos and sprintctl incidents.
- The appservice-peer half of Q5.
- The cause of the pgdump Job errors.
- Whether the Sovite OOM recurs.
- The vuoro-cloud running generation (operator package above).
- No secret, `.env`, `.state` or SOPS file was read. Cluster access was
  `get` only.
