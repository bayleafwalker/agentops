# Handoff 2026-09-12-enforced-isolation-fresh.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Close phase 4 of outctl's context-economy plan by proving a structured handoff survives a real host and uid boundary: the predecessor is bayleaf on the workstation, the successor is agent on devbox-vm, and the only thing that crosses is the handoff JSON.

**Next action.** Append the single line `Enforced isolation acceptance: 2026-09-12.` as the new last line of /projects/dev/outctl/docs/HANDOFF-ENFORCED-RUN-NOTE.md, changing nothing else in that file and nothing else in the repository.

## Predecessor

- harness: claude-code
- session: 75f65a35-f426-49bc-9638-b09003838075
- model: claude-opus-5
- context used: 34%
- transcript: /home/bayleaf/.claude/projects/-projects-dev/75f65a35-f426-49bc-9638-b09003838075.jsonl
- origin: `devbox:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-12-enforced-isolation-fresh.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Do not commit, push, stage or stash anything in any repository; leave the git index empty and every tracked file untouched.
- Edit only the untracked scratch file /projects/dev/outctl/docs/HANDOFF-ENFORCED-RUN-NOTE.md; read files by bounded range rather than dumping whole files.

## Decisions

- **The handoff is created on devbox against devbox's own clone of /projects/dev/outctl, with origin_host set to devbox.** — devbox-vm's /projects/dev is an independent zvol clone, so the workstation's outctl tree (a9392a0, dirty) and devbox's (1d3cdf1, clean) are different trees; diff_sha256 must be computed against the tree the successor will actually validate.

## Rejected

- **Reproducing the workstation's dirty outctl tree on devbox first (git diff HEAD as a patch plus a copy of the untracked files) so the handoff could be created on the workstation.** — Cross-host tree replication is not what this run tests, and under digest v2 it must reproduce untracked file contents byte for byte; the acceptance doc explicitly allows creating the handoff on devbox against devbox's tree instead.

## Repo state

Digest definition: v2 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/outctl` | main | `1d3cdf179a70` | yes | 0 | `2eeea2490e9de260…` |

## Unresolved

- The cross-host ack write-back (agent@devbox -> bayleaf@workstation over ssh) cannot be exercised: no reverse ssh path exists and none was created for this run.

## Evidence

- (none recorded)

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 2403ce97-b3c2-4fe8-804c-1a8f4d2f52b5
- acknowledged: 2026-09-12T15:19:58Z
