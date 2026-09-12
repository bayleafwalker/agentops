# Structured handoffs (handoff/v1)

Machine-readable session handoffs live here as `<date>-<slug>.v<N>.json`, each
with a rendered `<date>-<slug>.v<N>.md` beside it and, when sprintctl was
available, a `<date>-<slug>.v<N>.sprintctl-bundle.json` referenced by digest.

**The JSON is canonical.** The `.md` is for humans and is regenerated from the
JSON (`agentops handoff render <file>`); nothing reads it back. The ack guard,
the validator and the SessionStart injection all parse the JSON.

This is the machine half of the prose convention in `../handover-*.md`, not a
replacement for it: prose carries narrative a schema cannot, and a handover
document remains the right artifact for a session close that is not launching a
successor.

| Command | Purpose |
|---|---|
| `agentops handoff create` | gather repo state, write the pair |
| `agentops handoff validate <file>` | schema, paths, head, `diff_sha256` **now**, non-empty `next_action` |
| `agentops handoff prompt <file>` | the successor's first prompt |
| `agentops handoff ack <file> --session-id <id>` | claim it; refuses if already claimed |
| `agentops handoff render <file>` | regenerate the `.md` |

Schema: `../../../schemas/handoff.schema.json`.
Implementation: `../../../templates/dispatch/scripts/handoff.py`.
Skill: `/projects/dev/.claude/skills/handoff/SKILL.md`.
Acceptance procedure: `../../verification/handoff-v1-successor-isolation.md`.

## `diff_sha256` and `state.digest_version`

`diff_sha256` is what lets a successor prove the working tree is the one the
predecessor left; a mismatch is a refusal, never a warning. It has two
definitions, and `state.digest_version` says which one a given handoff used.
`validate` recomputes **the definition the file declares**, so nothing written
under the old one starts refusing.

| `state.digest_version` | Definition |
|---|---|
| absent, or `1` | sha256 over the bytes of `git diff HEAD` followed by the bytes of `git status --porcelain`, both run in the repo path, no separator |
| `2` — what `create` writes today | v1's two inputs, then, for each untracked non-ignored file (`git ls-files --others --exclude-standard`, sorted by raw path bytes), the record `NUL <path bytes> NUL <sha256 of contents, lowercase hex>` |

v2 exists because v1 was blind to *content* changes in untracked files:
`git status --porcelain` names an untracked path but never its bytes, so editing
an untracked file left the digest unmoved. That was a phase-4 acceptance finding
(`../../verification/handoff-v1-successor-isolation.md`), and it mattered
because scratch notes, drafts and generated output are exactly the untracked
files a session churns.

Contents are hashed as **bytes**, so an untracked binary is covered like any
other file. A path git lists but that cannot be read (a dangling symlink, a file
removed mid-scan) records the literal `unreadable` in place of a digest.
Gitignored files are outside the digest by construction.

The four handoffs committed here predate v2 and carry no `digest_version`; they
validate under v1 and are the compatibility case the tests pin.

## Two hosts, one guard

`origin_host` and `origin_path` are stamped at `create` time and name the
machine that keeps the authoritative copy. When the handoff is carried to a
successor on another host — `scp` to devbox-vm, which shares no filesystem mount
with the workstation — the single-active-successor guard would otherwise be two
files and two independent claims. So `ack` on any host that is not the origin
performs the atomic ack on the **origin's** copy first, over
`ssh <origin_host> agentops handoff ack <origin_path> --session-id <id>`
(falling back to `python3 …/handoff.py ack …` if `agentops` is not on the
origin's non-interactive PATH), and updates the local copy only once that
succeeded. A remote refusal leaves the local file byte-identical.

Requirements: the successor host must be able to `ssh` to `origin_host` as the
user that owns the file, and both hosts must have the repository checked out at
the same path (the `python3` fallback uses this file's own script path). A
handoff with no `origin_host` — anything written before this existed — acks
locally, as before.

An acknowledged handoff stays here as the record of the transfer. Do not edit one
by hand — `create` writes `.v<N+1>` rather than overwriting.
