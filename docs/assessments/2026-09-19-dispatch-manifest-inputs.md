# Dispatch manifest remaining-input consumer measurement — 2026-09-19

**Item:** agentops #2453 (sprint 559, clerical)
**Question:** of the two inputs TS-11 names as still keeping dispatch manifests and
`schemas/dispatch-manifest.schema.json` alive ("skill selection, verification routes"),
which is actually read by anything, and what would replace each reader under TS-11
(S3 `acceptance_contract`, S6 instruction/skill digests)?

This is read-only measurement. No manifest, schema, hook or script is changed by this
document (see the diffstat command in Validation, below).

## Method

1. Inventoried every `*.dispatch.json` in the devbox clone set (excluding worktrees).
2. Read each manifest's `skills` and `verification` blocks against the schema keys at
   `schemas/dispatch-manifest.schema.json` lines 141-170 (`skills`) and 353-420
   (`verification`).
3. In each of agentops, sprintctl, vuoro, auditctl, kctl, actionq, scribectl, ran:

   ```
   grep -rn --include='*.py' --include='*.sh' --include='*.yml' --include='*.md' \
     -E '\["skills"\]|\.get\("skills"|skill_lock|\["verification"\]|\.get\("verification"|verification\.(routes|profiles)' \
     <repo> --exclude-dir=_wt --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.next
   ```

