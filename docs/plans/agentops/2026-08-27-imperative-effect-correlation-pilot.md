# Imperative effect correlation pilot

**Status:** draft planning handoff; no production-change authorization  
**Date:** 2026-08-27  
**Contract owner:** Vuoro
`docs/plans/2026-08-27-effect-intent-projection.md`  
**Delivery owner:** AgentOps shared wrapper and projection surfaces  
**Pilot target:** the next separately authorized Talos control-plane upgrade

## Purpose

Two sessions can be correctly scoped and still affect each other. In the pilot,
Session A performs controlled cluster maintenance while Session B works on an
application deployed through the same cluster. GitOps and ordinary CI continue
to govern application delivery. The uncovered path is A's imperative
`talosctl` or related control-plane work: B may observe API or Flux instability
without knowing that the symptom is expected maintenance.

This plan delivers correlation, not arbitration. It does not introduce a
cluster lease, a session mutex, or a new route around native authorization.

## Ownership

| Concern | Owner |
| --- | --- |
| `ResourceRef`, graph-revision, and effect-intent projection semantics | Vuoro contract definitions |
| Wrapper adapters, bounded active view, and session-context projection | AgentOps |
| Desired state, operational runbook, and authorization for the real upgrade | appservice / cluster operator |
| Attempt and observation records | Auditctl-compatible evidence provider |
| Git, Kubernetes, Talos, and HA enforcement | Their existing native mechanisms |
| Trial acceptance and any later enforcement decision | Operator |

ActionQ remains outside this pilot. No execution lifecycle changes, durable-work
provider, or queue semantics are required.

## Observable data path

An effect-bearing wrapper records the request before execution and the receipt
after execution. Native RBAC, credentials, admission, CLI preconditions, and
operator approvals still decide whether the call may proceed. The wrapper
records only bounded operational fields: session and principal references,
tool and operation, resolved target selectors, timestamp, result class, and
evidence references. It must not capture credentials, prompt content, or a
reasoning trace.

The resolver applies one pinned `ResourceGraphRevision` to derive typed
propagation. A bounded active view combines that derivation with the session's
declared intent, phase, expected symptoms, abort conditions, and expiry. When a
consumer's planned or observed scope intersects the active propagation, AgentOps
injects the notice at the next relevant tool boundary. The notice links to
evidence and graph revision; it does not ask one model to trust another model's
narrative.

Session B should receive a notice when it queries the Kubernetes API, observes a
Flux reconciliation, or attempts a deployment whose control path intersects A's
maintenance. Merely editing local application code is not an intersection.

## Pilot slices

### 1. Wrapper inventory

List the actual imperative paths used during a control-plane upgrade and the
read or write paths B uses to assess deployment state. The initial candidates
are `talosctl`, `kubectl`, and Flux-facing operations. For each, record whether
target identity can be derived before execution and which receipt establishes
attempted versus observed effect.

Stop if a load-bearing target can only be supplied by free-form agent prose.

### 2. Graph fixture

Compile one content-addressed fixture from maintained topology and bounded live
discovery. It needs only the tested path: Talos node to etcd member and API
availability, API availability to Flux reconciliation, and Flux objects to the
application delivery surface. Each edge records source and validity. Unknown
edges stay unknown.

Reject a fixture that reduces propagation to the whole cluster without a typed
reason. That would recreate the granularity error as a notification storm.

### 3. Projection and replay

Emit an active view for a synthetic or recorded upgrade and replay B's relevant
tool sequence. Verify these cases before live work:

- expected API unavailability inside A's declared envelope is correlated;
- the same symptom after expiry is unexplained and escalates;
- etcd quorum loss exceeds the envelope immediately;
- a local-only session receives nothing;
- a stale graph revision is visible and cannot silently claim correlation.

### 4. Live falsification run

With separate operator authorization, run the next Talos control-plane upgrade
while an application session is active. A supplies the fields wrappers cannot
derive: intent, current phase, expected duration and symptoms, and abort
conditions. B receives only the derived intersection and evidence links.

Record whether B:

1. correlates the symptom without operator explanation;
2. continues when the symptom remains within the envelope;
3. escalates when the envelope is exceeded or no path explains the symptom; and
4. avoids attributing unrelated application failure to the maintenance.

The primary hypothesis fails if B still escalates the expected transient
instability as unexplained while the relevant projection and graph path are
available. Also report time to correlation, irrelevant-notice count, missing
wrapper coverage, graph staleness, and operator corrections. A null or negative
result is a completed pilot, not permission to broaden the graph.

## Delivery gates

1. The fixture and replay are reviewable without cluster credentials.
2. Attempted and observed effects remain distinguishable in stored evidence.
3. Agent-authored fields cannot create authority, prove execution, or clear an
   exceeded envelope.
4. Closure after disruptive work requires target health evidence or an operator
   decision independent of Session A's assertion.
5. Projection failure degrades to the current explicit operator escalation; it
   never changes the target's allow or deny result.
6. No A2A adapter, always-on graph service, target-side fence, or production
   rollout is included in the implementation tranche derived from this plan.

## Resulting implementation question

Only after the pilot should planning ask whether any imperative operation lacks
native conflict control. If one is found, repair or wrap that exact target
surface. If correlation works and native controls remain sufficient, the
proportionate result is the resource graph and intent projection, with nothing
new fenced.

