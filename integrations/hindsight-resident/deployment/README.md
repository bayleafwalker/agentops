# CPU embeddings with on-demand local memory generation

This deployment example uses Hindsight's existing local embedding provider and a
separately granted `worker-fast` chat route. It applies to either resident
executor placement in the [execution runbook](../../../docs/runbooks/resident-execution-paths.md).
It creates no host service, scheduler or public endpoint. The endpoint/credential
placeholders are deliberately incomplete; no service is running by virtue of
these files.

## What is pinned

- Hindsight source and downstream patch: the parent [manifest](../manifest.json),
  upstream v1.2.1 commit `0eb02d8c418eac6b489bc63883c993b2257dfac4`.
- CPU model: [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5/commit/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a)
  at `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, MIT, 384 dimensions and a
  512-token input limit. [The weight's published SHA-256](https://huggingface.co/BAAI/bge-small-en-v1.5/blob/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a/model.safetensors)
  is recorded in [embedding-artifact.json](embedding-artifact.json).
- Runtime location: an immutable, read-only local model directory, not a mutable
  Hub name or the regular user's cache. `local-cpu.env.example` forces CPU and
  offline loading. The host also omits GPU devices.

The model is an economical English baseline already used as Hindsight's local
default, not a multilingual or long-document qualification. Check retrieval on
the actual corpus, including long facts and names. The 512-token limit still
applies when a source document is much longer; exact source context remains
separate. Pinning weights alone does not pin Python/OS dependencies: capture
the final runtime image digest and complete model-file hash list in the release.

## Build the CPU-capable image and model artifact

First materialize the downstream source using the parent [README](../README.md).
From that Hindsight checkout, use the downstream build sequence with local ML
dependencies enabled and automatic model downloads disabled:

```sh
docker build -f docker/standalone/Dockerfile --target api-only \
  --build-arg INCLUDE_LOCAL_MODELS=true --build-arg PRELOAD_ML_MODELS=false \
  -t resident-hindsight-base:1.2.1-cpu .
docker build -f hindsight-extensions/resident/Dockerfile \
  --build-arg HINDSIGHT_IMAGE=resident-hindsight-base:1.2.1-cpu \
  -t resident-hindsight:1.2.1-policy1-cpu .
```

Use immutable image digests in the host declaration. These local build tags are
construction names, not reproducible deployment references. The downstream's
generic `INCLUDE_LOCAL_MODELS=false` recipe cannot provide this CPU embedding
configuration.

In a trusted build environment, use the `huggingface_hub` dependency already
resolved for the image to download the exact revision and selected files from
`embedding-artifact.json`. This example is run from the AgentOps repository:

```sh
python - <<'PY'
import hashlib
import json
from pathlib import Path
from huggingface_hub import snapshot_download

spec = json.loads(Path("integrations/hindsight-resident/deployment/embedding-artifact.json").read_text())
destination = Path("/tmp/resident-embedding-build") / spec["revision"]
snapshot_download(repo_id=spec["repository"], revision=spec["revision"],
                  allow_patterns=spec["files"], local_dir=str(destination))
hashes = {}
for relative in spec["files"]:
    path = destination / relative
    hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if relative in spec["known_sha256"]:
        if hashes[relative] != spec["known_sha256"][relative]:
            raise SystemExit("embedding artifact digest mismatch: " + relative)
(destination / "SHA256SUMS.json").write_text(json.dumps(hashes, sort_keys=True, indent=2) + "\n")
print(destination)
PY
```

The build owner packages the listed files, their hashes and license/model-card
provenance into its immutable artifact store. Mount the resulting directory at
the manifest's `runtime_path`, read-only, for API and worker. Keep the download
cache out of the runtime mount. Record the artifact/tree digest alongside the
container digest; do not make a writable directory immutable merely by naming
it after a commit.

Hindsight's pinned `LocalSTEmbeddings` accepts a filesystem path, passes
`force_cpu` and `trust_remote_code` to its loader, and skips prefetch for an
existing directory. It has no model-revision environment setting. The immutable
directory is the revision boundary. The source is
[`engine/embeddings.py`](https://github.com/vectorize-io/hindsight/blob/0eb02d8c418eac6b489bc63883c993b2257dfac4/hindsight-api-slim/hindsight_api/engine/embeddings.py)
and [`engine/local_device.py`](https://github.com/vectorize-io/hindsight/blob/0eb02d8c418eac6b489bc63883c993b2257dfac4/hindsight-api-slim/hindsight_api/engine/local_device.py).

## Apply the complete environment template

Use [local-cpu.env.example](local-cpu.env.example) as a **complete alternative**
to the downstream `service.env.example`, not an overlay that leaves remote
embedding endpoints, API keys or query/passage overrides behind. Host-owned
configuration must remove inherited provider fallback/per-operation overrides.
Change the exact bank in both this template's LLM route and the protected tenant
policy when commissioning a different project.

The API and standalone worker use the same image, model artifact, protected policy
and common environment; set `HINDSIGHT_API_WORKER_ENABLED=false` only on the API.
Run database migrations separately and start both processes from the downstream
image's trusted `/opt/resident-service` directory, whose empty `.env` prevents
project dotenv discovery. Follow the downstream README for process commands,
non-root identity, policy grants and database backup. Do not mount the resident
workspace into the raw memory service.

The memory gateway address is a deliberate placeholder. Provision a separate
memory-service grant through the host's fixed gateway owner, with verified TLS
when crossing hosts, `worker-fast` as its only model, bounded chat requests and
no fallback. The native resident gateway at port 18021 is restricted to its
tool UID and does not automatically admit the memory UID. The memory service gets
only its scoped gateway credential; it does not receive the workstation peer's
upstream token or an OpenCode subscription credential. No `/v1/embeddings` route
is used or required.

The local embedding workload is controlled by CPU/RAM/process limits, one local
encoding worker and bounded source/recall operations. It does not incur remote
embedding spend. LLM generation is serialized per memory process, with 8,192
completion-token ceilings and explicit timeout. API and worker are separate
processes, so their settings are not a global semaphore; the gateway/GPU owner
must handle contention with native execution. Keep extraction and consolidation
off the critical path of a native episode where possible.

## Qualify, observe outages and roll back

Keep admission disabled until these checks succeed on the selected host:

1. In the actual image with outbound Hub access denied and no GPU devices,
   load the exact local path, encode a canary and verify 384 dimensions, CPU
   placement and the complete mounted artifact hash list. Missing files must
   fail, not trigger a runtime download or different model.
2. Through the memory gateway, run real `worker-fast` extraction and one
   explicitly admitted consolidation. Poll the retained operation to completion;
   verify provenance, source correction and denied-bank isolation through the
   facade. A successful chat alone does not establish structured-output quality.
3. Stop/unavailable-test the GPU route. Exact snapshots remain usable; CPU-based
   recall of already indexed facts may remain available. New semantic processing
   must report its actual pending/failed/unknown state. AgentOps supplies durable
   receipts, not an automatic retry or model-availability queue.

The template disables autonomous consolidation/page/model sweeps, provider batch
work, bank configuration writes, MCP and file uploads. It also disables automatic
LLM/worker retries; later processing requires reconciliation/admission through
the existing owner. Do not label an unknown ingestion successful, delete its
receipt to retry, or send the same work to a hosted fallback.

For rollback, stop new admission and drain/stop the worker; preserve the latest
receipt/source state; restore a compatible image, policy, artifact and database
set through the existing host recovery procedure. Changing the embedding model,
dimension, prompts or normalization is a data/reindex migration. Preserve the
old artifact and compatible database; do not combine old vectors with a newly
named model and describe it as recovery.
