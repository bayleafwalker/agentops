# Neglect ledger

Status: implemented, opt-in, read-only tooling. This runbook and its examples do
not assert that an estate has been inspected.

The question is what can be established if the operator disappears at a stated
time **while existing automation continues**. A certificate expiry is a boundary
for that certificate. It is not a predicted outage when a renewer may replace it.
A recovery drill becoming due is a proof obligation, not an outage either.

`scripts/neglect_ledger.py` collects a small set of observations and evaluates
them against an explicit inventory. It does not modify dispatch lanes, repair
services, refresh credentials, schedule a job, or establish recovery authority.
Inventory, receipts and reports belong in a private location outside this public
repository. Only synthetic fixtures belong here.

## Run it

Requirements: Python 3.10 or later. Local certificate probes additionally require
`openssl`; timer probes require `systemctl` and access to the selected manager.
Neither is needed to evaluate saved observations.

Start from [the synthetic inventory](../examples/neglect-inventory.example.json).
Replace its placeholder revisions, obligations and evidence references with
inspected sources. Use `{"kind": "none"}` for anything without a runtime probe or
receipt. A source-only seed is useful: it makes the missing observations visible.

```bash
python scripts/neglect_ledger.py collect \
  --inventory /private/neglect/inventory.json \
  --output /private/neglect/observations.json

python scripts/neglect_ledger.py evaluate \
  --inventory /private/neglect/inventory.json \
  --observations /private/neglect/observations.json \
  --output /private/neglect/ledger.json \
  --markdown /private/neglect/ledger.md
```

Evaluation defaults to the current UTC instant. `--at` accepts an explicit
timestamp with a timezone offset for a reproducible cutoff, for example
`--at 2026-11-13T10:00:00Z`. That example instant is synthetic. Do not turn a
date-only source into a fabricated observation time. Preserve date-only history
in its source reference and leave its observation unknown.

The collector uses its real hostname and current time. There is no command-line
override to impersonate a different host. A local probe's `collect_on` must equal
that hostname; otherwise its result is `wrong_collection_host`. Run collection
on the host being inspected, or collect an independently dated receipt there and
use the receipt probe. This prevents a cloud workspace from quietly becoming
evidence about a homelab.

Outputs are atomically replaced with mode `0600`; newly created immediate output
directories use `0700`. Existing directories are not chmodded. The command
refuses to replace its inventory, observation input, certificate or receipt
inputs. It does not print observations to stdout. JSON is canonical; Markdown is
a view of the same evaluation.

Exit status `0` means the command completed, **not** that the estate is healthy.
`evaluate --require-complete` writes the report and returns `2` when coverage is
incomplete. Invalid inputs or inaccessible output return `1` without copying
private input contents into the error. A failed individual probe becomes an
unknown observation, so the other obligations can still be evaluated.

## Inventory contract

The validator rejects unknown fields and arbitrary probe commands. Version 1 has
these top-level fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `inventory_id` | Stable private inventory identifier |
| `scenario` | `operator_absent_automation_continues` |
| `source_revisions` | Object mapping repository identifiers to full immutable 40- or 64-character lowercase hexadecimal revisions |
| `obligations` | Explicit denominator: every expected obligation, including currently unobservable prerequisites |

Each obligation requires `id`, `kind`, `source_ref`, `max_age_seconds`, and
`probe`. IDs are unique; every dependency and renewer must have its own entry.
`source_ref` should identify the inspected contract at a revision, such as
`repo@revision:path#section`. The collector does not fetch or interpret that
reference. `max_age_seconds` is the maximum accepted runtime evidence age, from
one second to 366 days; choose it for the particular observation.

| Kind | Date interpretation |
| --- | --- |
| `expiry` | Observed hard expiry of the current object, such as certificate `notAfter` |
| `retention` | Observed retention boundary, or a boundary derived from a qualified recovery point and `retention_seconds` |
| `renewal` | Automation that requires both a recent successful run and available prerequisites |
| `drill` | Proof obligation; reaching its due time does not assert service failure |
| `manual_action` | Policy deadline that requires an operator action |
| `prerequisite` | A dependency whose current availability needs evidence |

Optional `due` is an object with `at`, `basis: "configured"`, and `evidence_ref`.
It remains labelled configured even when no runtime observation exists. It does
not establish a failure limit. Every timestamp requires an explicit offset.

Optional `renewer_id` identifies the automation that can replace an expiring
object or create newer recovery points. `prerequisites` and `recovery_path` are
ordered arrays of `{ "id": "dependency", "basis": "source", "evidence_ref":
"reference" }`. Allowed edge bases are `source`, `observed`, and `unknown`.
Sources establish the dependency relationship; current observations establish
whether its target is available. A source-backed edge is not evidence that the
dependency currently works.

## Supported observations

| Probe | Inputs | Retained observation |
| --- | --- | --- |
| `none` | None | Explicit unknown, with source reference and no fabricated observation time |
| `certificate` | `path`, `collect_on` | Public certificate `notAfter`, observation time and expiry state |
| `systemd_timer` | `unit`, `scope` (`user` or `system`), `collect_on`; optional `service` | Timer load/active state and, when available, the service's most recent successful exit time |
| `receipt` | `path` | A strictly validated supplied observation |

