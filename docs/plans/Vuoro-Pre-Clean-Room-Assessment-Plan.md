# Vuoro Pre-Clean-Room Assessment Plan

## Purpose

Determine which parts of the current Vuoro workflow are:

1. operationally necessary;
2. valuable but unnecessarily elaborate;
3. compensatory machinery for current environment constraints;
4. weakly used or obsolete;
5. candidates for external substitution.

This assessment does **not** compare Vuoro with `td` or other products. Its purpose is to prevent the clean-room exercise from treating every current Vuoro behaviour as a requirement merely because it already exists.

The output should be a reduced, evidence-backed functional requirement set against which Vuoro and external tools can later be compared.

---

## Starting assessment

The current evidence supports the following working position:

* `sprintctl` appears to contain a valuable execution-memory and session-resumption kernel.
* `kctl`, `auditctl`, and `actionq` have distinct intended roles and should not be presumed redundant.
* Vuoro solves a real cross-machine authority and workflow-serving problem.
* The system is highly adapted to one operator’s agent-assisted workflow.
* The cost of that adaptation is visible in schema maintenance, reconciliation, compatibility work, and cross-repository evolution.
* Existing evidence does not show whether those costs exceed the context-reconstruction, continuity, discovery, and safety value produced.
* The recent served-substrate migration is not representative of steady-state maintenance and must be analysed separately.
* `kctl` appears more likely to need decay and promotion policy than semantic removal.
* The claim that an external tool could provide “80%” remains untested and belongs to the later clean-room exercise.

The assessment should therefore test **value, necessity, and compression**, not replacement.

---

# Research questions

## RQ1 — What is the actual valuable kernel?

Which Vuoro semantics repeatedly change a consequential decision involving:

* what work is selected;
* who or what owns it;
* whether execution may proceed;
* how interrupted work is resumed;
* whether an action is accepted;
* how an unsafe or failed state is recovered?

A semantic that changes one of these decisions is presumptively valuable.

A semantic that is mostly written, rendered, transported, reconciled, or displayed without affecting a later action is a compression candidate.

## RQ2 — What reconstruction work does Vuoro avoid?

Measure the cost of resuming work with Vuoro against reconstructing the same state from:

* Git history;
* branches and worktrees;
* planning documents;
* agent transcripts;
* open pull requests;
* test and deployment state;
* personal memory.

The relevant comparison is not Vuoro maintenance versus zero. It is:

> capture and maintenance cost versus reconstruction and forgotten-state cost.

## RQ3 — What discovery value does explicit state produce?

Determine whether reconciliation and review processes surface:

* missing work;
* unstated dependencies;
* stale assumptions;
* incomplete implementation;
* unverified deployment claims;
* conflicting ownership;
* forgotten decisions.

Distinguish useful discovery from merely correcting metadata that had no downstream consequence.

## RQ4 — Where does process expressiveness become excess?

Identify states, fields, transitions, event types, review stages, and evidence requirements that:

* are rarely consumed;
* do not affect decisions;
* duplicate information available elsewhere;
* exist mainly because another Vuoro component expects them;
* require disproportionate maintenance;
* could be replaced by a simpler default or lossy representation.

## RQ5 — What is essential complexity versus architectural tax?

Separate complexity caused by real constraints from complexity caused by the system’s shape.

Real constraints include:

* trust separation between devbox and workstation;
* restricted production access;
* resumable unattended agent work;
* concurrency and claim ownership;
* durable audit requirements;
* offline or disrupted operation.

Architectural tax includes:

* compatibility work caused by unnecessary shared semantics;
* duplicated projections;
* cross-repository changes for presentation-only features;
* state transitions whose meaning is not operationally used;
* maintenance of interfaces with no active consumers.

---

# Scope

## Included

* `sprintctl`
* `kctl`
* `auditctl`
* `actionq`
* `actionq-dispatch`
* Vuoro service and client boundaries
* agentops/cockpit only as consumers and operator surfaces
* appservice changes directly required by Vuoro deployment
* representative consumer repositories

