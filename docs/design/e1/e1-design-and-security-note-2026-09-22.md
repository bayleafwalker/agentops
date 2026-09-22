# E1: a narrow public read surface over an agent-work substrate

Design and security design note. 2026-09-22.
Self-contained: assumes no prior context. Written to be passed to a reviewer.

Status at time of writing: the surface module is merged but mounted nowhere and
reachable from nowhere. No connector is registered, no route exists, no public
hostname points at it. Nothing described under "Deployment" has been built.

---

## 1. What this is

A substrate records what automated agents do: work items, releases, claims,
evidence, decisions. It is the authoritative record of agent activity for a
single operator. Historically it has been reachable only from inside that
operator's home network.

A growing share of the operator's agent sessions now run in places the home
network cannot see — hosted assistant runtimes. For those sessions the record
is not merely incomplete, it is absent: the proportion of automated activity
that is reconstructable is zero.

E1 is the narrowest possible remedy: **two read-only tools, published over MCP,
behind one static credential.**

    list_ready_work   -> what work is ready to be picked up
    describe_work     -> one work item, in more detail

No write. No claim. No effect. No tool that mutates anything, anywhere.

E1 is deliberately a **falsifiable bet**, not a foundation. See §9.

---

## 2. Placement, and why it is not the obvious answer

Two estates exist.

**Estate A — home.** A Kubernetes cluster on the operator's own network,
co-hosting a git forge, a password manager, a document store, an identity
provider and a file-sync service. LAN-only by design, human access over
WireGuard. Exactly two deliberately published entry points, each path-allowlisted
and enforced in CI by a guard that fails the build when an unlisted public
exposure appears. **Holds the authoritative work data today.**

**Estate B — hosted.** A separate single-node cluster at a cloud provider,
purpose-built to be the substrate's public edge. Already publicly reachable.
Default-deny network policy; only two workloads accept tunnel traffic.
Its architecture assumes the *cloud* holds coordination state and
operator-owned workers poll it outbound.

**The surface is served from Estate B.** The first analysis in this project
recommended Estate A on data-locality grounds — the authority is there, and
Estate B's per-workspace database means a workload there serves an empty
workspace. That recommendation was wrong, for two reasons:

1. **Blast radius dominates data locality for endpoint placement.** A third
   public path into a cluster whose neighbours are a password manager and a git
   forge, in order to expose a substrate that a separate purpose-built public
   estate already exists to expose, is backwards. Estate B's neighbours are
   nothing.
2. **Home-as-authority was the current arrangement, not the designed end state.**
   Estate B's connector model is an outbound poll loop from the operator's
   network to the public API — cloud-as-authority with operator-owned execution.
   "The data is in the wrong place" was describing a migration the architecture
   always implied.

**Consequence, decided separately:** a bounded slice of real *new* work becomes
authoritative in one cloud workspace from the start. No dual-writing. Existing
history is not migrated unless the trial in §9 proves out. This avoids depending
on a record-import path that does not yet exist.

---

## 3. Trust boundary

The binding rule, inherited from the enclosing design and unchanged here:

> **Intent, coordination and evidence may cross to a runtime the operator does
> not host. Effects and credentials may not.**

Concretely, what never crosses: cluster credentials; merge rights; any token
that can write to the cluster, the registry, or protected branches of the forge.

A hosted runtime's maximum achievable outcome is an unmergeable branch and a
queued intent. There is deliberately **no effect-apply scope**, and that absence
is recorded rather than merely omitted, so that a later implementer does not
helpfully add one.

Every tool on the published surface must classify as **read, coordinate, record
or propose**. A tool that cannot be put in one of those four buckets belongs on
the private side of the boundary. Both E1 tools are `read`.

**What E1 does NOT establish.** E1 creates no record path. Evidence produced by
a hosted runtime remains absent rather than late. The property the wider design
seeks — a verifiable chain from a signed commit back to a run record naming
runtime, model and profile — is **recorded and reconstructable, not attested**,
and must not be described as attestation.

---

## 4. Authentication

**One static bearer token.** Chosen deliberately over OAuth: for a single
operator, standing up an authorization server buys identity that is already
known, while the token *scoping* — where the design content actually lives —
works identically either way.

Registration is a custom connector with **no sign-in** plus a **request header**
carrying the credential (confirmed available on the operator's account,
2026-09-22).

