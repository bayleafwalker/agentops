# Output 5 — Cockpit Disposition

Workstream 7. Source: `agentops/apps/web` (`components/cockpit/cockpit-shell.js`),
deployed image 0.1.15 in namespace `vscode`. Frequency-of-use telemetry does
not exist; usage is inferred from configuration defaults (pollAll **off** —
panes load once), write-path wiring, and the operating record.

The plan predicted "cockpit should become a thinner state projection rather
than a central operating interface." The evidence shows **it already largely
is one**: 16 surfaces, of which 11 are read-only projections; of the 5 write
surfaces, 2 ship disabled and 1 is a pause file. The disposition below mostly
confirms and tightens that shape.

| Surface | Data source | Classification | Disposition |
|---|---|---|---|
| Repos strip + sprint list/toggle | pg://sprintctl | Useful convenience | **Retain** |
| Sprint **Activate** button | sprintctl domain-owned handler | Operationally necessary (the one direct write; CLI-parity enforced) | **Retain** |
| Overview counts | derived | Useful convenience | **Retain** (free) |
| Claims table (actionq sessions ⋈ sprintctl items) | actionq + pg | Operationally necessary during multi-agent batches; combines sources no single CLI joins | **Retain** |
| Work items + "↓ dispatch" prefill | sprint payload | Useful convenience | **Retain** |
| Dispatch composer + manifest summary | templates + actionq-server | Operationally necessary *if* queue dispatch stays cockpit-driven; contract (v1) wired and deployed | **Retain as provisional** — promote on evidence of routine dispatches from the pane vs CLI |
| Takeup pane | pg events | Replaceable projection; duplicates claim/occupancy info; active-mode-only | **Remove** (fold anything needed into claims table) — matches register row 15 demotion |
| Status bar (health, cost, pause) | mixed | Useful convenience | **Retain** |
| Model Headroom panel + force refresh | configured JSON cmds | Illustrative/convenience (soft signal by design) | **Retain** as-is; no further investment |
| Dispatches + review worktrees + cost join | actionq + derivation | Diagnostic; consequential during batch review | **Retain** |
| Reconciliation pane (accept/reject) | reconciliation artifacts | Provisional — review queue is plausible; **executor ships disabled** in prod | **Retain read-only**; decide executor's fate only after the planned disposable authority smoke target exists; until then the executor code is speculative carry |
| Knowledge pane | kctl knowledge-artifact/v1 | Replaceable projection, cheap and contract-clean | **Retain** |
| Outcomes & Review (audit NDJSON) | `_artifacts/*/audit` | Weak: upstream stream is 101 events, 87 mirroring kctl; pane cannot currently inform decisions the knowledge pane doesn't | **Remove or park** until audit has an independent consumer story (register row 33/34) |
| Sprint event feed | pg://sprintctl | Useful convenience | **Retain** |
| TWEAKS panel | client state | Convenience | **Retain** |
| Command palette | repos+sprints | Convenience | **Retain** |
| MCP endpoint (5 tools) | JSON-RPC route | **Unused** — requires configured write token; token unset in prod → 503 | **Decide**: either wire the token and make it the agent-facing surface, or delete the route. Shipped-disabled surfaces are speculative carry |
| Public site demo (`site/index.html`) | synthetic | Out of assessment scope (marketing) | — |

## Cross-cutting findings

- **Stale/misleading data risk is managed** (freshness handling, pollAll off,
  visibility backoff), and no confusion incidents are on record. The one
  observed drift is cosmetic: `CockpitNav` lists a nonexistent `#sprints`
  anchor and omits the reconciliation/knowledge sections; screenshots predate
  the current shell. Hygiene fix, not redesign.
- **Write-surface policy is sound and should be frozen as a requirement**:
  every mutation goes through an owner contract; the only direct write is a
  server-validated transition. The reduced spec encodes this as: *the operator
  surface may never hold authority; it may only submit owner-contract
  commands.*
- **Auth gap**: `COCKPIT_WRITE_TOKEN` optional/unset means the enabled writes
  rest on network identity alone. Either enforce the token or record the
  network-identity trust decision explicitly.
- The cockpit's unique value over CLI is exactly two joins: sessions⋈items
  (claims table) and dispatches⋈costs. Every other pane is a single-source
  projection an agent or CLI reproduces trivially — which is fine while the
  panes stay thin, and is the argument against ever thickening them.
