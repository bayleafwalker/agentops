---
doc_id: vuoro-1191-ratification-gate-design
status: draft
---

# Human-only document ratification gate — design

Owner: agentops reusable validation policy. Answers item #1191's design-pass
blocker (event #1299). This is a design only — no enforcement code ships
with this doc.

## What currently exists

Two documents in this repo already use a `ratified_by`/`ratified_at`
frontmatter convention with no enforcement behind it:
`docs/plans/agentops/vuoro-served-substrate-plan.md` and
`docs/plans/agentops/vuoro-appservice-runtime-handoff.md`. Both carry
`status: ratified`, `ratified_at: <date>`, `ratified_by: operator`. Nothing
today checks that the git-level actor who committed a ratification change is
actually the named human — the convention is enforced only by whoever
remembers to follow it, which is exactly the gap #1191 exists to close.

The repo's existing verification-hook family is a set of dependency-free
`validate_*.py` scripts under `templates/dispatch/scripts/`
(`validate_verification_artifacts.py`, `validate_vuoro_profiles.py`, etc.),
invoked at dispatch/verification checkpoints (e.g. the
`code-change-verification` skill, or explicitly before marking a sprintctl
item done — see tracker event history citing
`validate_verification_artifacts.py --root .`). There is no git-level
`pre-commit` hook in this repo today; "the Git validation boundary" in
#1191's title refers to this same validate-script family, run against the
working tree/diff, not literal `.git/hooks`.

## Trigger

A new script, `validate_ratification_gate.py`, following the existing
`validate_*.py` convention (stdlib-only, `--root` argument, raises
`ValueError` with a path-prefixed message on violation). It inspects the
current diff (`git diff <base>...HEAD -- '*.md'` for a CI/dispatch
invocation, or working-tree diff for a local pre-flight run) and triggers a
check on a file when either is true:

1. The file's frontmatter `status` field changes to `ratified` in this diff
   (a draft-to-ratified transition), or
2. The file already has `status: ratified` on either side of the diff and
   its body content changed (a ratified-supersession edit — re-ratifying
   existing content, or the `supersedes:` list changing).

Files whose frontmatter has no `status` field, or whose `status` is
anything other than `draft`/`ratified`/`superseded`, are explicitly
out of scope for this gate (freeform non-governed status fields must be
unaffected, per the item's verify clause) — the gate only ever looks at
files that already opt in to the three governed values.

## Proof format: commit trailer + configured human allowlist

Concrete mechanism (deliberately not left abstract):

- A new config file, `templates/dispatch/ratifiers.json`, lists configured
  human ratifier identities as a flat array of git author-email strings,
  e.g. `["operator@example.invalid"]` (exact value TBD by whoever builds
  this — the design only requires *a* configured allowlist file at this
  path, checked into the repo, human-edited).
- A qualifying commit must carry a `Ratified-By: <identity>` trailer (the
  standard git trailer convention, e.g. `git commit --trailer`) where
  `<identity>` exactly matches one entry in `ratifiers.json`.
- The validator additionally requires the commit's own `author email` to
  match the *same* entry the trailer names — the trailer alone is not
  sufficient, because a trailer is just text an agent could also type. The
  match must hold on both: (a) trailer present and listed, and (b) git
  author identity for that commit equals the listed identity. This is what
  makes agent/automation transitions fail: known agent actor conventions in
  this project (`claude:*`, `codex:*`, or any commit whose author is a
  service/bot identity, e.g. `noreply@anthropic.com` per this project's own
  `Co-Authored-By:` convention) will never appear in `ratifiers.json` and
  will never match on author email, so they cannot forge a valid trailer.
- The doc's own frontmatter `ratified_by` value must also match the same
  configured identity (closing the loop between the git-level proof and the
  document's self-declared claim) and `ratified_at` must be present and
  parse as a valid date.

## Where this plugs in

Alongside the existing `validate_*.py` family: add
`validate_ratification_gate(root: Path, base_ref: str | None) -> None`
called the same way `validate_verification_artifacts.py` is today —
from the `code-change-verification` skill's checklist, and as a discrete
step any dispatch-build/dispatch-review flow can invoke before treating a
ratification-bearing change as complete. It does not require a literal
`.git/hooks/pre-commit`, matching this repo's existing convention of
running validators at dispatch/verification checkpoints rather than at
raw commit time — though nothing prevents a future pre-commit wrapper from
calling the same function, which is why it should be a plain importable
function, not a script with inlined logic.

## How each verify-clause bullet gets tested

- **Agent/automation transitions fail**: test fixture commits a
  draft→ratified diff with `Ratified-By: claude:some-agent` (not in
  `ratifiers.json`) and author email `noreply@anthropic.com` — validator
  must raise.
- **Registered human-signed transitions pass**: fixture commit with
  `Ratified-By: operator@example.invalid` trailer, matching author email,
  and matching frontmatter `ratified_by` — validator must pass.
- **Unchanged ratified docs remain valid**: a diff that touches an
  unrelated file, or a ratified doc's non-body metadata (e.g. an unrelated
  frontmatter key), while leaving `status`/body untouched, must not
  trigger the gate at all.
- **Freeform non-governed status fields are unaffected**: a fixture doc
  with an arbitrary `status: exploratory` (not one of the three governed
  values) must never be inspected by this validator, regardless of trailer
  or author.

## Explicitly NOT in this design (non-scope, per item #1191)

- No centralized document-content store — the gate reads whatever `.md`
  files are already in the diff; it does not fetch or mirror content
  elsewhere.
- No autonomous approval path of any kind — there is no mechanism by which
  an agent can self-approve; the only path to "pass" is a human identity
  match on both trailer and git author email.
- No Vuoro ratification database — `ratifiers.json` is a plain
  repo-committed file, not a served/authoritative store. This may be
  revisited later; v1 is intentionally file-based.
- No actual enforcement code, hook wiring, or CI config ships with this
  document — that is the next, separate build dispatch's job.

## Rollback

Per the item's own rollback clause: disable the gate (skip invoking
`validate_ratification_gate` from the dispatch/verification checkpoints)
while leaving its audit-visible output (whatever it already logged) intact.
Since this is a pure-function validator with no side effects of its own,
"disabling" it is simply not calling it — no state to unwind.