Relative file paths resolve under the inventory's directory; traversal and
symlinks that escape that directory are rejected. Explicit absolute paths are
supported for public certificates and private receipts stored elsewhere.

The certificate probe calls only `openssl x509 -noout -enddate`. It does not
validate the trust chain, revocation, intended use or private key. Its available
state means that the inspected certificate has not reached `notAfter`.

The timer probe follows the distinction used by
[`hooks/forge-credential.sh`](../../hooks/forge-credential.sh): an inaccessible
user manager is an unknown probe, not an absent timer. A successful not-found
answer is distinct from a local unit file that exists but is not loaded. The
probe preserves the user's runtime and bus environment, inferring normal local
defaults only when they are unset. It never starts or enables a unit.

An active timer alone does not prove renewal. For a `renewal` obligation the
evaluator also requires a recent `last_success_at`, no later than its observation
time, plus an available prerequisite trace. The service probe obtains success
from `Result=success`, `ExecMainStatus=0`, and `ExecMainExitTimestamp`. This proves
what that service reports; choose a service whose successful exit represents the
operation you intend to track. A failed service query cannot supply success.

For domains without a built-in collector, produce a receipt using an appropriate
read-only domain tool or a documented inspection. A minimal **synthetic** example:

```json
{
  "subject_id": "broker-route",
  "observed_at": "2026-11-13T10:00:00Z",
  "evidence_ref": "private-inspection:example-receipt",
  "basis": "runtime",
  "state": "available"
}
```

Allowed receipt fields are `subject_id`, `observed_at`, `evidence_ref`, `basis`,
`state`, `reason`, `due_at`, `last_success_at`, `latest_recovery_point_at`, and
`timer_state`. State is `available`, `blocked`, or `unknown`; basis is `runtime`
or `source`. Available and blocked receipts require a dated observation. A
source-only historical receipt may carry its exact historical timestamp, but
always remains unknown for current runtime coverage.

For retention, `latest_recovery_point_at` means the newest recovery point whose
usability the receipt actually establishes. A successful upload does not itself
establish restore usability. `retention_seconds` must describe a duration-based
policy; it cannot represent count-based, tiered, or exceptional holds. The
derived boundary is conditional on that policy continuing and no newer usable
point appearing. Use an explicit observed `due_at` if the storage system exposes
the applicable boundary directly; leave it unknown when the policy cannot be
represented accurately.

Receipts are trusted assertions by their producers, not signed attestations.
Inventory and observation digests prevent accidental mixing of revisions; they
do not authenticate a receipt or prove the inventory covers the entire estate.
Never include tokens, key material, credential-bearing URLs, or raw command
output in allowed free-text fields. Unknown fields are rejected, and raw probe
stderr is never copied, but the report is private data, not an anonymizer.

## Read the report

Coverage counts expected entries, currently observed entries, and unknown
entries. Both available and blocked observations count as observed. A missing,
stale, future-dated or source-only receipt is unknown. Successful renewal and
recovery-point timestamps cannot occur after their enclosing observation. The
inventory remains the declared denominator; complete coverage is not a claim
that there are no unlisted obligations.

Dependency evaluation follows the declared order and stops at the first missing
edge evidence, unknown or blocked prerequisite, or evidenced cycle. Every
traversed edge retains its basis and reference in the report. A cycle describes
the evidenced dependency declarations and explicitly does not prove a runtime
deadlock. Remove evidence for either edge and that trace stops as unknown. Paths
over 64 levels stop as unknown rather than exhausting the evaluator.

The report separates `expiry_boundary`, `retention_boundary`, `policy_deadline`,
and `proof_obligation`. `due_basis` states whether its date is observed, derived,
configured, or unknown. A date survives only when the evidence needed to support
it does. A configured fallback never silently becomes an observed expiry.

The earliest known conditional limit uses only observed or derived expiry and
retention boundaries whose renewal chain is not currently established as
available. It carries its condition and `outage_prediction: false`. Working
renewal means the current object's expiry does not become the predicted first
failure. Unknown coverage leaves the global first failure unknown; even complete
coverage cannot predict future automation outcomes, so the evaluator never
manufactures a global outage date by sorting raw expiries.

## Verify changes

```bash
python -m unittest discover -s scripts/tests -p 'test_neglect_ledger.py' -v
python -m unittest discover -s scripts/tests -p 'test_forge_credential_timer.py' -v
```

The independent synthetic fixture includes a working renewal chain and an
unknown drill observation. Negative controls stop the renewer, remove success
or edge evidence, cross an expiry cutoff, add a cycle, and make receipts stale
or future-dated. Collector tests distinguish a failed timer query from a missing
timer, enforce the hostname guard, reject arbitrary commands and secret-shaped
extra fields, and prevent output from overwriting inputs.

There is no deployed service to roll back. Stop invoking the command and remove
the generated private observations and report if they are no longer needed. Keep
the inventory and evidence sources when they are required to reproduce a dated
inspection. Review any extract before publishing it; this repository intentionally
contains neither live topology nor operational receipts.
