# agentworker bootstrap (Arch bridge)

Imperative, Arch-native stand-up of the `agentworker` hybrid-dispatch worker
identity on the workstation host, which is bare Arch today -- NixOS is a
planned future path for this machine, not an applied one. Follows the same
"temporary bridge" convention as `local-inference/ops/install.sh`: everything
here is mirrored declaratively in `gitops-nixos`
(`modules/users/agentworker.nix`, `modules/system/hybrid-dispatch.nix`,
`hosts/workstation/default.nix`), and `uninstall.sh` exists so this does not
linger as unmanaged state once that NixOS config is actually applied.

## What it does

- Creates the `agentworker` system user/group (uid/gid 1101, matching the
  NixOS module) and the shared `agentdispatch` group (holding the coordinator
  and the worker, and nothing else).
- Creates `/var/lib/agentops/hybrid-dispatch` (state root, 0710),
  `worktrees/` and `evidence/` (2770, setgid, jointly writable), and the
  worker's own `~/.local/share/opencode` (0700).
- Decrypts `opencode.agentworker.auth` from `gitops-nixos/secrets/common.yaml`
  straight to the worker's uid at
  `/var/lib/agentworker/.local/share/opencode/auth.json` (0600) -- the
  coordinator never holds the plaintext. Uses whatever age identity at
  `~/.config/sops/age/keys.txt` (or `$AGE_KEY_FILE`) already decrypts that
  file; there is no `/var/lib/sops-nix/key.txt` on this host, that path only
  exists under sops-nix on NixOS.
- Installs `/etc/sudoers.d/agentworker-hybrid-dispatch`, scoped to letting the
  coordinator run `opencode` and `test` as `agentworker` with no password --
  nothing broader.

## What it deliberately does not do

- Does not install `/etc/agentops/*` vendored policy copies. The NixOS module
  vendors those for reproducibility (see its own comment on
  `contract.policy`), but that vendored copy
  (`gitops-nixos/modules/system/hybrid-dispatch/policy.json`) is currently
  **stale** -- it predates the `bindery_external_runtime_w0` route and the
  `local3090/worker-fast` model state, both only in
  `agentops/templates/dispatch/hybrid/hybrid-dispatch.v1.json`. This bridge
  points `hybrid_dispatch.py` at the live `agentops` checkout instead
  (`AGENTOPS_HYBRID_POLICY` / `AGENTOPS_HYBRID_WORKER_CONFIG`, see the
  `install.sh` output), so there's nothing to go stale here. Refresh the
  vendored copy via `scripts/check-hybrid-dispatch-policy.sh` in gitops-nixos
  before the NixOS cutover, or it will silently deny this route on switch.

## Usage

```bash
sudo ./install.sh
sudo /projects/dev/gitops-nixos/scripts/check-worker-containment.sh \
  agentworker /var/lib/agentops/hybrid-dispatch/worktrees /projects/dev
```

`check-worker-containment.sh` defaults `AGENTOPS_COORDINATOR_USER` to `agent`
(devbox's identity); export `AGENTOPS_COORDINATOR_USER=bayleaf` and
`AGENTOPS_SHARED_GROUP=agentdispatch` first if not running it as the
coordinator user itself.

At NixOS cutover: `sudo ./uninstall.sh`, then enable
`hybridDispatch.workerUser = "agentworker"` for real via
`gitops-nixos/scripts/deploy-host.sh --host workstation`.