## Excluded

* external product comparison;
* feature-by-feature comparison with `td`;
* product-market or multi-user requirements;
* speculative future agent-runtime capabilities;
* work performed only to publish or market the ecosystem;
* conclusions based solely on repository size, commit count, or number of components.

---

# Observation period

Use a representative 30–60 day operating window.

Do not artificially exercise unused features merely to generate data. The goal is to observe the normal workflow, including occasions when Vuoro is bypassed.

Divide changes into two datasets:

### Steady-state dataset

Normal use, defect correction, workflow adaptation, and small feature evolution.

### Migration dataset

The served-substrate transition, including:

* client/service split;
* domain adapters;
* authority migration;
* transport protocols;
* credential handling;
* deployment and compatibility work.

Analyse the migration separately. Otherwise it will dominate the results and make the study conclude, with great sophistication, that distributed-system migrations involve plumbing.

---

# Workstream 1 — Semantic inventory

Create an inventory of every meaningful workflow semantic.

Examples:

* sprint status;
* work-item status;
* claims;
* claim tokens;
* handoffs;
* dependencies;
* refs;
* decisions;
* notes;
* takeup and release;
* runtime session identity;
* worktree and branch metadata;
* knowledge candidates;
* approval and publication;
* coordination knowledge;
* audit events;
* queue actions;
* action lifecycle;
* session heartbeats;
* acceptance and ratification;
* evidence receipts.

For each semantic, record:

| Field                        | Meaning                                                 |
| ---------------------------- | ------------------------------------------------------- |
| Owner                        | Repository or domain that owns it                       |
| Producers                    | Humans, agents, hooks, services                         |
| Consumers                    | Commands, agents, cockpit, automation                   |
| Authority effect             | Whether it changes authoritative state                  |
| Decision class               | Execution, recovery, authorization, acceptance, none    |
| Write frequency              | How often it is produced                                |
| Consequential read frequency | How often it changes a later action                     |
| Reconstruction alternative   | Where the information could otherwise be recovered      |
| Loss consequence             | What fails if the semantic disappears                   |
| Maintenance burden           | Schema, migration, documentation and compatibility cost |
| Maturity                     | Stable, provisional, internal                           |
| Preliminary disposition      | Retain, simplify, decay, demote, remove, investigate    |

### Important distinction

Measure **consequential consumption**, not raw reads.

A cockpit polling a field every two seconds does not make it valuable. A claim identifier used once to prevent two agents editing the same worktree may be highly valuable.

---

# Workstream 2 — Session reconstruction experiment

Sample 10–20 real session resumptions across projects and complexity levels.

For each session, record:

1. time required to understand current state using Vuoro;
2. commands and surfaces used;
3. missing or misleading information;
4. what decision was made next;
5. whether the state prevented duplicated or incorrect work.

Then reconstruct the same state without using Vuoro’s live projections, using only ordinary project evidence.

Measure:

* time to reach equivalent confidence;
* number of sources inspected;
* unresolved ambiguity;
* incorrect initial assumptions;
* decisions or dependencies that were missed;
* whether another agent could reproduce the reconstruction.

Do not disable Vuoro during active high-risk work. The counterfactual can be performed retrospectively against a snapshot.

### Output

Produce a per-session comparison:

```text
Project:
Session type:
Vuoro-assisted resume time:
Manual reconstruction time:
Confidence difference:
Important information available only through Vuoro:
Information Vuoro presented but did not affect action:
Errors or ambiguities:
```

The goal is to quantify the main benefit `sprintctl` claims: deterministic context reconstruction.

---

# Workstream 3 — State economics

Estimate both sides of the ledger.

## Costs

Track effort spent on:

* entering or correcting workflow state;
* reconciliation;
* stale status repair;
* schema migrations;
* compatibility layers;
* projection and rendering maintenance;
* cross-repository contract changes;
* documentation alignment;
* repairing misleading resume state;
* maintaining unused surfaces.

## Benefits

