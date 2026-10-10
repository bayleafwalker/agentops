# Native skill observation coverage and the dispatch-manifest retirement point

Status: proposed design (2026-10-10). Served items:

- agentops#2488 (TS-11/S6: retire dispatch manifests, their schema and
  `sync_skills.py`)
- the measured gap recorded on it (event #4297) after agentops#2481

Governing records:

- `docs/plans/2026-09-17-target-state.md`
  - TS-3 (:41): "Role and skills are observed, not compiled"
  - TS-11 (:49)
  - S6 (:103-105)
- `schemas/session-binding.schema.json`

This document is a contract. It changes no behaviour.

## 1. Problem

TS-11 retires dispatch manifests "once S3 contracts and S6 digests replace
their remaining inputs (skill selection, verification routes)". #2481 made
S6 record loaded-skill digests. The mechanism is a PostToolUse hook on the
`Skill` tool:

- `hooks/session-skill.sh`
- `scripts/session_binding.py:538-553` (`--record-skill`)
- the hook is registered in user settings with the `Skill` matcher

#2481's acceptance (the workstation-local acceptance record, not committed
to this repository) lists three limitations. They are quoted here so the
evidence does not depend on that file:

> "Direct slash skill113345bc recorded no entry: bypasses Skill tool."
> "Only Skill-tool events observed; preloaded skills not qualified."
> "Stable flock assumes local filesystem; preexisting resolver/corrupt-binding
> shape exception caveats persist."

The served record carries the same finding: sprintctl event #4297 on
#2488, summary "Skill hook acceptance covers Skill-tool events; slash loads
still unobserved". Its detail says that a native direct slash in session
`113345bc-9414-4171-8322-c8e7ec5f9de0` invoked `recording-acceptance`, "but
emitted no Skill tool PostToolUse and binding instructions.skills stayed
empty".

One gap is not from #2481. It was observed separately for this document on
2026-10-10: Codex has no skill hook at all. The registered events in
`~/.codex/hooks.json` are PreToolUse Bash, SessionStart, SubagentStop and
Stop.

So an empty `instructions.skills` does not mean "no skill was loaded". The
schema says as much (`session-binding.schema.json:126`). Retiring the
manifest on that basis would replace a declared record with an incomplete
observed one. The blocker note forbids two fixes: reconstructing assumed
skill loads from prompt text, and reconstructing them from compiled
profiles.

A second finding affects #2488's scope. Two of the manifest's fields still
have live readers:

- `risk_surfaces`: `scripts/jev_shadow.py:188-199` and
  `scripts/validate_verification_artifacts.py`. That validator also
  hard-reads the two sections TS-11 names:
  - `skills.selected` and `skills.overlays` (:186-187)
  - `value["verification"]` (:192)
  - it requires `skills` on every risk surface (:203)
  - it refuses risk-surface skills not in `skills.selected` (:212)

  The schema lists `skills` and `verification` under `required`. The
  validator is a standard verification command (`AGENTS.md:16`).
- `hybrid.protected_paths`: `scripts/check_protected_paths.py:67,72`

The workflows also tell agents to read "the dispatch manifest (verification
commands, test layout, risk_surfaces)"
(`.claude/workflows/vuoro-dispatch-build.js:564,607,710,790`,
`vuoro-dispatch-verify.js:231`).

#2453's measurement still holds for the two fields TS-11 names:

- `skills.selected` has one selecting reader, `scripts/sync_skills.py:202`
- `verification` has no selecting reader (`validate_verification_artifacts.py:192` is a
  shape check)

The schema as a whole is therefore not reader-free.

## 2. Decision

1. **Coverage is declared per load path and recorded in the binding.**
   `instructions.skill_coverage` names each path the harness offers. For each
   path it says whether that path is observed in this session, and by which
   mechanism. An empty `skills` list then means "no skill loaded" exactly
   when every in-use path is `observed`.
