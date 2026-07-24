# Beads + Restate — Source-Level Adaptation Analysis

## Scope and method

This is Stage 1 of the strategic assessment. It is a static source review of
the same pinned Beads revision used by the integrated boundary run; it does not
claim a new R2 pass or a workflow substitution result.

| Input | Locked value |
| --- | --- |
| Beads revision | `d7b9f4fc52deebc86cb25c214107e96cdd512b67` |
| Source checkout | `/tmp/vuoro-clean-room-lane1-beads-20260723` |
| Checkout state during review | clean at the pinned revision |
| Existing integration | `2026-07-23-lane-2-beads-restate-integrated` |
| Deployment reviewed | embedded local Dolt, with workers able to invoke the Beads CLI |

The review traced commands and storage/unit-of-work entry points that can alter
execution-relevant planner state: status, assignee/claim, reopening,
unclaim/reclaim, and completion. It also checked the documented hook and
proxied-server paths for a supported pre-mutation authorization extension.

## Findings

### 1. The existing adapter has a real native bypass

The integration verifier invokes:

```text
bd update cr-689 --assignee untrusted-bypass --status in_progress --json
```

after Restate recovery and accepts that mutation. This is the observed R2
failure, not merely a code-reading concern. See
[the verifier](../runs/2026-07-23-lane-2-beads-restate-integrated/adapter/verify_integration.py)
and [the boundary evidence](../runs/2026-07-23-lane-2-beads-restate-integrated/evidence/integrated-r2-boundary.md).

### 2. Beads has several direct state-mutation paths

The essential paths are not all aliases of one bridge call:

| Operation family | Representative command/source path | Direct mutation target |
| --- | --- | --- |
| Claim | `cmd/bd/update.go:391`, `cmd/bd/ready.go:206` | `ClaimIssue` / `ClaimReadyIssue` |
| Update status or assignee | `cmd/bd/update.go:422`, `cmd/bd/assign.go:69` | `UpdateIssue` |
| Complete | `cmd/bd/close.go:152` | `CloseIssueChecked` |
| Complete/update in a batch | `cmd/bd/batch.go:352`, `cmd/bd/batch.go:367` | transaction `CloseIssue` / `UpdateIssue` |
| Reopen | `cmd/bd/reopen.go:64` | `ReopenIssue` |
| Release/recover | `internal/storage/storage.go:105-113` and `internal/storage/bulk_issues.go:16-25` | unclaim, heartbeat, and reclaim methods |
| Proxied-server CLI | `cmd/bd/update_proxied_server.go`, `cmd/bd/mutate_proxied_server.go` | `IssueUseCase().UpdateIssue` |

The static inventory found `UpdateIssue` callers in 22 non-test command files,
`CloseIssue` callers in 12, and direct claim, ready-claim, reopen, unclaim,
heartbeat, and reclaim paths as well. Import/sync, graph, molecule, and
administrative commands add further state-changing surfaces. A wrapper around
one CLI transition therefore cannot establish exclusive authority.

### 3. Current hooks are observability, not authorization

`internal/hooks/hooks.go:1-3` defines hooks as running **after** events.
`Runner.Run` starts them asynchronously and explicitly ignores failures
(`internal/hooks/hooks.go:47-72`). `HookFiringStore` likewise invokes the
inner update/close first (`internal/storage/hook_decorator.go:110-166`).

Consequently, `on_update` and `on_close` can project, audit, or attempt repair,
but cannot deny a proofless write before it becomes a Beads fact. They are not a
supported interception point for R2.

### 4. Proxied-server mode centralizes storage but does not add an authorizer

Proxied-server mode routes CLI operations through a Beads unit of work, but
`baseUOW.IssueUseCase()` constructs the ordinary domain use case directly
(`internal/storage/uow/uow.go:84-101`). That use case accepts an arbitrary
`actor` string and calls its issue repository for `UpdateIssue`, `ClaimIssue`,
`CloseIssue`, and `ReopenIssue` without a receipt parameter
(`internal/storage/domain/issue.go:387-455`, `1308-1535`).

This is useful engineering structure for a fork: it is a central domain seam.
It is not a public policy plug-in or a proof-verifying extension point. In
addition, the unit of work exposes `RawSQLUseCase` (`internal/storage/uow/uow.go:18-24`),
so a meaningful served deployment must also restrict raw database credentials
and access to the data directory. The worker-sandbox `readonlyMode` check is a
client-side process posture (`cmd/bd/errors.go:133-140`), not server-resolved
authorization.

## Variant disposition

| Variant | Stage-1 disposition | Reason |
| --- | --- | --- |
| Thin adapter in the tested embedded deployment | Rejected | It gates only its own path; native CLI and storage paths remain writable. |
| Thin adapter with existing hooks | Rejected | Hooks run after a successful mutation and cannot veto it. |
| Thin adapter with proxied-server mode only | Rejected as a sole-authority design | It centralizes a path but currently exposes ungated domain mutation methods and no receipt contract. |
| Maintained Beads fork | Advance to a bounded feasibility slice | It can add a central pre-mutation receipt authorization seam, but must also prevent embedded/raw storage writes by deployment design. |
| Upstreamable generic extension | Open, low confidence | A synchronous generic mutation-authorizer could be valuable, but it is absent and Beads' charter puts orchestration policy outside core. |
| Restate-backed replacement module | Open | It can preserve sole authority, but its custom-code and reconciliation cost are unmeasured. |
| Beads projection/UI only | Open for a deployment slice | It avoids making Beads authoritative, but only if workers are structurally read-only and the adapter service is the sole Beads writer. |

## Minimum fork/projection design to test

The next vertical slice should choose one explicit shape, not a permissive
wrapper:

1. Run a served/proxied Beads deployment with workers denied both raw database
   credentials and write access to the Beads data location.
2. Introduce a synchronous, fail-closed authorization boundary before every
   execution-relevant transition: claim, transfer, status/assignee change,
   close, reopen, unclaim, and recovery. It must take a current Restate receipt
   or call a generic receipt verifier.
3. Keep creation, labels, notes, and read queries outside that protected set
   only after recording why they cannot create an execution-authority
   disagreement.
4. Ensure system-generated mutations (for example molecule auto-close) have a
   distinct server-held authorization path, not a client-supplied actor-name
   exemption.
5. Repeat the native bypass test through every listed transition family, then
   run the full R2 pack before broader workflow scenarios.

This is no longer a “small Restate adapter” as previously labelled. The fork
may still be economically attractive, but its patch surface and deployment
boundary must now be measured rather than assumed small.

## Evidence

- [Actual implementation map](beads-restate-adaptation-fork-map.yaml)
- [Strategic assessment](strategic-assessment.md)
- [Pinned candidate lock](../runs/2026-07-23-lane-2-beads-restate-integrated/candidate-lock.yaml)
- [Integrated mutation-boundary evidence](../runs/2026-07-23-lane-2-beads-restate-integrated/evidence/integrated-r2-boundary.md)
