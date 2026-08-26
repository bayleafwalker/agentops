# Spec row — V6-K: `human_turns`

This is the whole specification. It is given to an independent oracle author who has no
implementation to look at, per handover Rule 5.

**Revision 2 (2026-08-26)** — revised after the revision-1 oracle author's ambiguity report, which
found one defect that would have shipped a field nothing reads (§E below) and five underspecified
points. Changes are marked **[r2]**.

## Seam

`templates/dispatch/hooks/log-session-cost.sh` — the Claude Code Stop hook. It reads the session
transcript (JSONL, one object per line) and appends a single JSON object to the cost log. The log
path is overridable with `AGENTOPS_COST_LOG` (T-1). The same function also publishes a subset of
that record to auditctl as a `workflow.session` event, built from an **explicit key list**.

The hook already emits a field named `turns`, computed as the number of transcript rows where
`.type == "user"`, `.isMeta != true`, and whose `.message.content` array carries no element with
`.type == "tool_result"`.

## Rationale — why a second field, and not a fix to the first

`turns` was documented as counting *human prompts into the session*. It does not. Measured against
one real transcript, 16 `turns` decomposed into 5 genuine human prompts, 9 harness-injected
background-task completion notices, 1 slash-command artifact, and 1 interruption marker. Every
downstream ratio built on `turns` is therefore inflated.

`turns` is **not** being corrected in place: existing scorecard rows and the cockpit read it, and a
silent change of meaning is worse than a wrong number with a stable definition. The fix is an
additional field with an honest definition, leaving `turns` behaviourally identical.

## Requirement

Add exactly one field, `human_turns`, to the JSON object the hook emits, **immediately after
`turns`** **[r2 — position was previously unstated]**.

`human_turns` counts transcript rows that satisfy the existing `turns` predicate **and** are
genuine human input.

### Deciding whether a row is human **[r2 — rewritten; revision 1 said only "begins with"]**

1. Collect the row's **text elements**: if `.message.content` is a string, that string is the only
   element; if it is an array, the `.text` value of each element whose `.type == "text"`, in order.
   If `.message.content` is anything else — absent, null, a number, an object — the row has **no**
   text elements.
2. Discard every text element that, ignoring leading whitespace, **begins with** any of:
   - `<task-notification>` — a background subagent completion, injected by the harness
   - `<command-name>`, `<command-message>`, `<command-args>` — slash-command plumbing **[r2]**
   - `<local-command-stdout>`, `<local-command-caveat>` — slash-command output **[r2]**
   - `<system-reminder>`
   - `[Request interrupted` — an interruption marker (a prefix, deliberately unclosed)
   - `This session is being continued from a previous conversation` — the compaction notice
3. The row is **human input** when what remains, joined together, contains at least one
   non-whitespace character. Otherwise it is not.

**Why discard-then-check, rather than testing only the first element [r3 — rationale corrected]:**
revision 2 justified this by asserting that the harness appends `<system-reminder>` blocks to
genuine human turns. **That claim was not supported when checked.** Across four real transcripts,
184 `turns`-eligible text elements contained `<system-reminder>` zero times, at the start or
anywhere else — those blocks do not appear in `turns`-eligible user rows at all. Discard-then-check
is retained anyway, on the weaker and honest ground that it is no more expensive than the
alternative and degrades more gracefully if the harness shape changes. It changes no measured
number today: all three candidate readings yield 5 in the T-series window and 15 across the full
session.

**Marker matching is per-element and prefix-only, deliberately [r3].** An element that *begins*
with a marker is discarded whole. No attempt is made to find a marker's closing tag and keep text
after it. A single element containing a marker block followed by real human text would therefore be
discarded — measured occurrences of that shape: zero. Block-matching is a materially larger rule
and is not bought by the evidence.

**Whitespace means jq's `\s` [r3]** — Unicode-aware, not `[ \t\n\r]`. Both "ignoring leading
whitespace" and "at least one non-whitespace character" are defined against it, because the
implementation is jq and harness artefacts are exactly where exotic spaces land.

### Reaching auditctl **[r2 — this whole subsection is new; see §E]**

`emit_record` builds the auditctl `--metadata` blob from an explicit key list. `human_turns` must
be added to that list, so the field reaches the audit store as well as the cost log.

Without this the packet ships a field that nothing downstream can read, since every consumer named
in the rationale reads either the cost log or the audit store. This is still one writable file and
one outcome: the key list lives in `log-session-cost.sh` alongside the record itself.

## Acceptance properties

