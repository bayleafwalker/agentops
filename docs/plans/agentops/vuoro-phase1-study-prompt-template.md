---
doc_id: vuoro-phase1-study-prompt-template
status: source-material
authored_by: operator
recorded_at: 2026-07-22
recorded_from: ~/Downloads/phase1-functional-investigation-prompt.md
---

# Phase-1 functional investigation prompt

Fill the four variables, hand the whole thing to an agent with repo access.

---

## Prompt

You are producing a phase-1 functional description of one capability of an external system, for a cross-system comparison study. The output is a behavioral specification, not an architecture document.

**System:** {SYSTEM} — {REPO_URL_OR_PATH}
**Capability under investigation:** {CAPABILITY}
**Evidence available:** {EVIDENCE — e.g. "source checkout at commit X, public docs, runnable binary"}

### Method

1. Read whatever evidence is available — source, schema definitions, tests, docs. Tests are the highest-value source: they state intended behavior directly.
2. If a runnable binary is available, execute the probe list in section F against it. Prefer observed behavior over documented behavior wherever they conflict, and record the conflict.
3. Reverse-engineer the *functionality*, not the code. Every claim in the main document must pass the substitutability test: **could a second, differently-built implementation satisfy this claim?** If a claim can only be satisfied by this codebase, it is an implementation observation and belongs in the annex.

### Prohibitions (main document only)

- No storage technology, database, or library names.
- No table, file, struct, or function names.
- No CLI flags or command syntax, unless the flag itself is the functional contract (e.g. "the operator can force a handoff without review" is functional; `--no-review` is annex).
- No inferred rationale ("presumably for performance"). State behavior; if the reason matters, mark it as an open question.

Everything excluded above goes into the **annex**, keyed to the claim it evidences.

### Claim format

Number every claim `{SYS}-{CAP}-NN` so the merge phase and roadmap can cite it. Tag each with its evidence class:

- `[code]` — read from source or schema
- `[test]` — asserted by the system's own test suite
- `[run]` — observed by executing the system
- `[doc]` — documented but not verified
- `[inferred]` — your conclusion; state the evidence chain

Example of a passing claim:
> TD-HANDOFF-03 `[code][run]` A handoff is a structured record with distinct fields for completed work, remaining work, decisions made, and declared uncertainty. Free-text handoffs are not accepted by the primary interface.

Example of a failing claim (annex material):
> Handoffs are rows in the handoffs table with FK to sessions.

### Output structure

Frontmatter: system, capability, commit SHA, evidence classes used, date, author (you), length of main doc (≤ 2 pages; annex uncapped).

**A. Purpose and boundary.** What problem this capability solves, for whom, and what it explicitly does not do. One paragraph.

**B. Entities touched.** For each entity the capability reads or mutates: does it exist as a first-class concept; is it canonical or derived; what is its identity scope (turn / session / repo / project / global); who may mutate it.

**C. Transitions.** The lifecycle as explicit state transitions. For each: is it explicit or inferred, reversible or terminal, does it require a second actor, does it emit a durable record.

**D. Authority.** Where authority over this capability's state is held; single or multiple writers; conflict handling (rejection / merge / last-write / fencing); whether stale actors can mutate; whether state is reconstructible from history. Judge the system **as shipped** — semantics inherited from a dependency count as the system's semantics.

**E. Persistence scope.** Each piece of state classified by scope (turn / session / repo / project / cluster) and lifetime (ephemeral / checkpointed / operational / historical record). Media and formats are annex material.

**F. Failure semantics.** For each probe, record observed or documented behavior; if neither is obtainable, write `UNTESTED` — do not infer. Minimum probe set, adapt to capability:
- actor terminates mid-operation
- two actors attempt the same exclusive operation concurrently
- the operation is invoked against stale state
- the durable record write succeeds but the acknowledgment fails (or vice versa)
- the underlying working copy (repo/branch) changes or disappears under the operation
- a completed operation is invalidated after the fact — what is the correction path

**G. Open questions.** Anything that could not be resolved from available evidence, phrased as testable questions.

**Annex.** Implementation observations, keyed by claim number. Consulted only during the adopt/adapt/interoperate/differentiate classification, never during primitive derivation.

### Quality bar

- Every claim numbered, tagged, and substitutable.
- No happy-path-only lifecycles: section F must have an entry for every probe.
- Where documentation and observed behavior diverge, the observation wins and the divergence is recorded as a finding.
- If the capability cannot be described without naming an implementation mechanism, say so explicitly in section G — that is a finding about the system, not a formatting failure.

---

## Example invocation

**System:** td — https://github.com/marcus/td
**Capability under investigation:** Session handoff — the mechanism by which one work session ends and a subsequent session (same or different agent) resumes with sufficient context, including any enforced separation between implementing and reviewing sessions.
**Evidence available:** source checkout (pin the commit SHA at clone time), public docs at marcus.github.io/td, runnable binary — execute the section-F probes in a scratch repo.

Suggested capability slices for the wider study, one investigation each:
- session identity and continuity (td, Beads, Vuoro/sprintctl)
- session handoff (td, Vuoro/sprintctl)
- exclusive claim / assignment (td, Beads, Vuoro/sprintctl)
- ready-work determination and dependency readiness (td, Beads, Vuoro/sprintctl)
- concurrent-edit convergence (Beads, Vuoro/sprintctl)
- knowledge claim lifecycle: creation → ratification → supersession (Graphiti, Vuoro/kctl)
- durable evidence emission at transitions (all four; reference annex: W3C PROV relation model)
