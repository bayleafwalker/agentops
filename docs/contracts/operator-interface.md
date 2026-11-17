# Operator interface contract

Status: adopted 2026-11-17. Applies to every agent-tool CLI and TUI in the estate
(sprintctl, auditctl, actionctl, lanectl, credctl, vuoro-cli, agentops, scribectl
and new tools) and to the vuoro.cloud web surfaces. Conformance check:
`agentops cli-contract -- <tool>` (scripts/cli_contract.py).

Every command has two users: an operator at a terminal and a coding agent in a
harness. The operator needs orientation and safety; the agent needs stable,
compact, parseable output and errors it can act on. Neither pays for the other.

## 1. Home: one command answers "where am I, what needs me, what next"

`<tool> status` prints, in order:

1. **Context**: the target the tool resolved (identity, repo, backend, database or
   workspace) and how (`marker`, `env`, `flag`, `fallback`). A fallback target is
   named as one: `context: ~/.sprintctl/sprintctl.db (fallback: no .sprintctl/ marker)`.
2. **Needs you**: items waiting on a human or failing, most urgent first, each with
   the id the next command takes. Empty is stated: `Nothing needs you.`
3. **In flight**: what is running, claimed or reserved, with age (`17d idle`).
4. **Next**: one to three exact commands that act on the above, on lines starting
   `next:`.

Budget: under 1 s on local state and at most 24 lines before `--all`.
A bare `<tool>` prints the grouped help (section 2); on a TTY a stateful tool may
print `status` instead. Either way it exits 0.

## 2. Help is a map, not an index

- Group commands by task, in this order: `Start here`, then the tool's daily
  verbs, then `Inspect`, `Change`, `Maintain`, `Plumbing` (hooks, credential
  helpers, migrations, schema). Plumbing may be hidden behind `--all`.
- Descriptions fit on one line and are never truncated (`...`). In click, keep
  the first docstring line under 45 characters or set `short_help`.
- Top-level help starts with one purpose line and ends with `Examples:` (one to
  three real commands) and a pointer to `<tool> <command> --help`.
- Every command that takes positionals documents them.
- `--version` works on every tool.
- A misspelled command exits 2 with `did you mean <command>?`.

## 3. Output: human on a TTY, contract with --json

- **Human default**: aligned columns with one header row; a summary line for
  lists (`8 releases: new=1 parked=5 ready=2`); relative ages (`3m ago`) with
  absolute times under `--long`; numbers rounded for reading (`$0.57`, `2.7M`).
- **State vocabulary**, the same in CLI, TUI and HTML, with symbols that still
  work without color: `▲ needs you`, `✗ failed`, `◐ running`, `● ok/done`,
  `○ idle/queued`, `◌ unknown/stale`.
- **Color** only on a TTY, and never the only carrier of meaning. Honour
  `NO_COLOR`, `FORCE_COLOR`, `TERM=dumb` and `--no-color`.
- **Non-TTY**: the same text without color, spinners, prompts or truncation.
- **`--json`** on every read command: one object (never a bare array) with
  `"schema": "<tool>.<noun>/v<N>"`, snake_case fields, ISO-8601 UTC times and
  the list under a named key. Pretty-printing only on a TTY. Changing a field
  bumps the schema version.
- **Bounded by default**: list commands default to open or active items in the
  current scope, with `--limit` (default 50) and `--all`, and say how many were
  omitted: `… 260 done items hidden (--all)`.
- **Agent economy**: ids in text output are exactly what the next command
  accepts; no prose repeated on every row; reasons clipped with `…` and the
  full text available under `show`.

## 4. Errors: what happened, why, and the exact fix

```
error: no sprint is active for repo agentops
  why: .sprintctl/backend.json selects served mode and no sprint is open
  fix: sprintctl sprint list --all     # or: sprintctl sprint create --name <name>
```

- `error:` line on stderr, then optional `why:` and `fix:` lines. Under `--json`
  the error is also on stdout as
  `{"schema": "<tool>.error/v1", "error": {"code", "message", "fix"}}`.
- No Python traceback without `--debug`. Catch driver errors (psycopg, httpx,
  ssl) at the command boundary and name the host and the configuration source.
- Missing configuration is an error, not an empty result: a list that silently
  reads an unintended fallback target violates this contract.
- Exit codes: `0` ok, `1` failed, `2` usage, `3` not found, `4` not permitted or
  not authenticated, `5` precondition failed (dirty tree, stale lease, gate
  closed), `75` temporary (network, lock). Document them in `--help`.

## 5. Effects are visible, previewed and receipted

- Help for a command that writes anything (a file, a remote event, a ref) says
  so in its one-line description, e.g. `handoff  write a handoff bundle (records an event)`.
- Effectful commands take `--dry-run`, which prints the exact plan and changes
  nothing. Tools that already preview by default and act on `--execute` keep
  that; a tool picks one convention for all its commands.
- Irreversible effects (land, merge, reap, delete, overwrite) confirm on a TTY
  and require `--yes` off a TTY.
- Every effect ends with a receipt and a next step:
  `✓ landed ui-07 → main 3f2a1c9 (train t-118)` / `next: lanectl status`.
- A repeated effect says `already <state>` and exits 0.

## 6. Shared flags and words

| Purpose | Flag | Not |
|---|---|---|
| machine output | `--json` | `--format json` (keep as alias only) |
| scope | `--repo <id>` | `--repo-id` (alias), positional repo |
| list size | `--limit N`, `--all` | unbounded default |
| preview | `--dry-run` (or the tool's single `--execute` convention) | mixed per command |
| non-interactive confirm | `--yes` | |
| diagnostics | `--debug` | |
| artifact path | `--output PATH` (`-` for stdout) | `--out`, `--html PATH` |

Listing verb is `list` (`ls` as alias); one record is `show`. Durations state
their unit in the flag name or help (`--timeout-minutes`, or "seconds").
Transport and connection flags (`--broker-host`, `--client-key`, …) are grouped
under `Connection options` and default from configuration.

## 7. Speed

`--help` under 300 ms (500 ms hard limit), `status` under 1 s on local state.
Import heavy modules lazily. A command that needs longer (estate probes) prints
progress on stderr and supports a cheaper scoped form (`--env X`).

## 8. TUI

- Views mirror the `status` sections; the same state vocabulary as section 3.
- A footer key legend that fits 80 columns (`? keys · q quit` minimum), `?`
  for the full list, `j/k` and arrows, `g/G`, `/` filter, Enter for detail,
  scrollable detail panes.
- Refresh is visible (`updated 4s ago`) and rate-limited; it never polls a
  remote owner faster than the configured interval.
- Below 80 columns, rows stack; on a non-TTY, the TUI prints `status` and exits.

## 9. Web (vuoro.cloud and generated HTML views)

- One token set (color, type scale, spacing, radius, focus ring) shared by the
  public site, the app shell, the dispatch console and the OAuth pages, in light
  and dark.
- Signed-out states show one primary action (`Sign in with GitHub`), never a form
  stuck on `Loading…`. Every async region has loading, empty, error and stale
  states.
- WCAG 2.2 AA contrast, visible focus, skip links hidden until focused, usable
  at 375 px without horizontal scrolling, `<meta name="viewport">` on every page.
- Generated HTML (lanectl `view`, `lifecycle-web`) uses the same state
  vocabulary and supports `prefers-color-scheme`.

## Adopting it

Run `agentops cli-contract --command <a real subcommand> --status status -- <tool>`
in a configured repository. A tool conforms when every check passes. Record
justified exceptions in the tool's README under "Interface exceptions" with the
reason; the checker does not grant waivers.
