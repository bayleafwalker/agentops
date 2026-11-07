# Branch sweep ledger (2026-09-23, session b2bee73e)

The operator's rule: every branch lands on main or is retired; checkouts and worktrees track the remote. The classifications below come from read-only sonnet audits (git cherry / merge-tree / status). Deletion tips are logged in `retired-branches.tsv` beside this file. The auto-mode classifier blocks bulk git deletions from the agent, so hand those to the operator as a frozen-list script, as `branch-cleanup*.sh` beside this file were. Build each list from LIVE refs: GitHub rejects the whole `push --delete` batch if one ref is already gone.

## DONE
- vuoro-cloud, vuoro, sprintctl, agentops, appservice: swept.
  - appservice remote keeps only main, rebuild/recovery (documented DR) and feat/langfuse-land (draft #1712).
  - 23 other repos' clean default checkouts were fast-forwarded.
- hostproto-{a2a-worker,dap-core,dap-debugpy,dap-delve,mcp-playwright,semantics}: local wt/gi-auditctl-ignore deleted.

## ALL ON-MAIN / SUPERSEDED: delete local + remote branches, remove the listed worktrees
- actionq: 12 local + 19 remote-only.
  - Superseded: daemon retired; tranche4 and action-lifecycle drafts overtaken.
  - Worktrees: _projects/*/members/actionq; /tmp wt-gen, wt-prd, wt-r3. The outctl-ready one has generated drift only: discard.
- actionq-dispatcher: 5 local + 1 remote; all on main.
  - Worktrees: _projects/*/members, two /tmp.
- outctl (frozen 2026-08-16):
  - dispatch-ready-20260808/outctl (local+remote): post-freeze wip, superseded.
  - wt/gi-auditctl-ignore: on main.
  - origin/outctl-architecture-20260810: superseded by the kill decision 3cb2c55.
  - Worktrees: _projects/*/members (the outctl-ready one has 1 untracked evidence file: discard).
- scribectl: s2/item6-agentops-paths (local+remote) and wt/bt-scribectl (local).
  - Worktrees: two /tmp.
- gitops-nixos (canonical origin = Forgejo):
  - On main: chore/devbox-repin-agentops-main, fix/llama-swap-docker-path, copilot-worktree-*T20-13-35, s2/item6-remove-hybrid-dispatch (+remote), wp8-host-telemetry, wt/bt-gitops-nixos, origin/feat/devbox-subagent-exit-hook.
  - Superseded: copilot-worktree-*T20-30-19, devbox-orphan/2026-09-16-* (+remote), feat/llm-inference-module, agent/opencode-qualification-2142.
  - Worktrees: .worktrees/copilot-worktree-* (scratch env edits only), /tmp wt-item6-pra, wt-bt-gitops-nixos.
- homelab-gitops-template: s2/item6-agentops-paths (+remote), wt/gi-auditctl-ignore; /tmp worktree.
- bindery-core:
  - On main: feat/minimal-game, s2/item6-agentops-paths (+/tmp worktree), wt/gi-auditctl-ignore, origin/feat/{cncnet-private-allocator,evidence-reconciliation,external-runtime-w0-w1}.
- bindery-ra2-adapter: origin/feat/ra2-adapter-boundary.
- frontier-weave (origin = Forgejo; github = mirror): s2/item6-agentops-paths (+/tmp worktree), wt/gi-auditctl-ignore.
- flowlab: grounding/sanitized-auditctl-shape (+remote), origin/campaign/2026-08-20-evaluation, wt/gi-auditctl-ignore.
- aligned-equity: s2/item6-agentops-paths (+/tmp worktree), origin/codex/adopt-working-process-dispatch, wt/gi-auditctl-ignore.
- acceptance-lab: origin/campaign/2026-08-20-evaluation, wt/gi-auditctl-ignore.
- sprintctl-bootstrap-template: codex/reservation-model-corrections (+remote), wt/gi-auditctl-ignore.
- cluster-alignment-mvp: dogfood/worker-fast-git-aware-manifest.
- wizard-valley-world-window: origin/render-fabric-frame-range-v1, wt/gi-auditctl-ignore.
- box, cv-studio, datacluster, datacluster-template, cluster-rebootstrap, ha-elisa-kotiakku, kotona.app, worldwindow-kernel: local wt/gi-auditctl-ignore.
- homelab-analytics: s2/item6-agentops-paths (+/tmp worktree).
- local-inference (no remote): wl-c1-rescore-2436, feat/tier-corpus-scorecard (+ _wt/local-inference-scorecard).
- appservice-recovery (a worktree of appservice on rebuild/recovery): fast-forward to origin/rebuild/recovery (2 behind).

## UNLANDED: land (rebase, PR, CI, merge), then delete the branch
- acceptance-lab feat/candidate-output-execution-provenance: 2 commits, clean.
- ha-elisa-kotiakku: two dependabot bumps (setup-python, hassfest), clean. Merge.
- homelab-analytics docs/bootstrap-admin-rotation-caveat: 1 doc commit, clean.
- browser-workbench wt/gi-auditctl-ignore: 1 commit, clean; this repo's main never merged it. Its local main also has no upstream set.
- bindery-core fix/crd-manifest-generation: 1 commit; CONFLICTS in Makefile and hack/verify-crds.sh. Rebase.
- kotona.app origin/codex/2026-08-27-cluster-lock-study-note: 4 commits; CONFLICTS (scripts/worker-smoke.mjs add/add, notes). Rebase.
- hostproto: see below.

## Uncommitted work in checkouts
- hostproto: now committed LOCALLY as 4ccb359 on branch land/wave1-mock-harness, on top of 4 never-pushed main commits. `node --test chrome/test/` FAILS. Fix it before landing. All other gates pass: fmt, clippy, cargo test, mock corpus 16/16, spec validator 166.
  - Gate commands: `tools/devshell.sh ...`; see hostproto AGENTS.md:49-60.
  - Still to land: s2/item6-agentops-paths, 1 commit. Only its AGENTS.md hunk differs from HEAD.
  - .auditctl/auditctl.db and the _artifacts audit shard are tracked tool state; leave them out.
- browser-workbench: 363 modified files, all evidence/release-0.2.0 regenerated on 2026-09-01. Discard with `git restore evidence/`.
- local-inference (master, no remote): commit the 3 hand-written docs (HANDOFF.md, docs/06, docs/08 "Finding 21"). `git rm --cached` the tracked .pyc and ignore `__pycache__/`. Decide whether it gets a Forgejo remote: the rule says checkouts match a remote.
- worldwindow-kernel: in-progress doc edits (README, docs/MIGRATION_FROM_LEGACY.md, docs/RESET_CHECKLIST.md, new docs/WIZARD_VALLEY_REFERENCE.md). Main is 1 behind. Commit via PR after a read.
- counterfactual-ops: only an appended audit shard line; main is 2 behind. Fast-forward, then commit the shard.
- homelab-analytics: 2 untracked audit shards. Commit or ignore, per that repo's audit convention.

## auditctl / kctl / cred-broker / cred-broker-public (classified last)
- auditctl:
  - On main: chore/render-native-runtime-federation-20260820, chore/render-project-auditctl, chore/render-project-auditctl-3, docs/agents-test-runner, feat/harness-baseline-event-type, s2/item6-agentops-paths (+remote), s2/item6-regenerate-guidance.
  - Superseded: agent/auditctl-schema-runtime; origin/agent/state-protocol-rollout (add/add conflicts, main has its own files at those paths; skim the diff before deleting).
  - UNLANDED, clean, tested: b2-audit-evidence-ledger-falsifier and b2-audit-terminal-reason-coverage (worktrees in _wt/). Land.
  - Worktrees: the dispatch-ready member, three /tmp wt-*, and the outctl-ready member (generated drift only: discard).
- kctl:
  - On main: chore/render-project-kctl, chore/render-project-kctl-3, s2/item6-agentops-paths (+remote), s2/item6-regenerate-guidance, wt/gi-auditctl-ignore, origin/feat/claim-knowledge-categories.
  - Superseded: chore/render-native-runtime-federation-20260820.
  - UNLANDED, clean: b2-kctl-pin-authority-vocabulary (test hardening a live authority check). Land.
  - DECIDE from target state: agent/p2.2-schema-runtime-kctl (3 commits, conflicts). kctl retires in S4, so check the S4 plan: retire it unless the store needs the split until then.
  - Worktrees: the dispatch-ready member, three /tmp wt-*, and the outctl-ready member (generated drift: discard).
- cred-broker (origin = Forgejo git.apps.kotona.app):
  - The checkout is on handoff-2026-09-13, an ancestor of origin/main. Move it to main at origin/main, then delete handoff-2026-09-13.
  - Also delete ci-build-environment-assertions, d11-revert-void-pin-test, phase3-drift-check and s2/item6-agentops-paths (+remote), all on main, plus remote-only origin/d11-void-pin-test and origin/feat/signed-step-up-approval.
  - Worktree: /tmp wt-prd-cred-broker.
- cred-broker-public (GitHub; a curated public sibling, not a mirror): origin/cred-broker-repo-write-canary-* is a one-off drill, superseded. Delete it.