2. **Skill tool path: already observed (#2481).** Unchanged.
3. **Native slash path: observed from the harness's own load record, not
   from prompt text.** When a user invokes a skill as `/<name>`, Claude Code
   writes two user records to the transcript:
   - a record whose content is `<command-name>/<name></command-name>` with
     `<command-message>`
   - immediately after it, an `isMeta: true` user record that carries the
     expanded skill body, with no `sourceToolUseID`

   This was measured 2026-10-10 in a workstation-local Claude Code
   transcript (session `8d1e42f3…`, records 355-356, not committed) for
   `/fewer-permission-prompts`. The two records, abbreviated:

   ```text
   {"type": "user", "message": {"content": "<command-message>fewer-permission-prompts</command-message> <command-name>/fewer-permission-prompts</command-name>"}}
   {"type": "user", "isMeta": true, "message": {"content": [{"type": "text", "text": "# Fewer Permission Prompts  Look through my transcripts' MCP and bash tool calls, …"}]}}
   ```

   The second record has no `sourceToolUseID`. A Skill-tool load's
   expansion record carries one; for example, an appservice session record
   has `{"isMeta": true, "sourceToolUseID": "toolu_…"}` followed by "Base
   directory for this skill: …". A built-in command such as `/clear` has
   the first record and no expansion record. The expansion record is
   evidence that a load happened, and its content is what was loaded. The
   recorder reads only that record pair. It never reads the user's
   free-text prompt. A slash token that produced no expansion is not a
   skill load and is not recorded.
4. **Slash observation runs on the existing Stop and SubagentStop hooks.**
   Both are already registered. Each hook scans the transcript from a cursor
   kept in the binding and records each new slash expansion through the same
   flock and idempotency path as `record_skill`. The digest is the sha256 of
   the expansion body as loaded (`loaded_sha256`). The resolver also records
   the on-disk `SKILL.md` path and sha256, when it can resolve them, for
   cross-checking. Observation is turn-granular. That is enough for a
   session record.
5. **Preloaded skills (agent frontmatter `skills:`): unobserved, and kept
   unused by a cheap check.** No agent definition in
   `.claude/agents`, `/projects/dev/.claude/agents` or `~/.claude/agents`
   declares `skills:` today. Until a path observes preloads from a
   harness-emitted record, a lint fails any agent file that declares one.
   Agents are not reconstructed from frontmatter, because that would be the
   compiled-profile inference the blocker forbids.
6. **Codex: coverage `none`, declared.** Codex bindings record
   `skill_coverage: [{path: "codex", status: "unobserved"}]`. Codex sessions
   do not count toward any TS-3 claim until a Codex-side observation is
   qualified.
7. **Retirement: the smaller safe path. Nothing in the manifest is
   deleted by #2488.**
   - The `skills` and `verification` sections are coupled to
     `risk_surfaces` through `validate_verification_artifacts.py`:
     risk-surface skills must be a subset of `skills.selected`, and
     `verification` is read unconditionally.
   - Deleting them before `risk_surfaces` has a new home would break a
     standard verification command. It would also leave
     `risk_surfaces[].skills` validated against nothing.
   - #2488 therefore delivers the observation half of TS-11's
     precondition:
     - the coverage contract
     - the slash scan
     - the preload lint
     - the real-session proofs
   - With those in place, the binding's `instructions.skills` becomes the
     record of skill *use*, as TS-3 requires.
   - The manifest's `skills.selected` stays, but it is demoted to
     distribution and validation configuration. It is read by
     `sync_skills.py` (which skill trees to copy into `.agents/skills/`)
     and by the validator. It is no longer described as a record of
     selection.

   The deletions TS-11 names move as one coherent change to a single
   follow-up item:
   - schema sections and their `required` entries
   - `validate_dispatch_manifest.py`
   - `validate_verification_artifacts.py:186-212` and its tests
   - `sync_skills.py`'s manifest read
   - `risk_surfaces`, `hybrid.protected_paths` and the workflow prompt
     readers

   That follow-up must first name the new home for `risk_surfaces`
   (including the source that validates `risk_surfaces[].skills`) and for
   `protected_paths`. It is not decided here.

## 3. Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Parse `/name` from the UserPromptSubmit `prompt` | That is reconstruction from prompt text, which event #4297 forbids. A typed slash may be a built-in, a typo or a failed load. |
| Record skills from the compile-time profile or agent frontmatter | Compiled-profile inference contradicts TS-3 ("observed, not compiled") and the blocker note. |
| Stop-time digest of the on-disk `SKILL.md` only | The file can change between load and Stop. The expansion body is what the model actually saw, so it is the primary digest. The file digest is a cross-check. |
| Retire the whole manifest and schema now, as #2488's scope says | `risk_surfaces` and `hybrid.protected_paths` have live readers (§1). Deleting them would break `jev_shadow`, `check_protected_paths` and the workflow prompts. |
| Retire only the `skills` and `verification` sections now | `validate_verification_artifacts.py:186-212` hard-reads both, and the schema marks them `required`. Removing them breaks that validator, and `risk_surfaces[].skills` would be checked against nothing. Rewriting the validator now would mean designing the `risk_surfaces` home as a side effect. |
| Keep `skills.selected` as the record of skill selection | It is a declared, unobserved record that competes with the observed one. #2488 demotes it to distribution and validation configuration, and the follow-up deletes it with `risk_surfaces`. |
| Require operator sign-off on coverage before retirement | An artificial gate. The real-session proofs and the lint are cheap checks of done work, and they decide it. |

## 4. Contract

### 4.1 `instructions.skill_coverage` (session-binding schema addition)

```json
"skill_coverage": [
  {"path": "skill-tool",   "status": "observed",   "mechanism": "PostToolUse:Skill",            "qualified_by": "agentops#2481"},
  {"path": "native-slash", "status": "observed",   "mechanism": "Stop|SubagentStop:transcript-expansion", "qualified_by": "agentops#2488"},
  {"path": "preloaded",    "status": "unobserved", "mechanism": null, "guard": "lint:no-agent-skills-frontmatter"},
  {"path": "codex",        "status": "unobserved", "mechanism": null}
]
```

| Field | Values |
|---|---|
| `path` | `skill-tool` \| `native-slash` \| `preloaded` \| `codex` |
| `status` | `observed` \| `unobserved` \| `failed` (the hook ran and errored this session; set by the recorder) |
| `mechanism` | string \| null |
| `qualified_by` | item reference for the real-session proof \| null |
| `guard` | for an unobserved path that is kept unused, the check that enforces it |

The SessionStart writer fills `skill_coverage` from the harness that started
the session: Claude Code (`skill-tool`, `native-slash`, `preloaded`) or
Codex (`codex`). Reader rule: `skills: []` means "no skill loaded" only if
every entry is `observed`, or is `unobserved` with a passing `guard`.

### 4.2 `instructions.skills[]` entry additions

The existing required fields are unchanged:
`{name, path|null, sha256|null, resolution, loaded_at}`. New fields:

| Field | Values |
|---|---|
| `observed_via` | `skill-tool` \| `native-slash` |
| `loaded_sha256` | sha256 of the loaded body. For `native-slash`, the `isMeta` expansion content. For `skill-tool`, null (the file digest is the observation). |
| `transcript_ref` | `<transcript basename>:<line>` of the expansion record. Native-slash only. A pointer, not content. |

Idempotency key: `(observed_via, name, loaded_sha256 or sha256,
transcript_ref)`.

### 4.3 Transcript scan cursor

`instructions.skill_scan`: `{transcript_path_sha256, offset_bytes,
scanned_at}`. The scan reads from `offset_bytes`. A record pair qualifies
only if all of the following hold:

1. The first record is `type: "user"`, with string content containing
   `<command-name>/<name></command-name>`.
2. The next record of `type: "user"` has `isMeta: true` and no
   `sourceToolUseID`.
3. The `<name>` is not in the harness's built-in command list. This is
   belt and braces, because built-ins have no expansion record anyway.

Plugin skills (`plugin:skill`) are recorded with `resolution: unresolved`
and a non-null `loaded_sha256`.

### 4.4 Errors and failure behaviour

The hooks never block the session. They run with `|| true`, which is
existing behaviour. They write coverage `failed` for the path when:

- the transcript is unreadable
- the cursor is beyond EOF (rotation): the scan resets to 0, and
  idempotency prevents duplicates
- the binding is corrupt: the existing caveat, with no write

## 5. Verification plan

1. **Unit tests** in `scripts/tests/test_session_binding.py`, with
   transcript fixtures:
   - a slash skill pair → one entry
   - `/clear` → none
   - free text mentioning `/recording-acceptance` → none (the
     prompt-reconstruction falsifier)
   - a Skill-tool expansion with `sourceToolUseID` → no duplicate from the
     scan
   - a re-scan → idempotent
   - cursor past EOF → reset, with no duplicates
2. **Real-session proofs**, recorded as an acceptance artifact like #2481's:
   - (a) direct `/recording-acceptance` in a fresh workstation session: the
     binding has one `native-slash` entry, and `loaded_sha256` equals the
     sha256 of the expansion record's content
   - (b) a no-skill session: `skills: []` with every coverage entry
     observed or guarded
   - (c) a Skill-tool session: still recorded, and not duplicated by the
     scan
3. **Lint:** `scripts/check_agent_skills_frontmatter.py` (new) fails on any
   `skills:` key in agent definitions under the three agent directories. It
   is wired into `scripts-tests.yml`.
4. **#2488 re-check** (its scope step 1). Re-run #2453's greps on
   `origin/main`. Confirm that `skills.selected` has one *selecting*
   reader (`sync_skills.py:202`) and that `verification` has none. Then
   record every non-selecting reader for the follow-up:
   - `validate_verification_artifacts.py:186-212`
   - `validate_dispatch_manifest.py:100-107`
   - the schema's `required` list

   For #2488, the check of done work is that AGENTS.md,
   `docs/project/project-binding-spec.md` and
   `docs/dispatch/dispatch-manifest.md` no longer describe `skills.selected`
   as the record of which skills a session used. Each of them points to
   `instructions.skills` with `skill_coverage`.

## 6. Migration

1. **Implement in this order:**
   - the §4.1-§4.3 schema additions, with defaults that keep old bindings
     valid (missing `skill_coverage` means "unknown")
   - the scan in `session_binding.py`, invoked from the existing Stop and
     SubagentStop hook scripts
   - the lint

   No new hook registration is needed.
2. **Prove** §5.2 (a)-(c) and record the artifact on #2488.
3. **Re-describe, do not delete (#2488):**
   - AGENTS.md, `docs/project/project-binding-spec.md` and
     `docs/dispatch/dispatch-manifest.md` describe `skills.selected` as
     distribution and validation configuration. They name
     `instructions.skills` plus `skill_coverage` as the record of skill use.
   - No schema, validator, script or CI step changes.
4. **Amend #2488's acceptance.** Its current acceptance is not achievable
   without breaking `validate_verification_artifacts.py`:
   - `git grep -l 'dispatch.manifest\|sync_skills'` returning only retired
     docs
   - the three files deleted

   Replace it with §5.1-§5.4. File one follow-up item covering:
   - the schema `skills` and `verification` sections and their `required`
     entries
   - `validate_dispatch_manifest.py`
   - `validate_verification_artifacts.py:186-212` and
     `scripts/tests/test_validate_verification_artifacts.py`
   - `sync_skills.py`'s manifest read, with its distribution role kept
     under an explicit skill list
   - `risk_surfaces`, `hybrid.protected_paths` and the workflow prompt
     readers

   Its precondition is a named home for `risk_surfaces` and
   `protected_paths`.
