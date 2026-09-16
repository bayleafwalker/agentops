# Working agreements (devbox, user `agent`)

Auto-loaded in every devbox session. Shared rules live in `/projects/dev/AGENTS.md`; this
file carries only what differs on this host.

- **Sandbox escalation is yours.** `gh`, `fj`, `curl`, `git push/fetch` and cluster calls
  return exit 0 with empty output inside the sandbox. Pass `dangerouslyDisableSandbox: true`;
  never ask for it, and never conclude absence from a sandboxed result (*could not check* is
  not *none found*).
- **Standard workflow needs no permission** (commit, push, PR, merge, release, deploy) except
  where a repo's `.claude/gates.json` declares a gate.
- **This host is not the workstation.** `/projects/dev` here is devbox's own clone set: same
  paths, different content. Say which host a finding is from.
- **Verify at the artifact, not the report**: running pod `imageID`, migrations table, the
  canonical remote (`git config claude.canonicalRemote`).

## Credentials on this host (measured 2026-08-29)

- `gh` authenticates through the environment, not a keyring; `gh auth status` is authoritative.
- `fj` holds an OAuth login for `git.apps.kotona.app`. The workstation's Forgejo token files
  do not exist here, and that is not a fault.
- `git push` credential helpers are wired. `git config user.email` is a placeholder: set an
  identity per repository before committing.
- The served-vuoro credential here is `vuoro-shared-agent`, not the workstation's identity.
  A `vuo_operator_` token is vuoro-cloud's, not Forgejo's.
- No sops age key and no appservice kubeconfig on this host: say "not available on devbox".