Track:

* reconstruction time avoided;
* duplicated work prevented;
* interrupted sessions successfully resumed;
* agent handoffs completed without re-analysis;
* conflicts or ownership errors prevented;
* missing work discovered;
* stale plans retired;
* hidden dependencies surfaced;
* unsafe actions blocked;
* recovery procedures enabled.

Use rough time bands rather than fake precision:

* under 5 minutes;
* 5–15 minutes;
* 15–60 minutes;
* 1–4 hours;
* more than 4 hours.

Record confidence and evidence for each estimate.

### Evaluation unit

Use individual workflow incidents rather than aggregate sentiment.

Example:

```text
Incident: resumed interrupted implementation after agent context loss
Vuoro cost: claim and notes recorded during original session, approximately 3 minutes
Vuoro benefit: avoided branch, test and plan reconstruction, estimated 20–40 minutes
Confidence: medium
Evidence: resume output, Git state, session transcript
```

---

# Workstream 4 — Change-origin analysis

Classify the last 50 representative ecosystem changes.

Use these categories:

1. **External-workflow pain**
   Added because working on another project became unnecessarily difficult.

2. **Essential environment constraint**
   Required by trust boundaries, multi-host execution, recovery, security, or authority.

3. **Defect correction**
   Existing intended behaviour did not work correctly.

4. **Process-semantic expansion**
   Added a new state, transition, evidence class, or workflow distinction.

5. **Vuoro-induced maintenance**
   Required because an existing Vuoro contract, projection, migration, or boundary changed.

6. **Platform migration**
   Part of moving machine-local authority into the served substrate.

7. **Operator surface**
   Cockpit, reports, display, convenience or visibility changes.

8. **Speculative capability**
   Built in advance of observed workflow demand.

For each change, record:

* triggering incident;
* repositories touched;
* implementation effort;
* downstream consumers;
* whether a simpler workflow change was considered;
* whether the change has since been consequentially used.

### Key test

For every externally triggered feature, ask:

> Could the pain have been resolved by automating the step, removing the step, or accepting the step?

Vuoro has a natural bias toward automation. The study should give deletion and tolerance an explicit hearing.

---

# Workstream 5 — Architectural blast radius

Select two groups of changes.

## Group A: semantically trivial changes

Examples:

* optional display metadata;
* read-only filtering;
* label or summary changes;
* a new non-authoritative event attribute;
* altered cockpit presentation;
* retry or expiry configuration;
* a new knowledge category.

## Group B: inherently difficult changes

Examples:

* claim-proof transport;
* authority migration;
* credential handling;
* offline recovery;
* human-only ratification;
* cross-host lease semantics.

For each change, record:

* repositories modified;
* contracts modified;
* schemas or migrations added;
* deployment changes;
* tests updated;
* documentation updated;
* rollout and rollback requirements.

### Interpretation

* Broad impact for Group B may be essential complexity.
* Broad impact for Group A indicates architectural gravity or excessive contract exposure.
* Narrow impact for both suggests the ownership boundaries are working.
* Narrow Group A and broad Group B is the expected healthy pattern.

---

# Workstream 6 — kctl decay experiment

Do not begin by removing coordination semantics.

Introduce or simulate a retention policy:

* coordination candidates expire after a defined period;
* repeated patterns remain eligible for promotion;
* high-severity, recovery-related, or operator-promoted events bypass expiry;
* published durable knowledge remains unaffected.

Test several policies retrospectively:

* 14-day expiry;
* 30-day expiry;
* expire unless repeated twice;
* expire unless tied to a failed execution or operator intervention.

Measure:

* percentage of candidates expired;
* percentage later found useful;
* repeated patterns retained;
* review burden reduced;
* important knowledge lost;
* number of published entries that changed later behaviour.

### Decision

Distinguish:

* useful semantic with poor retention policy;
* useful semantic with excessive lifecycle ceremony;
* semantic that should not exist.

---

# Workstream 7 — Cockpit assessment