4. Read every hit and classified it as **reader** (uses the value at run time to drive
   behavior), **validator only** (schema/shape check, including tests of the validator),
   or **documentation** (prose only) — with a fourth outcome this measurement had to add
   because the grep pattern is not schema-scoped: **different schema** for hits where the
   matched `"skills"`/`"verification"` key belongs to an unrelated record (session
   capsules, completion evidence, scribectl's own per-skill runner-routing config) and
   never touches `schemas/dispatch-manifest.schema.json`'s `skills`/`verification` blocks
   at all. The item text assumed all hits would classify into its three buckets; that
   assumption did not hold, and this document reports the mismatch rather than silently
   forcing those hits into one of the three.

## 1. Manifest inventory

```
find /projects/dev -maxdepth 2 -name '*.dispatch.json' -not -path '*/_wt/*'
```

14 manifests found (18 were found in the 2026-08-29 inventory; the drop is discussed
under "Discrepancies with the item text" below):

| Repo directory | Manifest | `skills.selected` count | `skills.overlays` | `verification.command_families` |
|---|---|---|---|---|
| actionq-dispatcher | actionq-dispatcher.dispatch.json | 5 | — | unit, docs |
| actionq-dispatch | actionq-dispatcher.dispatch.json | 5 | — | unit, docs |
| kctl | kctl.dispatch.json | 6 | 1 | unit, docs, full-suite |
| auditctl | auditctl.dispatch.json | 6 | 1 | unit, docs, full-suite |
| agentops | agentops.dispatch.json | 10 | — | unit, docs, full-suite |
| frontier-weave | frontier-weave.dispatch.json | 7 | — | docs, unit |
| homelab-analytics | homelab-analytics.dispatch.json | 20 | 1 | unit, lint, typecheck, architecture, full-suite |
| scribectl | scribectl.dispatch.json | 11 | 1 | unit, docs, full-suite |
| vuoro | vuoro.dispatch.json | 8 | 1 | unit, architecture, docs, full-suite |
| bindery-core | bindery-core.dispatch.json | 11 | — | unit, docs, integration, lint, full-suite |
| actionq | actionq.dispatch.json | 7 | 1 | unit, integration, docs, full-suite |
| sprintctl | sprintctl.dispatch.json | 15 | 1 | unit, integration, docs, full-suite |
| homelab-gitops-template | homelab-gitops-template.dispatch.json | 6 | 1 | kustomize, secrets, docs |

`actionq-dispatch/actionq-dispatcher.dispatch.json` and
`actionq-dispatcher/actionq-dispatcher.dispatch.json` are byte-identical
(`diff` empty) — two directories on devbox carrying the same repo's manifest. Not
in scope to resolve here; noted so the coordinator doesn't double-count it as two
repos.

### Not measured on devbox

- **appservice** — the item text names this as absent, but a directory
  `/projects/dev/appservice` exists. It is not a git repository (`git status` fails
  with "not a git repository") and contains only an empty `.claude/` directory — no
  `*.dispatch.json`. The 2026-08-29 inventory recorded `appservice.dispatch.json` as
  **executable**, so a manifest existed here previously; it is gone now along with the
  rest of the checkout. Net effect matches the item's claim (no manifest to inventory)
  but for a different reason than "repo absent" — flagging the mismatch per instructions
  rather than silently correcting the item text.
- **datacluster** — absent. (`datacluster-template` exists at `/projects/dev` but is a
  distinct repo the item did not name; not substituted in.)
- **local-inference** — absent (directory does not exist). The 2026-08-29 inventory
  recorded it as present but unsound ("no git remote at all"); it is gone entirely now.
- **acceptance-lab** — absent, consistent with the item text.

## 2. `skills` input

Schema (`schemas/dispatch-manifest.schema.json:141-170`): an object requiring
`selected` (array of skill-name enum strings); optional `template_root` (default
`/projects/dev/agentops/skills`) and (seen in manifests, not shown in this line range)
`overlays`.

### Consumer search — grep hits and classification

| Repo | Consumer path:line | Value read | Class | Replacement under TS-11 |
|---|---|---|---|---|
| agentops | `scripts/sync_skills.py:202` | `skills.selected` (via `manifests[0]` glob of `*.dispatch.json`) | **reader** — resolves the list to copy/sync skill templates into a target repo at run time | S6: "Session binding records instruction and skill digests" (`docs/plans/2026-09-17-target-state.md:56-57` names `sync_skills.py` itself for retirement at S6) |
| agentops | `scripts/validate_dispatch_manifest.py:53,61,99` | `skills.selected`, `skills.template_root` | validator only — this *is* the schema/enum/template-root checker named in the item's own Validation command | n/a (validator retires with the manifest/schema) |
| agentops | `scripts/validate_verification_artifacts.py:186-187,209` | `skills.selected`, cross-referenced against `risk_surfaces[].skills` | validator only — shape/membership check (`risk_skills not in selected` raises); does not use the list to decide which skills run | n/a (validator retires with the manifest/schema) |
| agentops | `scripts/validate_verification_artifacts.py:159-169` | `instruction_set.skill_lock_ref` (matched by the `skill_lock` alternative, not the `skills` block) | validator only — shape check of a *different* schema key. Notably `instruction_set` (schema lines 435+) is the S6-shaped v2 catalog already present as optional in this same schema, so this hit is evidence toward the replacement, not a consumer of the retiring input | already the S6 shape |
| agentops | `scripts/tests/test_validate_dispatch_manifest.py:112,115,135,471` | `skills.selected`/`template_root` | validator only — unit tests of `validate_dispatch_manifest.py` | n/a |
| agentops | `scripts/tests/test_schema_check_composition.py:886,918,933` (+ `skill_lock` hits at 52,745,772,774,786,787,789,790,829,836,840,843) | `skills.selected` / `instruction_set.skill_lock` | validator only — generic `schema_check` engine tests and docstrings (52, 745, 790), using this schema as the fixture | n/a |
| agentops | `scripts/tests/test_schema_check_audit.py:15,141,166,341,350,541,545,586,587,590,594` | `instruction_set.skill_lock` (docstrings + fixture data, matched by `skill_lock`) | documentation/validator-fixture — mix of prose docstrings (15, 541, 586, 590, 594) and generic `schema_check` audit-tool test fixtures (141, 166, 341, 350, 545, 587) | n/a |
| agentops | `scripts/tests/test_session_binding.py:108` | `instructions["skills"]` on a **session-binding record**, not the manifest | **different schema** — session binding's own `skills` field, asserted empty ("not yet determinable at SessionStart") | n/a — this is the S6 record's field, already live |
| scribectl | `scribedispatch/cli.py:174`, `scribectl/doctor.py:126` | `cfg.get("skills")` on `~/.config/scribectl/dispatch.yaml`, scribectl's own per-skill runner-routing map | **different schema** — unrelated to the dispatch manifest entirely | n/a |
| sprintctl, vuoro, auditctl, kctl, actionq | (no hits) | — | — | — |

**Reader count for `skills`: 1** (`agentops/scripts/sync_skills.py:202`).

## 3. `verification` input

Schema (`schemas/dispatch-manifest.schema.json:353-420`): an object requiring
`command_families` (array of enum strings); optional `targeted_first` (bool, default
true) and `commands` (array of strings).

### Consumer search — grep hits and classification

| Repo | Consumer path:line | Value read | Class | Replacement under TS-11 |
|---|---|---|---|---|
| agentops | `scripts/validate_verification_artifacts.py:192,195` | `verification.command_families` (shape only, via `_string_list`) | validator only — never used to select which commands actually run; `select_surfaces`/`--require-results` logic in the same file drives off `risk_surfaces`, not `verification` | n/a (validator retires with the manifest/schema) |
| agentops | `scripts/tests/test_manifest_schema_enums.py:35` | `SCHEMA["properties"]["verification"]["properties"]["command_families"]["items"]["enum"]` | validator only — schema self-test of the enum list | n/a |
| agentops | `scripts/validate_session_mechanization_artifacts.py:189,287` | `evidence["verification"]` / `value["verification"]` on **session-mechanization artifacts** (pass/fail/error tallies, git commits), not the manifest | **different schema** | n/a |
| agentops | `scripts/session_reconciler.py:137` | `capsule["verification"]` on a **session capsule**, not the manifest | **different schema** | n/a |
| actionq | `actionq/completion_log.py:181`, `actionq/completion_outbox.py:503` | `evidence.get("verification")` / `capsule["verification"]` — completion-event evidence tally (`pass`/`fail`/`error` counts), not the manifest | **different schema** | n/a |
| sprintctl, vuoro, auditctl, kctl, scribectl | (no hits) | — | — | — |

**Reader count for `verification`: 0.** No hit in any of the seven searched repos uses
`verification.command_families`, `verification.targeted_first` or `verification.commands`
to decide what runs; every hit against this schema key is either a shape check on the
manifest itself, or belongs to a different record entirely (session/completion evidence
verification tallies, which are an unrelated "did this run pass" structure, not "which
commands should run").

## Summary

- **`skills` reader count: 1** — `agentops/scripts/sync_skills.py`, already named for
  retirement alongside the manifest and schema at S6 in
  `docs/plans/2026-09-17-target-state.md:56-57`.
- **`verification` reader count: 0** — across agentops, sprintctl, vuoro, auditctl,
  kctl, actionq and scribectl, nothing reads `verification.command_families` /
  `targeted_first` / `commands` at run time; every match is a validator-only shape
  check on the manifest or a hit against an unrelated schema (session/completion
  evidence tallies, scribectl's own runner-routing config).
- **Not measured on devbox:** appservice (directory present but not a git repo, no
  manifest — see discrepancy note above), datacluster, local-inference, acceptance-lab.

## Discrepancies with the item text

1. **appservice is not simply "absent."** A directory exists at
   `/projects/dev/appservice`; it is not a git repository and carries no
   `*.dispatch.json`. The 2026-08-29 inventory recorded an executable
   `appservice.dispatch.json` here, so the checkout was stripped down at some point
   between then and now. The practical outcome (no manifest to inventory) matches the
   item's framing, but "repo absent" is not what is on disk.
2. **local-inference was present-but-unsound in the 2026-08-29 inventory, not absent.**
   It has since been removed from devbox entirely; today's measurement agrees with the
   item that it is not measurable here, but for a different reason (deleted vs. never
   cloned).
3. **Manifest count dropped from 18 (2026-08-29) to 14 today**, beyond the
   hybrid-dispatch deletion (`0baa680`) the item cites — appservice's and
   local-inference's manifests are both gone, and `hostproto` /
   `vuoro-bounded-output-starter` (archived/broken in the prior inventory) are also
   absent from this pass. Not investigated further; out of this item's scope.
4. **Two directories, one manifest.** `actionq-dispatch/` and `actionq-dispatcher/`
   both carry `actionq-dispatcher.dispatch.json` with identical contents. The prior
   inventory only names `actionq-dispatcher`. Not resolved here (writable scope is this
   document only).

## Validation

```
$ python3 scripts/validate_dispatch_manifest.py agentops.dispatch.json
ok agentops.dispatch.json

$ git diff --stat origin/main -- '*.dispatch.json' schemas scripts hooks
(empty)
```

Re-running the grep commands quoted in §2/§3 above against `/projects/dev` reproduces
the hit counts in this document (1 reader for `skills`, 0 readers for `verification`,
against the seven repos named in scope).
