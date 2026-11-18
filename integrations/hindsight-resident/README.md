# Downstream Hindsight source transport

This directory preserves the small downstream patch and exact tested tree while
publication to the canonical forge is unavailable. It does not move memory-engine
ownership into AgentOps. `manifest.json` binds the public upstream commit, patch
SHA-256 and resulting Git tree. No model weights, database, credentials or private
memory are included.

Materialize a new checkout:

```sh
python scripts/prepare_resident_hindsight.py /absolute/new/path/hindsight-resident
```

The preparation command fetches the public upstream, verifies the exact base and
patch, applies it to the index and verifies the complete resulting tree. The local
branch is `resident/v1.2.1`, with `upstream` as its read-only source remote. Existing
directories are refused. No remote fork is created, no commit is pushed and no
dependency or service is started.

After reviewing and committing the staged downstream changes, publish to the
established canonical forge when its authenticated owner path is available. Keep
upstream read-only. Preserve Hindsight's root MIT `LICENSE`; downstream source in
the patch is offered under that same license. The full license remains present in
the materialized checkout.

Changes comprise the resident policy extension, split API/worker system story,
packaging/environment template and managed-context coding-agent transport. Follow
`hindsight-extensions/resident/README.md` in the resulting checkout for the actual
server contract, tests and separate deployment qualification.

The manifest records source reproduction, not a reproducible container image or a
host acceptance result. OS/dependency resolution must be locked through the host
build pipeline and the final runtime image selected by digest.