| id | requirement | fails when |
|---|---|---|
| REQ-001 | `human_turns` is present in every record the hook writes to the cost log, including the zero record written when no transcript exists | the field is absent from any emitted record |
| REQ-002 | `human_turns` counts genuine human prompts only, per the three-step rule above | a transcript containing harness-injected rows of any listed kind yields a `human_turns` that includes them |
| REQ-003 | `turns` is unchanged **behaviourally** — the worker may restructure the jq freely so long as the value is identical for every transcript **[r2 — was ambiguous between source and behaviour]** | `turns` differs, for any transcript, from the value the current predicate produces |
| REQ-004 | every other field keeps its name, relative order and type; `human_turns` appears immediately after `turns` **[r2]** | any pre-existing field is renamed, removed, reordered or retyped, or `human_turns` appears elsewhere |
| REQ-005 | `human_turns` never exceeds `turns` | a transcript yields `human_turns > turns` |
| REQ-006 **[r2]** | the auditctl `--metadata` key list includes `human_turns` | the metadata blob the hook publishes omits it |

## Non-goals

- Changing `turns` itself.
- Restating §2b or the D-9 falsifier against the new field — a later coordinator pass.
- The PostToolUse gate hook, the `/friction` skill.
- **[r2]** Changing *how* auditctl is invoked, its `--type`, its `--summary` line, or its failure
  handling. Only the metadata key list is in scope.
- Subagent transcripts, or any spend accounting (a separate, undecided question).
- Anything outside `templates/dispatch/hooks/log-session-cost.sh`.

## Notes for the oracle author

- Write the test at `templates/dispatch/hooks/tests/test-human-turns.sh`, following the shape of
  the sibling tests in that directory (`test-cost-hook-fields.sh` is the closest).
- The test must construct its own transcript fixtures and point the hook at a temp log via
  `AGENTOPS_COST_LOG`. It must not depend on any real session transcript.
- **Pin `AUDITCTL_ARTIFACTS_ROOT` into your temp directory.** `auditctl` is installed on this host,
  so an unpinned run writes real `workflow.session` events into the live audit store.
- The test must currently **fail** — the field does not exist yet. Its failure must be a clean
  assertion failure naming the missing field, not a crash.
- Report any ambiguity you find in this spec. On the last five packets the oracle authors'
  ambiguity reports were worth more than their tests.

## What this field is not, and must be documented as **[r3]**

`human_turns` is a **lower bound on human prompts, not a count of them.** The rule is a prefix
inventory with no escape hatch, so a genuine human prompt that legitimately begins with one of the
listed strings — quoting `<system-reminder>` in a question *about* system reminders, pasting
`[Request interrupted` to ask what it means — is silently uncounted. This is unavoidable with a
prefix rule and is not testable.

**It must be stated wherever the field is documented.** This packet exists because a field's
documented meaning did not match its behaviour; shipping a second field with an unstated
limitation would repeat exactly that. The implementer is not asked to solve it — only not to
describe `human_turns` as "the number of human prompts" in any comment they write.

## Deliberate scope calls, recorded so they are not discovered later **[r3]**

- **The auditctl `--summary` line still reports the inflated `turns`.** REQ-006 puts `human_turns`
  into the metadata blob, which is what queries read, but the human-readable summary string is an
  explicit non-goal. Anyone reading audit summaries rather than querying metadata continues to see
  the old number. Accepted for this packet; it belongs with the §2b restatement.
- **REQ-006 pins presence and value, not position**, unlike REQ-004 which pins position in the cost
  record. The asymmetry is intentional: the metadata blob is a JSON object whose consumers key by
  name, whereas the cost record's key order is part of the T-1 backward-compatibility contract.
- **`turns` is not hardened against object-shaped content.** The existing predicate
  `[.message.content[]? | select(.type == "tool_result")]` raises `Cannot index number with string`
  on a row whose `content` is an object with scalar values — verified directly — and under
  `set -euo pipefail` that kills the Stop hook and costs the session its row entirely. Measured
  occurrences across all 179 transcripts on this host: **zero**, so it is latent, not active, and it
  is *not* the cause of the resume truncation in Finding D. Adding a type guard would change
  `turns`' behaviour on that shape from crash to counted, which REQ-003 forbids. It is therefore out
  of scope here and carried as a debt line. **`human_turns`' own extraction must not inherit the
  landmine**: step 1 requires an explicit type check, so a non-string, non-array content shape
  yields no text elements rather than an error.

## Known limits of this oracle — recorded, not delegated **[r2]**

The revision-1 author correctly noted that a test forbidden from reading real transcripts can only
check the implementation against the same six prefixes it codes to, so **a green oracle does not
establish that the number is right on real sessions.** That assurance is the coordinator's to
produce, not the oracle's: at receipt time the finished hook is run against the real transcripts
already measured for Finding A, and the receipt records whether it reproduces 5 human turns in the
T-series window and 15 across the full session. Do not attempt to cover this in the test.
