---
status: investigation-and-proposal
stage: S4
date: 2026-11-08
---

# S4: Vuoro Cloud runtime and client skew

Scope: offline source investigation and proposal only. No network request to
vuoro.cloud, live workspace access, cluster change, deploy, or test-workspace
operation was performed by the original worker. The correlation cause was later
confirmed live (see "Why the request fails"). The version inventory below was
read from local checkouts that lag origin/main (vuoro 17, vuoro-cloud 12,
sprintctl 2 commits behind at review time); the **released-artifact check at
2026-11-08 supersedes the 0.1.104/0.28.0 inventory**: see the target section.

## Version inventory

| Component | Observed/pinned version | Source |
|---|---|---|
| Workstation Sprintctl client | 0.20.0, as recorded by the 2026-11-07 readiness observation | [`2026-11-07-vuoro-cloud-workspace-readiness.md`](2026-11-07-vuoro-cloud-workspace-readiness.md#L72) lines 72–75 |
| Live tenant runtime | `vuoro-service` 0.1.94, image `91f61cea5b32…`; tenant schema 3 | [readiness note](2026-11-07-vuoro-cloud-workspace-readiness.md#L18) lines 18–20; vuoro-cloud [`config/compatibility.json`](/projects/dev/vuoro-cloud/config/compatibility.json:11) |
| Tenant manifest's vuoro-client pin | 0.1.2 | vuoro-cloud [`config/compatibility.json`](/projects/dev/vuoro-cloud/config/compatibility.json:6) |
| Sprintctl shipped in the tenant/runtime composition | 0.18.0 | [`config/compatibility.json`](/projects/dev/vuoro-cloud/config/compatibility.json:9) |
| vuoro-cloud qualification lock | Sprintctl 0.25.0 and vuoro-client 0.1.5 | [`uv.lock`](/projects/dev/vuoro-cloud/uv.lock:844), [`uv.lock`](/projects/dev/vuoro-cloud/uv.lock:990); cloud test/CLI extras pin client 0.1.5 at [`pyproject.toml`](/projects/dev/vuoro-cloud/pyproject.toml:20) |
| Sprintctl main source | 0.28.0; served extra pins vuoro-client 0.1.1 | [`pyproject.toml`](/projects/dev/sprintctl/pyproject.toml:7), [`pyproject.toml`](/projects/dev/sprintctl/pyproject.toml:31) |
| Vuoro main source | vuoro-service 0.1.104; vuoro-client 0.1.7 | [`packages/vuoro-service/pyproject.toml`](/projects/dev/vuoro/packages/vuoro-service/pyproject.toml:7), [`packages/vuoro-client/pyproject.toml`](/projects/dev/vuoro/packages/vuoro-client/pyproject.toml:7), [`uv.lock`](/projects/dev/vuoro/uv.lock:968) |
| Work schema needed by the source candidate | 31 for service 0.1.104 / Sprintctl 0.28.0 | vuoro-cloud [`IMPLEMENTATION-STATUS.md`](/projects/dev/vuoro-cloud/IMPLEMENTATION-STATUS.md:42); Vuoro [`tenant-runtime-schema-mapping.md`](/projects/dev/vuoro/docs/architecture/tenant-runtime-schema-mapping.md:41) |

The `compatibility.json` service digest and readiness observation describe
what was recorded for the deployed composition. The source checkout and lock
files describe candidates, not proof of what is currently running.

## Proposed target and reason

**Retargeted after review (2026-11-08).** The earlier proposal, vuoro-service
0.1.104 + Sprintctl 0.28.0 at work schema 31, is superseded by published
releases: `vuoro-service-v0.1.105` (2026-11-08) and Sprintctl `v0.28.1`
(2026-11-07, Latest). Sprintctl 0.28.1 migrates work schema 29 through 34,
declares schemas 32-34 compatible, and **rejects schema 31**
(vuoro `origin/main` `packages/vuoro-service/README.md`, 0.1.105 section).
Migrating the tenant to 31 with 0.28.0 would therefore strand it behind the
next release. Target **vuoro-service 0.1.105 + Sprintctl 0.28.1, work schema
34**. Sprintctl `v0.28.0` is the only artifact tied to schema 31; sprintctl
`main` still reads `version = "0.28.0"` with a higher `remote-schema-version`,
so cite released artifacts, not main source.

The selected vuoro-client must contain the `X-Request-ID` fix (vuoro PR #317,
proposed and open, vuoro-client 0.1.8 not yet released; latest released is
0.1.7), or the gateway must be fixed instead. Without one of them a qualified
pair still fails the live read route. Do not treat Sprintctl's served extra
pin of vuoro-client 0.1.1 as aligned (vuoro-cloud's lock is 0.1.5). Select and
pin one released client version in the Sprintctl served extra, cloud
composition manifest, and lock before qualifying. The exact immutable wheel
URL and digest come from release metadata; this note does not certify a
release artifact.

This is a proposal, not authorization to change pins, migrate a tenant, or
deploy. The rollout must remain `release_ready: false` unless a separate
release-readiness decision changes it.

## Why the request fails

**Confirmed 2026-11-08 (supersedes the inference below).** This is a defect in
the client/gateway handoff, not deployed-image drift. `vuoro-client` puts its
own `request_id` in the invoke body and sends no `X-Request-ID`; the PAT proxy
in the deployed gateway mints its own id, signs it, and the service rejects the
mismatch. Live evidence against `https://api.vuoro.cloud` with a `work:read`
workspace PAT: `work.read.sprints` without the header returns 401
`identity-required`; with `X-Request-ID` equal to the body `request_id` it
returns 200 and `kotona` sprints. Full trace and citations:
[`2026-11-08-s3-vuoro-cloud-read-route.md`](2026-11-08-s3-vuoro-cloud-read-route.md).
Proposed fix: vuoro PR #317 (open; client sends the header; vuoro-client 0.1.8, unreleased) or a gateway-side change that signs the body `request_id`. The
"operator must identify the deployed gateway image" limit below no longer
blocks this item. Version skew remains a separate S4 question.

*Original offline inference, kept for the record:*

The service gateway identity resolver checks that the signed `request_id`,
the upstream `X-Request-ID`, and the request body's invocation ID all match.
In `vuoro-service` this is the guard at
[`gateway_identity.py`](/projects/dev/vuoro/packages/vuoro-service/src/vuoro_service/gateway_identity.py:355)
lines 355–370. A disagreement is returned as `identity-required` with
`gateway identity request correlation failed`.

The current cloud `invoke/v1` forwarding path generates a gateway request ID,
signs it, and sets the forwarded invocation envelope's `request_id` to that
same value ([`gateway.py`](/projects/dev/vuoro-cloud/src/vuoro_cloud/gateway.py:2013)
lines 2013–2025 and 2035–2055). The current MCP forwarding path signs and
forwards the same gateway request ID in the header, while the JSON-RPC body
has a separate message ID. The service resolver's body binding is for the
invocation envelope path; the cloud source must be checked against the
deployed gateway route used by the failed command.

Thus the reported error is evidence of an ID mismatch at the runtime boundary,
not a credential-scope or tenant-schema rejection. The likely failure mode is
that the deployed gateway forwards a client-generated body `request_id` while
signing/forwarding its own transport request ID, or that the gateway and
runtime versions implement different correlation contracts. Current cloud
source contains the needed rewrite, but this does not prove that the deployed
gateway image contains that source. **Offline root-cause limit:** the deployed
gateway image corresponding to the failing route was not inspected, and the
S3 route report is absent. An operator must identify the failing route and
deployed gateway image/source revision before attributing this to a specific
deployed binary. Do not deploy based on the source inference alone.

## Local fake reproduction

The source repository already has a fake-request regression case:
[`test_gateway_identity.py`](/projects/dev/vuoro/packages/vuoro-service/tests/test_gateway_identity.py:399)
sets the HTTP request ID to the signed ID while setting
`invocation_request_id="different-body-id"`; the resolver raises
`IdentityResolutionError`. The helper and signed assertion are in that same
test module, so it uses local keys and fake request state, not a server,
credential, or workspace. Run from `/projects/dev/vuoro`:

```bash
uv run --offline --extra test pytest -q packages/vuoro-service/tests/test_gateway_identity.py::test_gateway_assertion_resolver_rejects_missing_invocation_request_binding
```

This test was not executed in the offline worker; the S3 follow-up ran the
client and gateway-identity suites with network access (138 passed). It is a source-level reproduction of the resolver's
failure condition, not an end-to-end reproduction of the specific deployed
gateway/client combination.

## Composition qualification

`scripts/qualify_composition.py` is offline-safe when run without
`--live-probe` or `--registry-token-file`: it runs disposable local PostgreSQL
composition tests and writes a local receipt. It does not accept version-pair
overrides. First update the cloud composition pins and lock to the proposed
immutable service, Sprintctl, and client artifacts; then run the script on
that exact tree. The documented command is:

```bash
cd /projects/dev/vuoro-cloud
nix develop --command uv run --extra test python scripts/qualify_composition.py \
  --postgres-bin "$(nix build --no-link --print-out-paths .#postgresql_16)/bin" \
  --out .artifacts/qualification-receipt.json
```

Do not pass `--live-probe`, `--live-pod`, or a registry token for S4 local
qualification. After qualification, verify the receipt against the same tree
with `python scripts/qualification_receipt.py verify
.artifacts/qualification-receipt.json`.

**Baseline (2026-11-08, current vuoro-cloud main, run on the workstation with Nix):** `qualify_composition.py` passed 21 scenarios, `release_qualified: false` (blockers: image source unverified, no live probe), exit 0. This is the baseline for main, not the proposed pair.

**Observed output in the offline worker environment:** the documented command could not
start because the Nix daemon socket is not permitted (`cannot connect to
socket at '/nix/var/nix/daemon-socket/socket'`). Retrying with `uv run
--offline --extra test` and a `/tmp` cache could not resolve the uncached
`vuoro-contracts` release wheel because network access is disabled. No
qualification scenarios ran and no qualification result is claimed. Therefore
the proposed pair's current qualification status is **not established**.

## Change and authority sequence

| Repo/action | Work | Operator authority required? |
|---|---|---|
| `vuoro` PR | Client fix and release: send `X-Request-ID` equal to the invocation `request_id` (PR #317 -> vuoro-client 0.1.8), with contract tests; release-note the gateway correlation requirement. | No for authoring/reviewing; maintainer/release authority to merge and publish. |
| `sprintctl` PR/release | Pin the same selected client version in the served extra and lock; publish an attested Sprintctl 0.28.x wheel after tests. | No for PR prep; maintainer/release-signing authority to merge and publish. |
| `vuoro-cloud` PR | Update `compatibility.json`, runtime image pin, tenant work-schema bounds/preference, cloud client/Sprintctl dependencies and lock. Pin the client release that carries the `X-Request-ID` fix (or land the gateway-side alternative); target vuoro-service 0.1.105 / Sprintctl 0.28.1 / schema 34. Keep `release_ready: false`. | No for PR prep; maintainer authority to merge. |
| Composition qualification | Run the command above on the exact candidate tree and retain its receipt; require every scenario pass or declared strict xfail. | No operator authority for the local run; access to Nix/PostgreSQL build environment is required. |
| Test rehearsal | Provision a **new disposable test workspace** matching the held-test constraints; migrate and exercise documented rollback, then retire it through the supported lifecycle when allowed. | Yes: workspace provisioning, migration, backup/restore, and retirement require operator authority. |
| Cloud promotion/deploy | Publish/promote the reviewed cloud release; verify image/source identity and runtime convergence; do not change release readiness. | Yes: signing/promotion and cluster deploy authority. |
| Workstation profile/cutover | Only after S4 gates, update the workstation profile/client and separately follow the record-family cutover plan. | Yes: operator authorization for production endpoint use and the named cutover. |

## Test-workspace migration and rollback plan

The four existing workspaces (`blocker12-canary`, `isolation-proof`,
`g2-gen71-canary`, `g3-gen72-canary`) remain held and untouched. Preserve
their recorded `READY`, maintenance=true, read-only=true states; do not use
them as canaries, unhold them, migrate them, or retire them. The
`isolation-proof` schema-2 workspace is useful only as a documented constraint
for a fresh disposable fixture, not as a target.

1. After approval, provision a new `is_test` workspace from disposable data
   with the same maintenance and read-only protections, and confirm its
   schema/image, backup checkpoint, and empty/known record counts before any
   migration. Keep all four held workspace IDs out of the command inputs.
2. Establish a verified checkpoint before migration. Run the normal tenant
   migration through the supported lifecycle to schema 31 using the candidate
   runtime. Verify migration state, tenant catalog and per-domain ledger
   versions, client handshake/invocation, and before/after counts. Keep the
   workspace fenced from normal user traffic during the rehearsal.
3. Exercise the supported failure/rollback path only on this disposable
   workspace: require `ROLLBACK_REQUIRED`, inspect
   `python -m vuoro_cloud.tenant_rollback plan --workspace <new-id>
   --checkpoint-ref <recorded-ref>`, then have the authorized operator restore
   that exact checkpoint. Run `verify-restored` with the same workspace and
   checkpoint reference. The rollback tool is read-only; restoration is an
   operator action. Confirm schema and counts match the checkpoint before any
   retry or reopening.
4. If restoration and verification pass, re-run the migration forward from
   the restored schema as the rollback module specifies, then verify the
   intended target. Keep the workspace held until the operator decides its
   supported retirement path. On any mismatch, leave it fenced and stop; do
   not attempt SQL repair or alter the four existing held workspaces.

No migration or rollback rehearsal has been performed. The readiness record
also says the cluster rollout gate still counts held workspaces; their
agentops estate allowlist does not exempt them from vuoro-cloud rollout or
fleet-convergence gates.
