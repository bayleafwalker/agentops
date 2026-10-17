# Estate evidence delivery: owner registers and qualification

This implements the source/design portion of the [estate evolution plan](../plans/agentops/2026-10-17-estate-evolution-plan.md).
It does not accept an estate outcome or authorize a deployment. The owner plans
remain the delivery contracts; Sprintctl remains the work-item authority.

## Architecture and authority

Appservice owns the service/release register (AS-P1), NixOS owns source-defined
host roles and current host evidence (NX-P1/P2/P6), and Datacluster owns provider
resources, operating intent and spend (DC-P1). Agentops links these deliverables.
It does not add an inventory database, writable work queue or new operator UI.

The existing [estate status report](../runbooks/estate-status.md) remains the
read-only observation tool for its supported Vuoro/Cloud/workstation/devbox
environments. It is supplemental evidence, not a complete service, host or
provider inventory. In particular, it does not cover infra or Datacluster, assign
human ownership, measure actual use, or establish coherent application recovery.
An unavailable fact stays unknown even when its configuration exists.

Each owner can refresh its evidence independently. Cross-owner references retain
the original location, source branch/commit, artifact identity, UTC observation
time and scope. Configuration declarations, runtime observations, target receipts,
independent verification and acceptance are distinct. A snapshot never grants
current effect authority or closes a live readiness gate. Published summaries
carry redacted references; credentials and raw private evidence stay with owners.

## Implemented source results

| Owner result | Implementation and boundary | Qualification still required |
|---|---|---|
| Appservice AS-P1 / EE-01 | `docs/scripts/service_truth.py`, `docs/service-truth-metadata.yaml` and `docs/service-truth-register.md`: offline source report, explicit pins/dependencies and reviewed declarations; observed revision/image/schema/health/use/backup/restore remain unknown. Initial snapshot contains 92 configured Flux units and zero runtime-observed units. Source, metadata and generator provenance are separate. | All critical operating owners/classifications, rendered resources and retirement residue, live observations, actual use and AS-P3/P4 coherent restore receipts. Source list length is not a deployed-service denominator. |
| Appservice AS-P6 / EE-05 | Existing public-exposure and backup guards inspected and exercised; evidence in `docs/evidence/2026-10-17-policy-guard-qualification.md`. Existing CI runs both without changed-path filters. No bypass was established and no redundant fixture was added. | Live disposable-canary retirement, target/orphan and alert proof, current recovery-composition and upgrade qualification. |
| NixOS NX-P1 / EE-04 | README, AGENTS and historical runbook pointers now follow source-defined encrypted workstation, isolated devbox and agent-free infra; `docs/runbooks/current-host-operations.md` preserves recovery references and names runtime unknowns. | Nix evaluation/checks and dated runtime identity/isolation/recovery evidence. No host conversion was restarted. |
| NixOS NX-P4 / EE-05 | Offline `scripts/tests/test_deploy_host_guard.py` exercises refusal before rebuild, valid workstation alias, explicit remote destination and explicit override semantics; wired to `deploy-host-guard` in existing flake checks. Helper examples/comments follow current outputs. | Actual flake evaluation, host dry-run/deployment evidence and rollback/recovery qualification. No deployment behavior or host settings were changed. |
| Datacluster DC-P1 / EE-01, EE-04 | `docs/infrastructure/dc-p1-inventory-template.md` prepares timestamped provider/Terraform metadata/DNS/Flux/billing reconciliation and operating-intent decision. Historical architecture/status/upgrade entrypoints link the current gate. | Actual resource existence, owners, costs, access and operating-intent decision. DC-P2–P6 remain gated; no infrastructure change was performed. |

These are implementation references, not fabricated Sprintctl IDs or completion
states. The cloud workspace has no Sprintctl binary/served profile or configured
operational credentials. No live items/reservations or acceptance decisions were
read or changed. Reconcile existing owner items before scheduling further work.

The source changes are published for review in draft pull requests:

- [Appservice #1917](https://github.com/bayleafwalker/appservice/pull/1917) — service
  register and policy evidence.
- [NixOS #25](https://github.com/bayleafwalker/gitops-nixos/pull/25) — current
  operations and deployment-guard fixtures.
- [Datacluster #3](https://github.com/bayleafwalker/datacluster/pull/3) — resource
  evidence intake and historical-guide pointers.
- [Agentops #365](https://github.com/bayleafwalker/agentops/pull/365) — architecture,
  dependency sequence and this handoff.

These links identify proposed delivery, not merged or deployed capability. The
Appservice PR's hosted offline validation can supply the missing local `mise`
gate; Nix evaluation still needs a Nix-capable environment.

## Sequence from source delivery to a qualified result

1. Inspect live owner items and reservations, bind this source work to existing
   items, and validate the branches with each repository's required tools. Do not
   manufacture a new queue from this document or restart completed work.
2. Refresh owner-local EE-01 evidence using authorized read-only access. Record
   scope/denominator, freshness, unknowns and differences. A complete register may
   expose missing recovery evidence; it must not pretend recovery is proven.
3. Reconcile EE-02 desired/runtime/release/schema/identity/Cloud-hold facts. Preserve
   exact source pins separately from shipped artifacts and observed rollout.
4. Obtain AS-P3/P4 and NX-P2/P3 recovery and isolation evidence for EE-03/EE-05.
   Keep isolated rehearsal targets and recovery-only credentials separate from
   production. No live upgrade, restoration, retirement or exposure follows from
   the source register or passing fixtures.
5. Use the resulting installed composition for Vuoro's EE-06 reference workflow.
   Select the household objective and measurement with its domain owner, retain
   exact artifacts and authority through two sessions, and reconcile an interrupted
   protected operation before retry. The present work does not select a domain
   outcome, fabricate accepted results or qualify the workflow.

EE-07–EE-16 retain their owning-plan design scope while these qualification
dependencies are open. Domain outcomes EE-17–EE-22 remain with their owners.
Nothing in this pickup drops the supported distribution, tenant design, learning
or smaller-tool scope already accepted by the estate plan.

## Validation and operating limits

Appservice source-register and backup fixtures: **52 passed** (13 new boundary
cases and 39 existing backup cases); public-exposure fixtures: **23 passed**.
The register generated successfully in JSON and Markdown against current source;
the snapshot's generator/metadata digests and 92-unit denominator were checked.
`mise run validate` could not run because `mise` is absent. The validation task
now includes source-register fixtures and generation; the full gate is pending.

NixOS deploy guard fixtures: **5 passed**, including a copied-tree rehearsal;
shell syntax, Markdown links and diff checks passed. `nix flake check` could not
run because Nix is absent. All host outputs/aliases and the new derivation still
need evaluation in a Nix-capable environment. Datacluster changes are documentation
only; local links and diff checks passed. No Terraform or provider operation ran.

No estate runtime observation, adoption measurement, restored artifact or cost
receipt was collected. Actual operating effort/cost remains unknown; agent reports
and test counts do not establish EE-23's outcome or support-burden measures.
