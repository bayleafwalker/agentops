# MI-1 native evidence commissioning

Served agentops item 2618 is the explicit native identity prerequisite for P2
item 2613. This record covers one real Codex session and one captured GitHub
check response; it is not the different-harness Track B result.

## Source, publication and live projection

Vuoro PR184 introduces optional issuer-controlled workspace metadata; PR185
releases service 0.1.85 at `8c5b64f3a9b295a68273cab32fdcd9c9527e36b4`.
Both publication workflows succeeded. `publication.json` records successful
specific-workflow GitHub attestation verification for the immutable image
index, and the actual installed Sprintctl 0.12.0 / auditctl 0.1.6 versions.
These adapter pins are unchanged; no schema or runtime role mutation occurred.

Appservice steady-state main PR1830 merged at
`a6fe44ffbf00deb635c1501071b54a2e2f6119f5`. Required local validation,
exact-head CI and post-merge Offline Validate / State protocol checks passed.
`native-gitops-convergence.json` records the same source and Kustomization
revision, ready deployment and identity revision 10. `native-handshake.json`
records service 0.1.85 and compatible work/audit domains.

The SOPS candidate comparison proved all five old identities unchanged. A
separate token adds principal `vuoro-static:workstation-mi1-native:0`, explicit
standalone partition `vuoro-native:agentops-mi1:0`, agentops-only repository
scope, and only `work:read` / `work:evidence`. This is not a Cloud workspace.
The compatible released image accepts the registry. The separate mode-0600
host credential is referenced by agentops PR314's explicit native profile;
credential bytes and decrypted registry contents are absent here. Rollback is
recorded in appservice's `docs/migrations/2026-10-mi1-native-evidence-identity.md`.

## Real run and original provider capture

`run-register-request.json`, its owner receipt and `run-binding.json` record
registration/resolution of the actual session using the new authenticated
identity. Harness build and observed instruction digest remain `unknown`.
Skill digests are observed file hashes, not complete instruction attestation.
Client/grant are null on this direct native bearer path.

The GitHub response's unaltered gh API output body and capture metadata are
already immutable at Vuoro `dccc0c306bcb854ddce907dc533b6c2ffff42113` under
`docs/evidence/2026-10-06-mi1-provider-api-capture/`. The normalized observation
and append request here retain an explicit `check_run_response` family and
captured request repository. Artifact digest, check revision and other absent
provider facts remain unknown. Assurance stays `unverified-supplied-payload`;
no HTTP signature or protected verifier assertion was observed.

## Measured client repair

Initial durable sync refused `work.run.resolve-v1` with `repo-id-required`,
before append. The request remained pending and unchanged. The Sprintctl
native transport helper had omitted the configured repository envelope.
The owner repair forwards explicit repository scope for run resolve and
append, retaining the two-operation allowlist and owner retry/chain semantics.
The associated owner verification packet records before/after regressions,
CLI forwarding and test-fixture environment corrections.

Sprintctl PR126 merged at `a57db170042523b457618de4ef971551c79ca84d` after
all four exact-head checks passed, including disposable PostgreSQL integration.
The existing source fallback then retried the original pending request.
`provider-sync-confirmed.json` records owner confirmation and no pending
request. Its original source and binding SHA-256 remain unchanged.

`provider-owner-tail.json` and `provider-exact-retry-receipt.json` show the
recorded observation at chain sequence 0 and the same item on exact replay.
The tail remains identical after retry and refusal checks.
`provider-recapture.json` proves exact original bytes recapture as the same
request; `provider-sync-repeat.json` shows no attempts or pending requests.
`native-effect-refusals.json` records HTTP403 `authority-required` for both
public accept and mark-applied with catalog-valid, uncreated intent subjects.
This is a public authority gate test, not verification of an actual protected
effect or of wrong-artifact approval reuse. The separate owner fault-history
packet proves its stated bounded synthetic histories.

The native commissioning prerequisite is now measured end to end. This is not
full MI-1 acceptance, protected verification, a signed provider delivery,
concurrent live delivery or different-harness continuation. Those remain
separate P1/P3/Track B work.
