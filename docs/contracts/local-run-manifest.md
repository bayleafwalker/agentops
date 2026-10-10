# Local dispatcher RunManifest

Status: implemented (agentops#2479, local-dispatcher residual). The hosted path
is vuoro#122 (the `RunManifest` object in
`vuoro/packages/vuoro-evidence/src/vuoro_evidence/run.py`) and vuoro#131
(`register_run` builds one per hosted run). Attribution of native sessions is
agentops#2640 and is not part of this contract.

## Obligations

1. **One manifest per run, at start.** `vuoro-dispatch-build` runs
   `scripts/run_manifest.py emit` once, after the readonly-agent probe and before
   any workspace, route or build stage. The manifest is written to
   `$AGENTOPS_RUN_MANIFEST_DIR` (default `/projects/dev/.claude/state/run-manifests`)
   as `<run_id>.json` by exclusive link. It is never rewritten, and a second write
   under the same id is refused. One `run.manifest` auditctl event announces it.
2. **Every record cites it.** The run carries `{run_id, manifest_digest}` and
   attaches it to:
   - every `dispatch.route.decision` event, as `metadata.run` with a `status`
     that `jev_shadow.py record` resolves against the manifest on disk;
   - every closeout note the run adds to a sprintctl item, as the line
     `Run-Manifest: <run_id> <manifest_digest>` at the end of `--detail`.
3. **Emission never gates the run.** If emission fails (the agent throws,
   prints something that is not JSON, reports `emitted: false`, or prints ids
   that are not well formed), the run proceeds unchanged. Its decision events
   then carry `run.status: "absent"`, and its notes carry no `Run-Manifest`
   line. A record is never dropped because its run is unbound, and no run id
   is guessed after the fact.

## Shape (`run-manifest/v1`)

The composition is the vuoro-evidence `RunManifest`, field for field:
`run_id`, `harness_id`, `harness_build`, `model_id`, `recipe_id`,
`observed_profile {instruction_digest, skill_digests}`, `grant_ids`, `claim_ids`.
`composition_digest` is computed exactly as `RunManifest.composition_digest`
(canonical JSON of the composition without `run_id`), so a reader that has
vuoro-evidence can rebuild the object and compare runs by that key. The record
also holds `schema_version`, `emitted_at`, `emitter`, and `manifest_digest`:
sha256 over the canonical JSON of the whole record except that field. A
reference resolves (`status: "resolved"`) only when the file exists, both
digests recompute, and `manifest_digest` equals the cited digest. Any other
result is `invalid`, `unresolved` or `digest-mismatch`.

| Field | Source | Never |
|---|---|---|
| `run_id` | minted locally as `lrun_<ULID>` | `run_<ULID>`. That is sprintctl's served run namespace (`scripts/vuoro_run_records.py`), and a local process cannot mint one. |
| `harness_id` | declared by the workflow (`claude-code`) | inferred from event text or ids |
| `harness_build` | first line of `claude --version`, else `unobserved` | guessed |
| `model_id` | the sorted set of models the workflow declares it routes to | the model of a session the workflow cannot see |
| `recipe_id` | `vuoro-dispatch-build@sha256:<digest of the script on disk>` | a caller-supplied path |
| `observed_profile.instruction_digest` | digest over the native root-to-CWD `AGENTS.md`/`CLAUDE.md` chain, as observed by `session_binding._instructions` (TS-3) | a compiled or rendered profile |
| `grant_ids`, `claim_ids` | empty at start: the local dispatcher holds no grant and has reserved nothing yet | back-filled. Reservations taken later appear on the records that cite them. |

The 2026-10-10 audit decision on #2479 governs the native side. Native
session metadata (session bindings) may be used to validate emitted records.
It never manufactures work identity, and it is never used to infer an
expected cohort. This contract therefore does not derive a run from a session
binding, and it does not link a binding to a manifest by guessing which
session launched the workflow.

## Reading

```bash
agentops run-manifest resolve --run-id lrun_... --digest sha256:...   # exit 0 only when resolved
```
