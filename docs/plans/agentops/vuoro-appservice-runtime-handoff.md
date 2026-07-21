---
doc_id: vuoro-appservice-runtime-handoff
status: ratified
ratified_at: 2026-07-21
ratified_by: operator
---

# Vuoro appservice runtime handoff

## Ownership

Appservice owns the concrete `vuoro-dev` and production deployments. The
public Vuoro repository owns the service image, Compose stack, neutral
Kustomize base, migration commands, and application-level health contracts.
This handoff authorizes backlog and planning work; it does not claim that
appservice manifests or runtime state already exist.

## Development target

Create a persistent isolated development environment with:

- its own namespace and low-resource PostgreSQL/CNPG authority;
- four domain schemas with distinct migration and runtime roles;
- development-only identities, endpoint, secrets, and network policy;
- no production secrets, database reach, artifact mounts, or identities;
- explicit seed/reset jobs guarded by `environment_class=development`;
- retained functional state and a documented operator reset path.

The service configuration accepts one DSN per domain even if development uses
one cluster. Migration jobs run before the service and publish per-domain
schema evidence. Runtime roles have no DDL privileges.

## Production target

The production overlay supplies private database endpoints, identity secrets,
networking, backup/restore integration, resource sizing, and observability.
Promotion uses the exact digest verified in development. No production seed or
reset job is rendered.

## Release gate

1. Render the public Kustomize base with the development overlay.
2. Run per-domain migrations and compatibility checks.
3. Deploy the release-candidate digest.
4. Run black-box catalog, work, execution, knowledge, and audit tests.
5. Record digest, catalog revision, schema versions, and results.
6. Apply production migrations with backups and rollback ready.
7. Promote the same digest and run read-only/non-destructive smoke checks.

Rollback reverts the service digest; schema rollback uses the domain's
documented restore/forward-fix procedure rather than running an older client
against a newer schema.

## Required appservice backlog outcomes

- isolated `vuoro-dev` authority and overlay;
- production overlay and secret/role split;
- migration Job ordering and failure visibility;
- same-digest promotion evidence;
- backup, restore, rollback, and smoke runbooks;
- protection proving development identities cannot reach production.

The appservice repository was unavailable in the authoring workspace. Before
registration there, re-read its live backlog and current GitOps topology and
link the resulting owner-local records back to this handoff.

Agentops coordination item **#1189** holds this handoff and the deployment done
conditions until that owner-local inspection is possible. Do not implement
GitOps from #1189 or create a duplicate appservice item without linking the two.