Treat cockpit as a consumer, not as evidence that the underlying semantics are valuable.

For each cockpit pane or interaction, record:

* frequency of use;
* decisions made from it;
* whether the same decision could be made faster from CLI output;
* whether the pane combines sources in a way no single CLI provides;
* whether stale or partial data has caused confusion;
* whether the interface is operational, diagnostic, or merely illustrative.

Classify each surface as:

* operationally necessary;
* useful convenience;
* replaceable projection;
* misleading;
* unused.

The likely result may be that cockpit should become a thinner state projection rather than a central operating interface, but that should be demonstrated rather than assumed.

---

# Serving-boundary admission policy

Apply the assessment while the served-substrate work proceeds.

Every operation should be classified as:

## Stable

Eligible when it repeatedly affects:

* execution;
* recovery;
* authorization;
* acceptance;
* durable responsibility.

Requires:

* named owner;
* real consumers;
* compatibility policy;
* migration and deprecation path;
* recovery semantics;
* evidence of consequential use.

## Provisional

For plausible but insufficiently proven semantics.

Properties:

* explicitly unstable;
* limited compatibility guarantee;
* usage and decision-effect telemetry;
* review or expiry date;
* clear promotion criteria.

## Internal

For projections, UI metadata and implementation details.

Properties:

* non-authoritative;
* rebuildable;
* no compatibility promise;
* cannot authorize transitions.

This lets serving continue without granting every current semantic permanent constitutional status.

---

# Scoring model

Score each semantic from 0–3 on six dimensions.

| Dimension                   | 0          | 1                  | 2                        | 3                                       |
| --------------------------- | ---------- | ------------------ | ------------------------ | --------------------------------------- |
| Decision impact             | None       | Convenience        | Sometimes changes action | Regularly controls consequential action |
| Recovery value              | None       | Minor context      | Useful in interruption   | Essential to safe recovery              |
| Reconstruction cost avoided | Trivial    | Under 10 min       | 10–60 min                | Over 1 hour or materially unreliable    |
| Discovery value             | None       | Occasional cleanup | Finds meaningful gaps    | Repeatedly prevents missed work         |
| Maintenance cost            | Negligible | Small              | Recurring                | High/cross-system                       |
| External substitutability   | Commodity  | Mostly available   | Partial                  | Highly specific                         |

Do not calculate a single automatic total. Use the dimensions to support an explicit disposition.

Recommended dispositions:

* **Retain and stabilize**
* **Retain as provisional**
* **Simplify**
* **Add decay**
* **Demote to projection**
* **Replace with external source**
* **Remove**
* **Insufficient evidence**

---

# Required outputs

## 1. Semantic register

One row per state, transition, field, event or operation with evidence and recommended disposition.

## 2. Workflow economics report

A balanced account of:

* Vuoro maintenance cost;
* reconstruction avoided;
* discovery value;
* recovery and safety value.

## 3. Architecture-tax report

Separate analysis for:

* steady-state changes;
* served migration;
* trivial versus inherently difficult changes.

## 4. kctl retention recommendation

A tested decay and promotion policy, including estimated loss and review-burden reduction.

## 5. Cockpit disposition

Per-surface recommendation:

* retain;
* redesign;
* replace with CLI or generated view;
* remove.

## 6. Reduced workflow specification

This is the handoff into the clean-room exercise.

It should contain only requirements that survived the assessment.

Each requirement should include:

```text
Requirement:
Problem solved:
Evidence of repeated use:
Consequence if absent:
Minimum acceptable behaviour:
Current Vuoro implementation:
Implementation details that are not requirements:
Maturity:
```

## 7. Open hypotheses

Keep unresolved propositions explicit, particularly:

* whether an external planner can provide approximately 80%;
* whether claim semantics need to live in the planner or in a narrow coordination adapter;
* whether knowledge extraction belongs in the work system or downstream;
* whether audit should remain repo-local;
* whether cockpit has any unique operational role.

---

# Decision gates

## Gate 1 — Kernel definition

