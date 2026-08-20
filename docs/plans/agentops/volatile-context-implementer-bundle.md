# Revision-gated volatile context implementer bundle

The complete handoff is landed at
[`volatile-context-implementer-bundle/`](volatile-context-implementer-bundle/).
It was imported from `/home/bayleaf/Downloads/volatile-context-implementer-bundle.zip`
without changing its contents.

Provenance:

- source SHA-256: `91f5982c7ebed964d77823e92f0fe248cdbcd23442779c1fc36bb4f8b373016f`
- bundle version: `0.1.0`
- manifest: [`volatile-context-implementer-bundle/MANIFEST.sha256`](volatile-context-implementer-bundle/MANIFEST.sha256)
- validation: `./scripts/validate-bundle.sh` passed; 20 reference tests passed

This is a cross-repository implementation handoff, not a claim that the
runtime feature is implemented. The ownership split remains:

- AgentOps: cross-repository plan, dispatch/harness distribution, and review
  topology.
- Sprintctl: authoritative task revisions and compare-and-swap mutation paths.
- ActionQ: dispatch binding and harness execution surfaces.
- Vuoro: served projection contracts and service composition.
- Appservice: deployment and rollout, separately authorized.

> **2026-08-20 supersession note.** The bundle is preserved byte-for-byte as
> imported evidence, so its dispatcher-owned binding and attributed-claim
> language is historical. ActionQ's newer target removes its execution plane,
> Sprintctl `origin/main` uses advisory reservations and revision CAS, and
> Outctl is retired. Do not implement those obsolete bundle mechanisms.

The required current mapping is complete in
[`volatile-context-native-runtime-integration-mapping-2026-08-20.md`](volatile-context-native-runtime-integration-mapping-2026-08-20.md).
Use it before production work. The bundle's original
`docs/integration-mapping-template.md` remains unchanged so its recorded
manifest and provenance stay truthful.
