---
render_levels: [full]
---

## Ecosystem ownership and safety boundaries

- `agentops` owns reusable dispatch templates, project bindings and render
  tooling, cross-repository guidance, and the cockpit application source.
- `sprintctl`, `kctl`, and `actionq` own their respective runtime semantics and
  state. Do not add raw cross-tool database writes or cross-tool transactions.
- The former `outctl` member is retired from active Vuoro scope. Its repository
  remains a frozen discovery artifact; new harness-evidence work belongs at the
  native runtime boundary and targets standard OpenTelemetry plus Langfuse or
  Phoenix with object storage rather than a new evidence product.
- Inspect declared `risk_surfaces` before changing queue, claim, lease, retry,
  recovery, projection, publication, reconciliation, or backend-parity paths.
  `full` is a sequence of scoped actions, not blanket mutation authority.
- Keep browser-facing cockpit writes behind documented owning APIs. Project
  scope does not authorize cluster reconciliation, image publication, or
  deployment changes.
- Reusable dispatch behavior stays canonical in agentops. Express a member's
  true difference in its own `.agents/overlays/` fragment instead of copying a
  shared skill body.

Check generated guidance with the deterministic renderer in agentops. Missing,
stale, or hand-edited output is regenerated from canonical sources; it is never
merged manually.
