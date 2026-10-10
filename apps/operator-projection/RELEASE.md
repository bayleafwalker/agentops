# Operator projection wheel release contract (v1)

This is the existing `operator-projection` distribution, beginning with
version `0.2.5`; no second core wheel or service is introduced. Its source is
`apps/operator-projection`, and the only accepted release tag is
`operator-projection-v<pyproject version>`. The release workflow triggers only
on `operator-projection-v*`, checks the complete tag/version shape, and refuses
unless the checked-out tag commit equals the current canonical `origin/main`
commit. It cannot publish a tag from a feature branch or select any other
Agentops/Vuoro package. A concurrent advance of main is a refusal requiring a
new source/version decision; the job never silently rebases a release.

Agentops has no declared `.claude/gates.json` exception to its normal reviewed
CI, canonical merge and release workflow. The tag format and exact-main check
scope this workflow to its own package and reviewed source; no repository
ruleset, manual enable switch or extra approval is introduced.

The workflow synchronizes the checked-in `uv.lock` on Python 3.12, runs the
complete operator-projection tests, builds exactly one wheel from the same
checkout, and validates the wheel's filename, embedded distribution metadata,
portable P1 module, package version, and exact published `vuoro-client` 0.1.2
wheel URL/SHA-256 pin. It computes a checksum for the built wheel, generates
GitHub provenance using `actions/attest@v4`, and creates a draft GitHub release
with only that wheel and checksum. It then downloads the draft assets, compares
their bytes and checksum, and verifies the wheel attestation against this
repository, release workflow, tag ref and source commit. Only a successful
readback changes the draft to published. A failed run leaves the draft for
inspection; it does not substitute an unverified wheel.

The release job never runs from `workflow_dispatch`, publishes no image, and
does not modify owner Decisions, native tools, Cloud tenants or runtime. The
source package CI is a separate prerequisite: source review, required CI and
canonical merge happen before the package tag. Consumers may pin the exact
published wheel digest only after release asset and provenance readback. A
local `uv build` result is a candidate, not a published or attested artifact.

The publication pattern follows Vuoro's existing
`.github/workflows/publish-python-packages.yaml`, with package selection
removed because Agentops owns only this distribution here. GitHub's
[artifact attestation action](https://github.com/actions/attest) and
[verification guide](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
define the provenance and readback commands.
