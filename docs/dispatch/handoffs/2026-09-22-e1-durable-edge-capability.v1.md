# Handoff 2026-09-22-e1-durable-edge-capability.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Rebuild E1 as a durable, OAuth-authenticated MCP capability on the existing vuoro.cloud public gateway, reading a workspace-scoped public-work view, replacing the static-bearer month-long trial design that was abandoned on 2026-09-22.

**Next action.** Land the one thing that is durable, urgent and independent of every open question: cd /projects/dev/_wt/e1-cloud && git log -1 92afde2 to read it, then open a PR for commit 92afde2 ALONE (not 490d7be) against vuoro-cloud main. It fixes a live pre-existing supply-chain gap: OWNED_IMAGE_PATTERNS in scripts/validate-deployment-distribution.py keyed 'migration' and 'tenant-controller' when the real container names are 'migrate' and 'controller', and 'web' was absent entirely, so the 'all promoted workloads pin one identical digest' invariant has been running over 2 of 4 manifests while the validator exited 0. Verify first with: cd /projects/dev/_wt/e1-cloud && uv run --extra test pytest tests/ -q (expect 124 passed, 49 skipped) and confirm the pin check fails on a wrong digest before trusting it.

## Predecessor

- harness: claude-code
- session: ec99fb25-17c7-45f0-98a1-3252aa6163a2
- model: claude-opus-5[1m]
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-22-e1-durable-edge-capability.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- DESIGN FOR USE, NOT DISPOSAL. Operator directive 2026-09-22: 'Building in deprecation at this point is excessively wasteful. Plans should always aim for assumption of use.' Do not reintroduce trial counters, a phase clock, a deletion-shaped deployment, or reversibility as the dominant architecture goal. Ordinary GitOps rollback is sufficient reversibility.
- MCP is a standard route on the EXISTING public gateway (src/vuoro_cloud/gateway.py). Not a separate namespace, not a separate tunnel, not a separate stack.
- OAuth 2.1 with short-lived, audience-bound, workspace-scoped tokens. Static bearer is superseded and must not be reinstated.
- The permanent absence of an effect-apply scope is binding and must be preserved. Its absence is a design decision recorded so a later session does not helpfully add one.
- Every tool on the published surface must classify as read, coordinate, record or propose. A tool that fits none of those belongs on the private side of the boundary.
- vuoro.cloud is the authority for active coordination work. Do not dual-write the same items into both estates.
- The homelab (appservice) is NOT the place to expose this. It co-hosts a forge, a password manager and an identity provider, and is LAN-only by design.
- Do not vendor vuoro's MCP code into vuoro-cloud. 13-REPO-OWNERSHIP-AND-CHANGE-MATRIX.md puts sprintctl work semantics on that repo's does-not-own list; hosting vuoro's own image unchanged is in bounds, copying the module is not.
- Deploying anything to vuoro.cloud needs two hardware YubiKey touches via scripts/promote-release.sh. There is no software fallback. The operator has offered the touch when the work is ready.
- Nothing is pushed. No PRs opened for any E1 branch. No connector registered. Nothing deployed.
- Every guard must be forced into its failure case before it is trusted. Every test must be proved falsifiable by breaking the code it covers, capturing the failure, and reverting.

## Decisions

