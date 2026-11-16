# Resident execution paths

**Status: implementation and commissioning guidance, 2026-11-16.** The source
changes do not activate a host, timer, model credential or external effect.
Use [resident-memory.md](resident-memory.md) for the memory/context contract and
lanectl's [episode commissioning](https://github.com/bayleafwalker/lanectl/blob/main/docs/resident-episodes.md)
for admission, fencing and recovery. AgentOps owns the integration guidance;
native OpenCode owns execution, lanectl owns episode admission, and the existing
work/effect owners retain their authority. No AgentOps model router is added.

## Choose the executor and the generation route separately

| Path | Executor | Explicit generation route | Appropriate use |
|---|---|---|---|
| Devbox + hosted | Isolated resident service on devbox | OpenCode Go `opencode-go/deepseek-v4.1-flash`, using the exact qualified provider binding | Work while the workstation is unavailable; ordinary hosted native execution |
| Devbox + local GPU — recommended local arrangement | Same isolated devbox resident | Guarded workstation model peer, `worker-fast` | Keep durable work and memory independent of workstation availability; use the 3090 on demand |
| Workstation + local GPU | Separate isolated resident system service on workstation | Same `worker-fast` serving owner through a local fixed gateway | Keep the entire executor on the workstation without using the regular login account |

These are explicit selections, not an ordered fallback list. Provider denial,
GPU unavailability or an exhausted configured hosted request allowance stops or
defers that selected route. It does not authorize another provider or model.
An OpenCode subscription is not a generic Hindsight LLM or embedding credential.
The provider-qualified hosted ID and endpoint must match the installed OpenCode
catalog and the owner route record; a model name alone does not prove either.

The workstation option uses its own service UID, HOME, XDG directories, temporary
files, network namespace and workspace. A different HOME alone is insufficient. The protected
launcher must enforce filesystem, process and network boundaries, deny access to
the regular user's home and runtime directory, and omit display/session, SSH/GPG
agent, Docker/libvirt and supervisor sockets. The resident gets no GPU device:
its shell/tools call the fixed model gateway. Arbitrary changes inside its own
workspace remain allowed within the charter. Host configuration, credentials,
gateway policy and admission receipts remain outside that writable tree.

The existing GPU service is a separate trusted component. Its historical use of
the regular user's UID/cache does not grant those privileges to an HTTP client.
Moving that service to a dedicated inference UID/cache is a separate host-owner
migration; do not create a second competing GPU router to isolate the resident.

## Source-qualified workstation assumptions

The following are source observations, **not a new live-host verification**:

