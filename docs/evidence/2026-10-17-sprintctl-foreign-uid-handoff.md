# Sprintctl foreign-UID delegated handoff source check

Result: PASS on 2026-10-17 UTC. Sprintctl source commit: `3dfa79d9c0e816a542e3361d66bc953c6d7c327c`. Container image: `python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`.

The disposable container ran with `--network none` and `--read-only`; only `/fixture` and `/tmp` were writable tmpfs mounts. The only bind mount was `/workspace/sprintctl-delegated-profile/sprintctl:/src/sprintctl:ro`. It received no Git directory, host credentials, or other host paths. Container root created an adapter-owned fixture as UID 1110/GID 1100: a `03770` workroot, `.sprintctl` mode `0750` with a `0644` served marker, `.vuoro` mode `0750`, `profile.json` mode `0644`, and delegated credential mode `0640`.

The source package was imported before forking because this workspace snapshot makes its source files owner-readable only. The child then changed to the real effective UID/GID 1100/1100 and executed backend/profile selection, delegated credential resolution, and all protected-path checks under that identity. This exercises actual Unix ownership and permission checks in the reader, without changing source permissions.

Assertions passed:

- `load_backend_config(cwd=fixture, environ={})` selected served mode from the exact-CWD marker and protected handoff, retained the UUID repo identity, and marked the profile as trusted implicit delegated.
- The default served credential resolver read the delegated test token from the fixed sibling file.
- UID/GID 1100 could not overwrite either handoff file, add an entry to `.vuoro`, or rename the adapter-owned `.vuoro` entry. Original ownership, modes and credential contents remained intact.
- The child read a separate foreign-owned mode-`0640` token file directly through its group-readable parent directory; only then did the ordinary owner-only reader reject it for its foreign owner.

Reproduction command (run from `/workspace`; the script is supplied on stdin, not mounted):

```sh
docker run --rm -i --network none --read-only \
  -e SPRINTCTL_HANDOFF_TEST_CONTAINER=1 \
  --tmpfs /fixture:rw,nosuid,nodev,noexec,size=16m,mode=1777 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=4m,mode=1777 \
  --mount type=bind,source=/workspace/sprintctl-delegated-profile/sprintctl,target=/src/sprintctl,readonly \
  --workdir /fixture --user 0:0 \
  python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 \
  python -u - < /workspace/agentops-estate-progress/scripts/test_support/verify_sprintctl_foreign_uid_handoff.py
```

This is source-reader and Unix DAC evidence only. It does not establish production adapter installation, systemd identity/groups, ACL/MAC behavior, service lifecycle, or a host qualification run.

The shared receiving UID/GID is not a confidentiality boundary between sessions.
Any process with that same Unix identity and visibility of another run directory
can read its group-readable token; the owner then limits that copied token to
its own run, rather than identifying the presenting process. This check proves
protected writes and reader behavior only. Host qualification must address the
actual per-session filesystem/process visibility and harness CWD controls before
claiming isolation between runs. The current launch gate remains disabled.