**Two properties of that arrangement matter for security review:**

1. **The client will connect without credentials.** Selecting "no sign-in" means
   the vendor makes no client-side requirement that the header be present, and
   the dialog offers no way to mark it required. **Enforcement therefore rests
   entirely on the server's own 401.** The bearer check is a single point of
   enforcement and is treated accordingly.
2. **Connector auth settings are immutable after registration.** A wrong first
   choice costs a remove-and-re-add. Consequently the surface accepts the bearer
   from either the standard `Authorization` header or a configurable alternate
   header name, so that the registration-time choice is not load-bearing.

**Audience validation.** Under a static bearer there is no audience claim to
validate. The property audience validation buys is obtained by construction
instead: the token is unique to this surface and used nowhere else, so it cannot
be replayed against another service. This is stated rather than ticked.

**Token labelling.** More than one token may be issued — in practice one for the
hosted client and one used only for operator probes. This is not a
defence-in-depth measure; it exists so that the trial in §9 can attribute calls.
See §9.

---

## 5. Threat model

**The hosted runtime holds all three legs of the classic trifecta**: it reads
untrusted repository content, it holds a credential to the substrate, and it has
network egress. This cannot be remedied by removing a leg. It is mitigated by
making the credential worth as little as possible — read scope only, no effect
scope, short-lived where possible — so that an attacker who fully compromises a
session gets to make a mess of a work queue and propose intents the operator
sees before they execute.

**The hosting estate is already exposed, and has already been found.** Within
hours of its public routes going live, a cloud-hosted scanner swept both
hostnames, requested several hundred credential paths, and successfully read an
unauthenticated metrics endpoint and an OpenAPI document. That prompted
same-day remediation: a path-traversal fix, a privilege fix, and an edge WAF
rule. This history is the reason the surface is treated as internet-facing from
the first line of code rather than as an internal service that happens to be
routable.

**The most likely failure is misconfiguration, not attack.** A mis-mounted or
mistyped credential produces a stream of 401s. Unless those are recorded, that
state is indistinguishable from "nobody came" — and would be read as evidence to
delete the surface. See §9.

**Prompt injection is in scope and is only partly mitigable.** Work-item text is
authored by humans and agents and is placed into a hosted model's context. It
can act as instructions to that model, which may hold tools the substrate
neither controls nor can see.

---

## 6. Disclosure controls

An audit of the real corpus found that internal work-item bodies contain, in
routine items: internal hostnames, absolute filesystem paths, credential and
bucket names, an unremediated security finding stated as an exploit, and
runnable command lines. Acceptance sections alone — median a few hundred
characters — carried several of each.

**The control is field selection, not content filtering.**

- The adapter **never parses internal description bodies.** The pilot workspace
  authors external-facing fields from the start; anything not authored for
  external consumption is not emitted. The fallback, if such a field cannot be
  carried, is to emit identifier and title only.
- Fields with no faithful external mapping are **not emitted at all**, rather
  than transformed.

**Mitigations deliberately NOT built, with reasons** — this matters more than
the list of what was:

| Rejected | Why |
|---|---|
| Stripping imperative phrasing | Imperative constructions appear across dozens of *legitimate* items. A filter mangles real content while an attacker rephrases declaratively. |
| Delimiting / fencing untrusted text | Requires the *consuming* model's system prompt to honour the convention. The substrate neither controls nor can verify that. |
| HTML/JSON escaping as injection defence | The consumer is a language model, not a renderer. |
| Secret-keyword denylists | The actually-sensitive strings in the corpus are ordinary hostnames and bucket names matching no secret-shaped pattern. |

A content-warning envelope may be included as a hint. **It must never be counted
as the mitigation.** The only control the substrate owns is which bytes it emits.

---

## 7. Deployment and removability

The surface is deployed as its **own removable unit** — own namespace, own
tunnel, own image — rather than folded into an existing workload. It is composed
as a standalone application: nothing in the main service references it, so its
deletion is complete rather than partial.

**The kill switch must be tested, not asserted.** Removing a vendor-side
connector registration does *not* stop a running server: the route, the workload,
the credential and any exported data all continue to exist. Removal is therefore
a defined, ordered procedure over all of those, with a test that proves the
endpoint is closed afterwards.