| Source | Observed configuration |
|---|---|
| [`local-inference` at `217916a1`](https://github.com/bayleafwalker/local-inference/blob/217916a1c7ed4bc6caa572b9f9c6e2fdc766ea33/README.md) | NixOS owns the deployed system unit. `ops/nixos` is historical; serving profiles and measurements remain in local-inference. |
| [Serving profiles at the same revision](https://github.com/bayleafwalker/local-inference/blob/217916a1c7ed4bc6caa572b9f9c6e2fdc766ea33/configs/llama-swap.yaml) | `worker-fast` is Qwen3.6-35B-A3B `UD-IQ4_XS.gguf`, llama.cpp, 65,536 context, one slot, thinking off, idle TTL 1,800 seconds, one exclusive GPU group. |
| [Context policy](https://github.com/bayleafwalker/local-inference/blob/217916a1c7ed4bc6caa572b9f9c6e2fdc766ea33/configs/model-routing.yaml) | HOT target is 12,288 input tokens; retrieve/compact/decompose before overflow. No general escalation target. |
| [`gitops-nixos` mirror at `56a90506`](https://github.com/bayleafwalker/gitops-nixos/blob/56a90506fbe3e71de49aa44655affdf266bdafae/modules/system/llm-inference.nix) | Declarative service owner is `modules/system/llm-inference.nix`. The inspected source still uses the regular user and its cache for the trusted GPU service. Canonical-forge freshness and the activated generation were not established here. |
| [Model peer at that mirror revision](https://github.com/bayleafwalker/gitops-nixos/blob/56a90506fbe3e71de49aa44655affdf266bdafae/modules/system/llm-inference/model-peer-proxy.py) | TLS, bearer, source allowlist and model allowlist. Generation routes only; no `/v1/embeddings`. `/healthz` is proxy liveness; `/v1/models` is synthesized from policy. |

Two known source mismatches need explicit handling when commissioning:

- Local-inference's `worker-fast` command requires `--device CUDA0`; the inspected
  [vendored Nix configuration](https://github.com/bayleafwalker/gitops-nixos/blob/56a90506fbe3e71de49aa44655affdf266bdafae/modules/system/llm-inference/config.yaml)
  lacks that argument. Reconcile the intended host revision and verify real GPU
  generation; do not infer it from a successful health check.
- `configs/integrations/opencode.speculative.jsonc` still names retired
  `think-robust`. Use the current route record and native launcher examples,
  not that historical snippet or old Devstral escalation prose.

Here **on demand means request-triggered model load and idle unload after 1,800
seconds**. It does not install Wake-on-LAN or power on the workstation. One model
owns the card at a time. Keep related episode work on `worker-fast`; profile swaps
discard resident state and compete with desktop use.

## Install through the execution and host owners

Use lanectl's native examples:

- [`contrib/resident/native-go.example.json`](https://github.com/bayleafwalker/lanectl/blob/main/contrib/resident/native-go.example.json)
- [`contrib/resident/native-local.example.json`](https://github.com/bayleafwalker/lanectl/blob/main/contrib/resident/native-local.example.json)

Render the reviewed OpenCode configuration before installing the protected
recipe. This is a pure rendering command, not qualification or execution:

```sh
python -m lanectl.resident_native render-config --config SOURCE.json
```

The immutable launcher entry point is:

```sh
python -m lanectl.resident_native run --config /etc/lanectl/resident-native.json
```

Run it through the qualified lanectl episode path, with the admitted context,
generation and output contract supplied by the owner. Do not invoke it as an
unattended login-shell loop. The host owns the protected configuration, separate
resident service identity, cgroup/resource limits, home/socket exclusions and
network enforcement. Workstation placement requires these same protections.

The resident gateway is a separate service identity. The NixOS composition
passes only its fixed filesystem Unix socket into the worker's private network
namespace. A bounded local relay exposes `http://127.0.0.1:18021/v1` there;
the regular user's localhost and abstract Unix sockets are outside that namespace.
The host socket permits the dedicated worker group, and the gateway permits
only its configured upstream and model. It holds upstream credentials
outside the tool process, uses a protected `/etc/lanectl/resident/gateway.json`,
and never forwards caller-supplied destinations or credentials. The hosted and
local examples select one upstream each. Remote GPU transport additionally needs
a separately authorized source, resident credential and verified TLS identity;
the existing cluster-client grant is not an implicit devbox grant.

Use lanectl's [NixOS module and host procedure](https://github.com/bayleafwalker/lanectl/tree/main/contrib/resident/nixos)
for immutable package/profile generation, socket activation, the private
worker filesystem/network, explicit cgroup cleanup and target probes. Current
OpenCode standalone mode uses a private ephemeral HTTP server; confining its
private namespace preserves that IPC without opening host localhost services.

The native launcher receives the exact admitted context packet. Its scoped
filesystem/shell tools do not thereby gain a dynamic memory plugin, raw Hindsight
API access or memory-service credentials. Dynamic `memory_search` remains an
optional separately qualified facade integration described in the memory runbook.

## Memory deployment for either executor

Use the [CPU embedding and local generation deployment example](../../integrations/hindsight-resident/deployment/README.md).
Keep PostgreSQL, the source/ingestion receipt store and protected memory services
on the durable host; devbox is the recommended location when the workstation may
be off. If all services are placed on the workstation, persistence survives a
stop but availability does not.

The memory route is explicit: `worker-fast` for extraction and admitted
consolidation; pinned local CPU embeddings; RRF reranking without another model.
`worker-fast` is a candidate for this workload until the real memory canary
passes. Its general coding qualification is not memory-quality evidence.
The memory service requires its own protected gateway access and identity; the
native resident gateway's tool-UID allowance does not grant that access.

If the GPU is unavailable, exact source snapshots and context construction remain
available when their own host is running. Existing semantic recall may still work
with CPU query embeddings and the database, but fresh extraction/consolidation
cannot. If recall itself fails, the facade records `memory-unavailable` and the
context includes that omission; required exact sources still control admission.
Do not call a failed extraction retained or an unknown acknowledgement queued.
The adapter durably records submission identity and uncertainty; there is no
automatic retry, consolidation scheduler or GPU-availability queue in AgentOps.
The existing owner must explicitly reconcile/admit later processing.

## Bounds and stop/continue policy

Local inference has no aggregate monetary/request allowance by default. It still
executes finite operations; an unlimited supply of on-demand GPU time does not
make an individual episode or request unbounded.

| Bound | Mechanism and meaning |
|---|---|
| One coordinator per workspace | lanectl workspace lock, durable wake identity and generation fencing |
| Episode at most 2,700 seconds | lanectl deadline plus qualified host process/cgroup cleanup |
| One request in flight per resident gateway | Gateway serialization; the GPU profile also has one generation slot |
| Local model request configured for 900 seconds | Gateway connected-read deadline; host DNS/initial TCP/TLS bounds also require observation, and cold load consumes episode wall time |
| At most 8,192 requested output tokens per call | Gateway output bound; request/response byte limits are separately configured |
| Hosted request allowance | Operator-configured rolling gateway counter, for example 120 attempts per 3,600 seconds; this is neither provider entitlement nor a monetary/token ledger |
| Context envelope | Native profile may request 20,480 total with 8,192 output, leaving a 12,288 input target. Exact tokenizer accounting must be observed before claiming that target was met. |
| CPU/RAM/process/disk use | Host cgroup and filesystem limits; a polling size check alone is not a disk quota |

Stop on completion, no eligible work, a dependency wait, unavailable required
context, route failure, budget denial, timeout, interrupted execution or a failed
qualification/source check. Checkpoint the artifact, exact basis, unresolved work
and stop reason. A proposed continuation is data for the existing admission owner;
it does not launch itself. That owner may admit another bounded episode with a
fresh wake ID after checking current work and resources. Replaying the prior wake
returns its receipt. This implementation adds no autonomous timer or task-count
quota and does not require daily operator approval for the local route.

Self-evolution uses the existing candidate/evaluator/pointer workflow. The
resident can propose changes to its charter, context strategy or workspace code;
it cannot replace its own boundary, credential gateway, evaluator or receipt
authority. External mutations continue through their established effect owner.

## Qualification and rollback

Commission one route at a time with execution disabled until the existing
protected qualification receipt is earned. Record the exact native binary,
generated configuration, route, upstream/model identity, host revision and
recipe/source-check digests. Exercise these concrete boundaries:

1. Generate through the chosen route, including a real local cold load. Proxy
   liveness/catalog responses are insufficient. Check an unavailable upstream,
   rejected model and rejected alternate destination; none may select a fallback.
2. From arbitrary native tool code, attempt regular-user home/session/socket,
   credential and direct-network access. Confirm access is denied and the
   process tree disappears after a deadline or cancellation.
3. Complete three fresh native episodes using corrected exact source and one
   bounded critic. Check wake replay, source changes, continuation proposals and
   the final artifact independently of the conversation history.
4. Separately qualify memory retain/operation completion, scoped recall, source
   correction, CPU-only embedding identity and denied banks. Test GPU outage
   without losing exact context or inventing a successful ingestion receipt.

To pause, stop new admissions and drain/stop the resident service; preserve its
workspace, generation and receipts. Roll back the protected launcher/profile and
gateway configuration through the host owner's previous generation, then
requalify the changed recipe. An executor move never runs both coordinators
against one workspace: fence and stop the old placement first.

For a memory rollback, use the matched backup procedure in
[resident-memory.md](resident-memory.md#recovery-and-rollback). Preserve later
corrections, revocations, budget observations and external-effect receipts when
restoring. An embedding identity/dimension change is an explicit reindex/data
migration, with the previous artifact and compatible database available for
rollback; restarting with a different model name is not that migration.