Proceed when there is an evidence-backed list of semantics considered essential to execution, recovery, authorization or acceptance.

## Gate 2 — Compression decisions

Proceed when low-value semantics have been marked for decay, simplification, demotion or removal.

Actual implementation can occur later; the requirement set must no longer assume they survive.

## Gate 3 — Migration normalization

Proceed when served-substrate migration work has been separated from estimated steady-state operating cost.

## Gate 4 — Counterfactual established

Proceed when there is at least a small but representative sample comparing Vuoro-assisted resume with manual reconstruction.

## Gate 5 — Clean-room input frozen

Freeze the reduced workflow specification before studying external tools in detail.

This avoids modifying the requirements to favour either Vuoro or a promising competitor during comparison.

**Status note (2026-07-23):** the external shortlist review was conducted
while the spec was one blocker (the five timed resume observations) short
of freeze. To preserve the gate's intent, the spec text committed
2026-07-23 is the recorded baseline; until freeze it may change only in
response to evidence from the resume observations (and H9), never in
response to candidate capabilities or gaps; and the shortlist's coverage
scores are recorded in the comparison plan as dated priors, judged by
whether hands-on testing confirms or overturns them.

---

# Relationship to the clean-room exercise

The two exercises answer different questions.

## This assessment

> Which workflow capabilities are actually worth preserving?

It produces the reduced workflow specification.

## Clean-room comparison

> Which system or combination of systems best provides those retained capabilities?

The 2026-07-23 external-candidate shortlist review established that no
single reviewed tool covers all five differentiators (proof-bearing claims,
transfer/recovery, conflict-detecting resume, fenced execution,
trust-separated authority); the market splits them across product classes,
so the credible alternative is a composed stack. The comparison is
therefore structured by **ownership boundary** (work registry, claim
authority, semantic resume, execution queue, sandbox boundary, knowledge
distillation, operator projection, cross-machine authority), not product
by product, and runs in five lanes:

* Lane 0 — minimized control: `td` (can claim authority and execution
  governance simply be removed?);
* Lane 1 — closest market substitute: Beads + Gas Town (mandatory);
* Lane 2 — decomposed hybrid: Beads + minimal Restate claim/resume adapter;
* Lane 3 — execution substitution: existing work authority + Windmill +
  Daytona;
* Lane 4 — durable-execution reference: Temporal spike (calibration, not
  presumed winner).

See `Vuoro-Clean-Room-Comparison-Plan.md` for lane protocols, the standard
batch scenario, the R2 litmus test (prevented conflicting mutation vs
recorded assignment), recorded priors, and exclusions (LangGraph, OpenAI
Agents SDK, standalone sandboxes).

Internal utilization evidence must not be presented as proof that Vuoro should continue implementing a feature. It only establishes whether the capability belongs in the requirement set.

Conversely, external product coverage must not determine whether a workflow distinction is valuable. A useful requirement remains useful even when no existing product provides it.

---

# Recommended execution order

1. Build the semantic inventory.
2. Start passive instrumentation and incident logging.
3. Run the session-reconstruction sample.
4. Classify representative changes, excluding the served migration.
5. Analyse trivial and difficult blast-radius cases.
6. Run the retrospective kctl decay experiment.
7. Assess cockpit surfaces.
8. Produce the balanced workflow-economics report.
9. Decide semantic dispositions.
10. Freeze the reduced workflow specification.
11. Begin the clean-room descriptions and comparison.

---

# Success criterion

The assessment succeeds when the clean-room exercise can evaluate Vuoro and external tools against a requirement set that is:

* smaller than the current implementation surface;
* grounded in observed workflow value;
* explicit about trust and environment constraints;
* neutral about implementation;
* honest about both maintenance cost and reconstruction avoided;
* clear about which semantics are stable, provisional, or expendable.

The intended result is not necessarily a smaller Vuoro.

It is a situation where every retained piece of Vuoro can answer:

> What consequential decision, recovery path, authority boundary, or repeated reconstruction cost justifies this semantic?
