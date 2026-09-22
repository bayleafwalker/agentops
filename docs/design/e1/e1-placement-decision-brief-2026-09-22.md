# Where should a public read-only MCP surface be served from?

A decision brief for an external reviewer. Self-contained: no prior context assumed.
Prepared 2026-09-22.

## What you are being asked

One operator runs an agent-work substrate. A small read-only MCP surface has been
built and merged. It now has to become reachable from hosted AI runtimes. There are
two candidate estates to serve it from, and they trade off against each other in a
way the operator and I disagree about. **Which estate should serve it, and what is
the least-regret sequencing?**

Please argue against the framing if you think it is wrong.

## The system, briefly

**The substrate.** A work-coordination system ("vuoro") wrapping a sprint/work-item
authority ("sprintctl"). It holds work items, releases, claims, evidence records and
decisions. It is the authoritative record of what every automated agent has done.
Single operator, no external users, no on-call.

**Two estates exist.**

*Estate A — the homelab.* A Kubernetes cluster at the operator's home. LAN-only by
design, with remote human access over WireGuard. It co-hosts a git forge, a password
manager, a document store, an identity provider and a file-sync service. The internet
reaches it only through a Cloudflare Tunnel (outbound-dialled; no inbound firewall
rule), currently with exactly **two** deliberately published entry points, each
path-allowlisted and enforced in CI by a guard that fails the build if an unlisted
public exposure appears. **This estate holds the authoritative work data today.**

*Estate B — the hosted estate ("vuoro.cloud").* A separate single-node Kubernetes
cluster at a cloud provider. Purpose-built to be the substrate's public edge.
Already publicly reachable (two hostnames, live), already scanned by a credential
scanner within hours of going live, already hardened in response (WAF edge guard,
path-traversal fix, privilege fix). Default-deny network policy; only two workloads
accept traffic from the tunnel. Its architecture assumes **the cloud holds
coordination state** and user-owned workers poll it outbound. Its tenancy model gives
each workspace its **own** database — so a workload running there does not
automatically see Estate A's data.

**The surface itself.** Two read-only tools: list ready work, describe one work item.
Single static bearer token. No write, no claim, no effect. Deliberately composed as a
standalone app so that deleting the connector removes the public surface completely,
with no other code change.

## The written direction (what was already decided)

- The public path is **decided and accepted**: a narrow public MCP surface for
  interactive runtimes, *plus* a separately-built self-hosted worker for unattended
  runs. Both. This is not in question.
- The boundary is binding: **intent, coordination and evidence may cross** to a
  runtime the operator does not host; **effects and credentials may not.** There is
  deliberately no "apply an effect" scope, and its absence is recorded so a later
  implementer does not helpfully add one.
- A **one-month stop condition** is agreed in advance: if a month passes without the
  substrate being reached from a hosted runtime, the surface is deleted rather than
  kept warm, and the follow-on work is not built.
- Design docs name Estate B as the surface's home, but describe it by **role** ("the
  substrate's network-reachable edge"), and no document states where the surface must
  physically run.
- A separate threat-model section warns that exposing the homelab substrate
  "converts a homelab-internal substrate into an internet-reachable,
  credential-holding service with one user and no on-call" — a change in kind.

## The disagreement

**My initial recommendation was Estate A** (homelab origin, public hostname on the
hosted estate's DNS zone). Reasoning: the authoritative data is there; Estate B's
per-workspace database means a workload there would serve an *empty* workspace;
making it serve real data would need either a data migration or handing a public
workload a WAN database connection to the home network, which the boundary forbids.
Estate A also already runs the exact narrow publish pattern needed, twice, in
production.

**The operator's objection:** introducing a *third* public pathway into a LAN-only
cluster that co-hosts a password manager and a git forge — when a separate, already
public, single-purpose, default-deny estate was built precisely to be the public edge
— is backwards. Blast radius should dominate data locality.

**I now think the operator is right on posture**, and that I under-weighted two things:

1. Estate B's architecture *assumes the cloud holds coordination state*. Homelab-as-
   authority is the current arrangement, not the designed end state. So "the data is
   in the wrong place" may be describing a migration that was always implied rather
   than a constraint.
2. Blast radius asymmetry is severe. Estate A's neighbours are a password manager and
   a forge. Estate B's neighbour is nothing.

**The unrecorded question underneath it**, which neither repository answers: *is the
authoritative work record intended to move to the hosted estate, or to stay at home?*
Everything else follows from that, and it has never been written down.

## The alternatives

**1. Move the authority to the hosted estate.** The surface becomes just another
route on an estate that already holds the data. No new exposure anywhere. The
connector model works as designed.
*Cost:* a real data migration. The hosted estate's own status document names "the
absence of any tenant migration path" as an open blocker. Also moves the authoritative
record of all agent work off-site.

**2. Keep the authority at home; push data outward.** The home estate initiates an
outbound sync of ready-work to the hosted estate, which serves it publicly. No inbound
path to the home network at all.
*Cost:* a replication path, not a small change. Introduces staleness the "describe one
work item" tool would have to be honest about. Two systems holding overlapping state.

**3. Seed a workspace on the hosted estate and run the surface against it.** Cheapest
way to answer the one-month stop condition — find out whether hosted runtimes reach
for the substrate *at all* before paying for 1 or 2.
*Cost:* for that month the surface answers about seeded workspace data rather than the
operator's real work, which arguably weakens the very signal the month is meant to
collect.

**4. Serve from the home estate** (my original recommendation, now doubted).
*Cost:* a third public entry point into the cluster with the sensitive neighbours;
accepts the threat-model sentence about the perimeter itself.

## Questions

1. Which alternative, and why? Is the blast-radius argument decisive, or is data
   locality being under-weighted in the reversal?
2. Alternative 3 is meant to be the cheap falsifier — but does testing against seeded
   rather than real data invalidate the signal? If a hosted runtime does not reach for
   a *seeded* workspace, has anything been learned?
3. Is there a fifth option? Specifically: is there a way to serve real data publicly
   from the hosted estate without either migrating the authority or building a
   replication path?
4. The one-month stop condition is answered by classifying callers. With a single
   shared bearer token the credential cannot distinguish an operator's own test call
   from a hosted runtime's, so classification currently falls back to source-address
   heuristics. Is that sound enough to hang a delete-or-keep decision on, or does the
   auth design need to change before the clock starts? Note that the connector's auth
   settings are immutable after registration — changing later means remove and re-add.
5. What is being missed entirely?

## Constraints on any answer

- Single operator. No team, no on-call. Solutions requiring sustained operational
  attention are worse than they look.
- The surface must stay trivially deletable: removing the connector must remove the
  public surface completely.
- Read-only. No write, claim or effect capability may be added to answer this.
- The month-long falsification test is the point. An answer that makes the surface
  permanent-by-default defeats it.
