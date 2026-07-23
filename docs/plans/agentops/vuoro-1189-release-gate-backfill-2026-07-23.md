---
doc_id: vuoro-1189-release-gate-backfill-2026-07-23
status: draft
authored_at: 2026-07-23T17:43:49Z
authored_by: claude:1189-backfill-worker
supersedes: none
relates_to: vuoro-appservice-runtime-handoff (ratified 2026-07-21; NOT amended by this doc)
---

# #1189 backfill: syncing vuoro-dev to vuoro-shared's digest, retroactive release-gate evidence

## Why this document exists, and what it does not do

The ratified handoff (`vuoro-appservice-runtime-handoff.md`) requires the
production overlay to promote "the exact digest verified in development"
(Release gate step 7). A reconciliation pass on 2026-07-23 found this
violated: `vuoro-shared` (production) was running a different image digest
than `vuoro-dev`, introduced 28 minutes after a compliant same-digest
promotion, with no release-gate evidence recorded for that second bump.

This document backfills `vuoro-dev` to match `vuoro-shared`'s digest and
walks through the release gate retroactively, stating plainly which steps
are now evidenced and which cannot be, rather than fabricating steps that
did not happen in the actual order they happened in. It does **not** amend
the ratified handoff — that requires human ratification, not an agent edit.

## What changed

`clusters/main/kubernetes/apps/vuoro-dev/app/deployment.yaml` image bumped:

- from `sha256:fe0ab4445a6a4b4ecc771376737e59811a0aaef91b1e52fc80af3cc08046607c`
- to `sha256:e5a767c85dbd04146e594db5daf9d33f72264f777f6853ebd2c59642826508ab`

(unpushed at authoring time — see "What this document does not authorize" below)

## Why the new digest is safe to run in development

vuoro commit `82c372b` ("feat(service): allow production composition",
2026-07-22T21:28:14+03:00) is the source change baked into the new digest.
Inspected directly: it generalizes `create_composed_app`'s environment-class
check from `_DEPLOYABLE_ENVIRONMENT_CLASSES = {"development"}` (hard
`CompositionError` otherwise) to `{"development", "production"}`. The
`environment_class` value is now passed through instead of hardcoded to
`"development"`. For any deployment running with
`VUORO_ENVIRONMENT_CLASS=development` (which is how `vuoro-dev`'s
ConfigMap is configured), the code path is behaviorally identical to the
prior digest — this is a strict superset change (adds a new accepted
class; does not alter the development path). This is why backfilling
`vuoro-dev` is the correct remediation rather than rolling `vuoro-shared`
back: the new digest is not development-incompatible, it was simply never
promoted there.

## Release gate — retroactive walk-through

1. **Render the public Kustomize base with the development overlay.** —
   Already done prior to this document (appservice commit `a675e397`,
   2026-07-22T19:16:50+03:00, "add development service and schema gates").
   Evidenced by the existing manifest tree.
2. **Run per-domain migrations and compatibility checks.** — Migration
   Job manifests exist (`vuoro-dev-db/app/vuoro-migrate-v1.yaml` and
   per-domain migration secrets for work/execution/knowledge/audit).
   **Not independently re-verified here**: this session's `kubectl`
   context (`kind-bindery`) is a local kind cluster, not the real
   appservice cluster — there is no live-cluster access from this
   session to confirm the migration Jobs actually completed successfully
   against real data. This step's evidence is the committed manifest
   only, not an observed Job success. Flagged as a gap, not asserted as
   satisfied.
3. **Deploy the release-candidate digest.** — As of this document,
   `vuoro-dev`'s manifest now declares the same digest as `vuoro-shared`.
   Whether the live cluster has actually reconciled this manifest is
   **unknown from this session** (same access limitation as step 2, and
   this change is not yet pushed — see below).
4. **Run black-box catalog, work, execution, knowledge, and audit
   tests.** — vuoro's own test suite (74/74, per the #1190 worker's
   independent run this session) exercises the composition/service code
   at the unit/integration level, including the specific
   `create_composed_app` change this digest contains. **This is not the
   same as a black-box test against the deployed `vuoro-dev` service** —
   no such black-box run was performed here, for the same access-limitation
   reason as steps 2–3.
5. **Record digest, catalog revision, schema versions, and results.** —
   This document records the digest (above). Catalog revision and schema
   versions were not independently re-derived in this pass; out of scope
   for a digest-sync backfill.
6. **Apply production migrations with backups and rollback ready.** —
   N/A retroactively: production (`vuoro-shared`) was already migrated
   and running this digest since commit `3904377b`
   (2026-07-22T21:31:15+03:00); this document does not touch production.
7. **Promote the same digest and run read-only/non-destructive smoke
   checks.** — The digest is now the same in both manifests (this
   document's change). **No smoke check was run against a live service
   by this session** — same access limitation. Stated plainly: this step
   happened out of the documented order in the real timeline (production
   got the new digest first, unaccompanied by recorded gate evidence;
   this document is completing the paperwork after the fact, not before
   the change as the gate implies). That inversion is the actual finding,
   not something this document can retroactively fix.

## Honest summary: what's evidenced vs. what remains a gap

**Evidenced:** the digest divergence's root cause (a genuine, tested,
backward-compatible feature commit); that the new digest does not break
the development code path; the manifests now declare matching digests.

**Not evidenced, and not fabricated here:** live-cluster confirmation that
either `vuoro-dev` or `vuoro-shared` is actually running the declared
digest, that migrations completed, or that a black-box/smoke check passed
against the running service. This session had no route to the real
cluster to check. Whoever has real cluster access should independently
confirm reconciliation before treating this gate as closed.

## What this document does not authorize

This document's manifest change is **committed locally, not pushed**.
Appservice's Flux controller reconciles directly from `origin/main`, so
pushing this change is a real deployment action against the `vuoro-dev`
namespace, not a documentation-only step. That decision is left to the
orchestrating session / operator, not taken here.
