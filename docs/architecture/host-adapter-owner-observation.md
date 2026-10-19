# Host-adapter owner initialization and metadata observation

The host adapter now completes the released Vuoro client's handshake before it
invokes any owner operation. Client construction and `__aenter__` alone do not
perform that handshake. A failed profile load, client entry or handshake leaves
no cached client or open event loop; a retry starts a fresh client. Successful
initialization is cached until `close()`.

This uses the existing client contract: the expected environment must match,
the client protocol must be in the service's range, and a supplied service release
identity must have the recognized distribution and nonempty version. An absent
release remains permitted by that client and is reported as unknown. This is
neither an exact deployment-version pin nor a continuous check after the initial
handshake. The existing typed owner methods and invocation envelopes are unchanged.

## Read-only inspection

With an interpreter that has the released `vuoro-client` installed:

```sh
python scripts/host_adapter.py --profile /path/to/profile.json inspect-owner
```

The command opens no adapter state, harness, policy, password or run directory.
It performs the checked handshake and a fresh catalog GET, then closes the client.
It invokes no owner operation. Its JSON exit statuses are:

- `0`, `exact-match`: every inventoried contract field for every declared owner
  call matches, with supported schema features and no additional contract fields.
- `1`, `drift`: at least one operation is missing, duplicated, has changed or
  missing fields, requires an unsupported feature, or adds a contract field.
- `2`, `unavailable`: the local inventory, profile, handshake or catalog could
  not be read or checked. Each identifiable owner call remains explicitly unknown.

The command derives the 14 operation names from the actual `VuoroOwner` call
sites. A newly dynamic or stale operation inventory cannot silently pass. The
expected contracts come from the immutable historical EC-01 record
`agentops:vuoro-owner-port` in
`2026-10-18-estate-first-consumer-contracts.json`. The observation records its
SHA-256, the current adapter source SHA-256, operation-name digest and installed
client version. This inventory remains descriptive evidence, not a new IDL or
generator foundation.

Each operation includes its expected authority, envelope idempotency, repository
scope and execution semantics. Input and result schemas and all other contract
fields carry canonical JSON digests and explicit comparison states. Array order
is significant; a drift is not automatically an incompatible semantic change.
Observed server text is represented by digests rather than copied into the
report. Profiles, credential references, endpoints, environment names and raw
errors are omitted. Extra, unconsumed catalog operations contribute only a count.

`effective_authority` and `execution_acceptance` are always `unknown`, including
when all fields match. A catalog declaration does not prove that the selected
identity can execute an operation. Handshake and catalog are separate reads;
this observation does not claim an atomic service snapshot or a stable deployment
through subsequent execution. It does not complete EC-01 or discharge EC-00,
EC-02, EC-03 or Auditctl's EC-07 prerequisites.

## Verification and installation boundary

`scripts/tests/test_host_adapter_owner_inspection.py` exercises local inventory
coverage, lifecycle cleanup/retry, drift, unavailable metadata, redaction, CLI
exit states and absence of execution dependencies. The optional released-client
replay is run explicitly with the installed package:

```sh
/path/to/released-client-python scripts/tests/test_host_adapter_released_client.py
```

It uses the actual `vuoro-client` transport over `httpx.MockTransport`, with
fixture-only profiles and credentials. It asserts no catalog or invocation
request after an incompatible handshake, fresh retry after a 503, and only the
two metadata GETs during inspection. The default scripts suite skips this file
when that optional client is absent; that skip is not released-client evidence.

The retained live observation used the existing workstation profile and client
0.1.1, plus a request guard that rejected anything except handshake/catalog GETs.
All 14 consumed operations matched in a catalog of 126 operations. This proves
metadata reachability and comparison only. No live owner operation, handoff,
launch, cancellation, revocation or service rollout was exercised.

As measured on 2026-10-19, neither the workstation system nor bayleaf user scope
has an `agentops-host-adapter.service` installed. The workstation `agentops`
command resolves to `/projects/dev/agentops/bin/agentops`, which invokes the source
checkout with system Python; its optional client dependency must be present in
the selected interpreter. The Gitops NixOS devbox package is a separate deployment
path. Read-only inspection of the actual devbox found the adapter active/running
from package `agentops-host-adapter-7aa1f71dcd27` in system generation
`c2sc6f4s77vs5zhmm1dn7xfjwaxx45gd-nixos-system-devbox-26.11.20261015.fe13242`. Its verified canonical source pins the currently running Agentops commit
and copies only three Python scripts. A reviewed package bump must also install
this inventory at
`$out/share/docs/architecture/2026-10-18-estate-first-consumer-contracts.json`,
next to the installed script's sibling `docs` directory. Without that file,
inspection deliberately returns `inventory-unavailable`; normal owner execution
does not depend on the observation inventory.

After Agentops landing, the deployment owner can pin the accepted revision and
source hash in `gitops-nixos/pkgs/agentops-host-adapter.nix`, copy that inventory,
and extend the installed-wrapper check to verify the 14-call binding and run
these refusal fixtures against the installed code/client. Build the package,
flake checks and devbox system closure before switching a generation. Then run
the installed wrapper's `inspect-owner` with the adapter identity and its existing
root-owned profile; capture exact package/service/client identities and the
redacted report. No second adapter may compete for the same state directory.

The active devbox reports configuration revision
`c3c6301f70031399e733751a1f73a77d2e1eb727`. That revision and the verified canonical
Gitops `origin/main` at `ad4b0b821845e7dd78a2ee5bdc33e961f304770c` both set
`launchesEnabled = true` and `runDelegationQualified = true`, matching the measured
runtime policy (`enabled = true`, `max_concurrent = 1`). The workstation's stale
local Gitops `main` had false flags and an older package; it must not be used as
the deployment basis. A package-only bump on canonical source must preserve the
existing flags and other commissioning settings. This change itself authorizes
no gate transition.
Any new qualification or enablement still requires the existing
`gitops-nixos/docs/runbooks/devbox-run-delegation.md` commissioning chain: retire
the legacy adapter, rotate the old principal epoch, install the isolated decision
credential, and verify one bounded continuation through mint, protected handoff,
context/note, settlement and revocation, including interruption/recovery and stale
credential refusal. The metadata observation does not waive those holds.