**That test needs a positive control**, because a removal test that passes
against an already-closed endpoint proves nothing, and — critically — a probe
that fails for *any* reason (typo'd hostname, missing binary, expired credential,
a sandboxed call returning empty) will report "closed". The control therefore
proves the probe can observe an *open* endpoint before it is trusted to report a
closed one.

---

## 8. Checks that cannot fail

This estate has repeatedly produced checks whose green state was structurally
guaranteed: a redaction processor whose test never fed it anything to redact; a
stop-condition that passed because its precondition was absent so the code path
never ran; a permission check that passed because no object existed to check.

A design review of this work catalogued **thirteen** such signals in the E1
design and its first implementation. Examples, stated generally:

- A trial clock that arms on first use — so if nobody ever calls, the clock never
  starts, the trial never elapses, and the surface survives *by* the absence it
  exists to detect.
- A demand counter incremented only on successful calls — so an outage converts
  real demand into silence, and the surface is deleted on evidence produced by
  its own downtime.
- An empty allowlist that causes every caller to classify as external — biasing
  the outcome toward keeping the surface.
- A digest-pin validator that filters by workload name, so a workload named
  outside the list is never checked and the validator exits successfully having
  examined nothing.
- Auth failures recorded nowhere, so the most likely misconfiguration produces
  the exact signature of no traffic.

**The rule adopted: every guard is forced into its failure case before it is
trusted.** Point the pin at a wrong digest and confirm non-zero exit. Start the
application with an empty allowlist and confirm it refuses. Drive the demand
counter to one and back to zero before the trial starts. *A guard that has never
rejected anything is not known to work.*

This applies to tests as well as to runtime guards: every test written for this
work is proved falsifiable by breaking the code it covers, capturing the failure,
and reverting. Two defects found this way had passed human and automated review:
a distinguishability digest that covered only one of seven composed fields, and a
test asserting an outcome value that belonged to no category and therefore
exercised nothing.

---

## 9. The falsifier

**Stop condition, agreed in advance:** if a month passes with no case of the
substrate being reached from a hosted runtime, the surface is **deleted**, and
the follow-on work is not built. The default is deletion, not retention.

For that to be answerable rather than merely remembered:

- **Setup and trial are separate phases with separate clocks.** Calls made by the
  operator to prove the deployment works are recorded in full but counted apart.
  A failed setup call is an integration failure, not evidence of no demand.
- **The phase defaults to setup.** A journal that began in trial by accident
  would silently start a month nobody meant to start.
- **Demand is an authenticated invocation, not a success.** A backend failure on
  the server's side still counts: whether the substrate answered says nothing
  about whether anyone wanted it. Caller errors and auth failures do not count,
  but are recorded.
- **Callers are attributed by token label where available**, falling back to
  network origin. A single shared credential cannot distinguish an operator's own
  probe from a hosted runtime; labels can.
- **An unattributable call classifies as unknown, never as external.** A guess is
  not an answer.
- **Counters must survive a restart.** In-process counts die on any redeploy,
  which would read as "no demand". A durable read path is required before the
  clock starts.
- **The month-end review is scheduled with its default written down.**

---

## 10. Residual risks, stated plainly

1. **Prompt injection is mitigated by field selection only.** If the pilot
   workspace ever carries free text authored for internal use, the mitigation is
   gone. This is a process dependency, not a technical control.
2. **A single credential is a single point of failure**, and the client makes no
   client-side requirement that it be sent. Server-side enforcement is the whole
   of the control.
3. **Attribution by network origin is heuristic** and degrades if the operator's
   own network address changes. Raw origin is logged so the decision can be
   re-derived rather than trusted from a counter.
4. **The trial reads a bounded slice of real work, not the whole record.** A
   negative result is therefore weaker evidence than it appears: it may indicate
   the slice was uninteresting rather than that the capability is unwanted.
5. **The hosting estate's own acceptance gates remain open** — restore drill,
   tenant isolation, external onboarding, canary. The surface is being added to
   an estate that is publicly exposed ahead of its own release criteria.

---

## 11. Deliberately not built

Mounting into the main application; a traffic-triggered trial clock; any
effect-apply scope; emission of fields with no faithful external mapping;
content-filtering injection defences; a second environment; per-tool dashboards;
migration of existing history; dual-writing across estates; an authless connector
as a substitute if header auth were unavailable.

Each was considered and rejected for a reason recorded above or in the project's
decision log.