- **Serve from vuoro.cloud (Estate B), not the homelab** — Blast radius dominates data locality for endpoint placement. The homelab co-hosts a password manager and a git forge; vuoro.cloud is already public, single-purpose and default-deny. Recorded as sprintctl event 3584.
- **vuoro.cloud is authoritative for active coordination work; a bounded slice of real NEW work lives there, no dual-writing** — Its architecture already assumes the cloud holds coordination state with operator-owned workers polling outbound. Homelab-as-authority was the current arrangement, not the designed end state. Full history import is deferred because the estate has a tested tenant SCHEMA migration but no demonstrated record import.
- **OAuth 2.1 replaces the static bearer** — Operator direction 2026-09-22, superseding DECISION 2 (agentops#2470). A unique static token has no expiry, no revocation semantics, no client identity and is replayable against the surface if stolen. The claude.ai connector dialog supports all three OAuth client paths (published identity / dynamic registration / own client), so the client side is solved.
- **The strict emission boundary becomes a versioned public-work view** — Field selection is the only disclosure control the substrate actually owns. As a view it is a lasting boundary that keeps paying off when coordinate/record/propose arrive, rather than an E1-specific filter.
- **Demand is an authenticated invocation, not a success** — Counting only outcome=='ok' converts a backend outage into silence. Retained as reasoning even though the trial counters themselves are discarded.
- **Committed superseded work rather than discarding it** — ~2400 lines of tested work sat uncommitted in worktrees and would have vanished with a prune. Commit messages state explicitly what is KEEP and what is DISCARD ON REWORK.

## Rejected

- **Serving E1 from the homelab with a vuoro.cloud hostname pointed at it** — Recommended by a design adviser on data-locality grounds and rejected by the operator. A third public path into a cluster whose neighbours are a password manager and a forge, to expose a substrate a separate public estate exists to expose, is backwards. Do not re-derive this.
- **A private vendor MCP tunnel (OpenAI Secure MCP Tunnel / Anthropic MCP tunnels) instead of a public route** — Proposed as the most secure option and then withdrawn by its own author as overfitting the one-month falsifier and optimising for disposal. Anthropic's is a research preview. Do not revive it as the primary design.
- **The one-month stop condition as an architecture driver** — Demoted by operator direction to at most a post-launch prioritisation review. It must not shape the deployment, the telemetry or the auth design again.
- **Attribution by network origin (OperatorNetworks, classify_caller, DHCP-resolving hostname lookup)** — Unsound behind a tunnel: source IP identifies a proxy and forwarded headers need explicit trusted-proxy configuration. An audit also proved S14 — with a single bearer labelled 'hosted', the operator's own probes satisfied the stop condition, the exact failure the design existed to prevent. Delete it; do not repair it.
- **Imperative-stripping, delimiting/fencing, HTML/JSON escaping, and secret-keyword denylists as prompt-injection defences** — Measured against the real corpus: 31 imperative constructions appear across 26 LEGITIMATE items, so a filter mangles real content while an attacker rephrases declaratively; fences require the consuming model's system prompt to honour them, which the substrate neither controls nor verifies; the consumer is a language model, not a renderer; and the sensitive strings are ordinary hostnames and bucket names matching no secret-shaped pattern.
- **Emitting tier, prior_attempts/prior_attempt_count, or parsing acceptance/objective out of internal description bodies** — sprintctl has no structured columns for these — they are prose sections inside description, which the disclosure audit found carries internal hostnames, eight absolute paths, six runnable command lines and an unremediated security finding stated as an exploit. prior_attempt_count additionally has no source event type, so it is structurally 0.
- **isolation: 'worktree' for implementation subagents** — The worktree-isolation guard in this environment refuses EVERY git invocation inside an agent worktree, so agents cannot commit and fall back to patches and bundles. Create worktrees from the main session and forbid agents from running git at all.
- **Mounting the surface into vuoro_service.app.create_app** — Its own docstring forbids it: different auth, different wire protocol, different exposure story. Nothing in app.py or composition.py may reference mcp_surface or mcp_journal.

## Repo state

Digest definition: v3 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/vuoro` | e1-call-journal | `100082231f82` | no | 1 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud` | docs/record-generation-33 | `f6d2c4217db7` | yes | 0 | `ce4c25acb364a209…` |
| `/projects/dev/agentops` | main | `23b8c9b110b7` | yes | 0 | `bbbbdaa57fb80bd6…` |
| `/projects/dev/appservice` | main | `a318f6ee074b` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing running. devbox lane-loop.timer confirmed inactive and disabled (it self-disabled 2026-09-21 as designed).
- Three git worktrees exist and hold committed work: /projects/dev/_wt/e1-surface (branch e1-surface-wiring, 3ac68b5), /projects/dev/_wt/e1-edge (branch e1-mcp-edge, 28155c0), /projects/dev/_wt/e1-cloud (branch e1-cloud-manifests, 490d7be and 92afde2). None pushed. Safe to remove the worktrees; the branches hold the work.
- UNVERSIONED EDIT ON DISK: /projects/dev/.claude/hooks/log-session-cost.sh was fixed this session and that directory is NOT a git repository. The fix exists only on disk; a backup is at /tmp/claude-1000/-projects-dev/ec99fb25-17c7-45f0-98a1-3252aa6163a2/scratchpad/log-session-cost.sh.bak which is session-scoped and will be cleaned.

## Unresolved

- agentops#2465's acceptance is no longer the work: three of its four acceptance lines are superseded (deletion-completeness, the one-month tripwire, and static bearer via #2470). Decide whether to supersede it with a new item scoped to the durable capability, or revise it in place. Do not silently drift.
- OAuth 2.1 on the vuoro.cloud gateway is a genuine build with no existing foundation. Today the estate has browser-session OAuth (audience vuoro-control), GitHub sign-in and vuo_pat_ workspace tokens, but NO MCP authorization server and no protected-resource metadata endpoint. Scope this before anything else.
- The vuoro-mcp-edge operation names and result schemas are INFERRED. No live GET /api/catalog/v1 has confirmed them. They are isolated in named constants in work_source.py for a one-line correction.
- The public-work view does not exist. Under the durable design the runtime should read a versioned, workspace-scoped view containing only approved fields, rather than the work API directly.
- Which cloud workspace and repo_id the pilot slice lives in, and how duplicate IDs across home and cloud are prevented, are undecided and cannot be inferred from the repos.
- Whether the auditctl session metadata should carry the full gates array at all. The hook fix removes the crash but ships a 169 KB payload per session row that only grows; bounding or aggregating it is the real fix and is the operator's call.
- vuoro-cloud's own acceptance gates remain open — restore drill, tenant isolation, external onboarding, home-unavailable Forgejo recovery, synthetic canary. The surface is being added to an estate that is publicly exposed ahead of its own release criteria.

## Evidence

- artifact: `/projects/dev/_artifacts/vuoro/e1-design-and-security-note-2026-09-22.md`
- artifact: `/projects/dev/_artifacts/vuoro/e1-placement-decision-brief-2026-09-22.md`
- artifact: `/tmp/claude-1000/-projects-dev/ec99fb25-17c7-45f0-98a1-3252aa6163a2/scratchpad/synthesis.md`
- sprintctl: `agentops#2465 events 3576 3583 3584 (placement decision)`
- sprintctl: `agentops#2491 events 3579 3580 3581 (D11 read:issue, closed)`
- sprintctl: `agentops#2513 (D11 cron throttling, filed, untouched)`
- artifact: `vuoro docs/plans/2026-09-20-vuoro-at-the-edge.md`
- artifact: `agentops docs/plans/2026-09-17-target-state.md TS-1 TS-3 TS-16`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: (unacknowledged)
- acknowledged: —
