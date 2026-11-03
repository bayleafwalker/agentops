# Routing estate snapshot — 2026-11-03

This is a point-in-time observation, not a provider entitlement or billing
record. [The routing policy](../../model-routing.json) provides aliases and
guidance; it is not a central model-selection service. Native harnesses choose
their own configured or explicitly requested models. The
[routing guide](../dispatch/model-routing.md) describes the alias and audit
boundaries.

| Runtime | Observed configuration or execution | Boundary |
| --- | --- | --- |
| Workstation Codex CLI 0.166.0 | User config selects `gpt-6.1-terra`; workspace and agentops configs had no model override. The bundled catalogue lists that ID. | Config and bundled catalogue do not attest a provider-side serving identity or entitlement. |
| Devbox agent Codex CLI 0.166.0 | User config selects `gpt-5.6-sol`; workspace and agentops configs had no model override. The bundled catalogue lists both that ID and `gpt-6.1-terra`. | A separate [resume observation](../dispatch/model-routing.md) found the default selected on ordinary resume and Luna selected when explicitly requested. |
| Workstation Claude Code | A no-tools Sonnet marker succeeded after interactive Claude.ai reauthentication. | Authentication and a successful response do not establish a quota balance or invoice allocation. |
| OpenCode Go | Kimi responded on workstation and devbox; devbox also responded to an explicit Luna request. The operator reported stored Go and Console credentials. | Provider-side subscription allocation, quota and any API billing were not verified. |
| Codex Cloud | A native cloud task reached READY and returned its marker. | The task status and viewer did not expose the serving model identity. |
| Workstation local inference | The running worker-fast configuration and a bounded clerical pilot are separately recorded in [the local pilot](2026-11-03-routing-local-clerical/README.md). | A config path and filename do not independently attest loaded weight contents. |

Policy aliases predominantly name `gpt-5.6-sol` and `gpt-5.6-terra`, whereas
the workstation's configured default and the bounded comparison requested
`gpt-6.1-terra`. That difference is an inventory finding, not evidence that
policy should automatically change. Bundled catalogue visibility is weaker
than an executed request and is not an entitlement check.

## Route telemetry

`scripts/jev_shadow.py` implements publication of `dispatch.route.decision`
events to auditctl. On this workstation, the local audit ledger contained 80
such events dated September 28–30; a query since October 1 returned none as of
this snapshot. The historical events did not include a run reference. Current
source can attach a RunManifest reference, but no current emission was observed.
These events describe workflow tiers and outcomes; they do not establish the
actual provider, model, token usage, subscription allocation or cost. The
historical ledger is host-local, not authoritative. The saved dispatch
workflows are marked legacy in agentops instructions and must not be revived to
generate telemetry.

Read-only reproduction, using the configured agentops environment:

```sh
direnv exec /projects/dev/agentops auditctl list --type dispatch.route.decision --since 2026-10-01T00:00:00Z --limit 5 --json
```

The result is a point-in-time query. The remaining work is to measure outcomes,
review effort and provider-side quota or billing where those sources are
available, and to attach actual route evidence to an active workflow without
assuming that configuration or successful authentication proves billing.
