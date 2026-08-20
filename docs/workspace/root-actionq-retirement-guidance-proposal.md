# Root workspace guidance: ActionQ retirement proposal

`/projects/dev/AGENTS.md` is host-local assembled guidance rather than a file
tracked by a repository. The versioned Agentops fragment is
`templates/workspace/AGENTS.agentops.md`; it now carries the current retirement
boundary. Apply the following cleanup to each host-local assembled copy through
the workspace-guidance owner, not by syncing one host's whole file to another.

## Remove obsolete executable guidance

Delete these ActionQ-specific passages from the host-local root file:

- Under **PATH in legacy devbox pod**, the list of known-good `actionctl`,
  `dispatcher-once`, and Sprintctl pod-venv binaries.
- The `kubectl exec ... dispatcher-once` example and the PATH override that
  prepends the ActionQ dispatcher virtual environments. Preserve the general
  warning that switching users must retain injected model-provider variables.
- Under **Workflow — legacy devbox pod**, the requirement to start
  `actionq-daemon` in tmux and its `actionq-daemon --config ...` example.

Those commands cannot represent current package behavior: ActionQ 0.1.26 no
longer provides the daemon/server/harness execution plane, and
actionq-dispatcher 0.2.0 is an intentionally failing tombstone.

## Insert current boundary

Include the versioned **ActionQ retirement boundary** from
`templates/workspace/AGENTS.agentops.md` in the next assembled root-guidance
update. In particular:

- never install, invoke, schedule, refresh, or repin the removed execution
  path;
- allow only a one-time tombstone upgrade of an existing stale launcher before
  uninstalling it;
- distinguish merged source retirement from appservice/devbox/NixOS runtime
  retirement; and
- require operator evidence for appservice phase 1 → health proof → phase 2,
  followed by the devbox unit and NixOS retirement gates.

This proposal changes guidance only. It does not stop a unit, alter appservice,
deploy NixOS, or assert that any running system has already been cut over.
