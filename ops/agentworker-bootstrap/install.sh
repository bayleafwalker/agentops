#!/usr/bin/env bash
# Arch-side bring-up for the workstation's `agentworker` hybrid-dispatch identity.
#
# *** THIS IS A TEMPORARY BRIDGE. ***
# gitops-nixos/hosts/workstation is written for this exact machine (commit 83e0c6a
# added workerUser/workerAuthSecret to its hybridDispatch profile) but is not yet
# applied -- the host is still bare Arch, mid-migration. Everything this script does
# imperatively is mirrored declaratively in:
#   gitops-nixos/modules/users/agentworker.nix
#   gitops-nixos/modules/system/hybrid-dispatch.nix
# When the NixOS cutover happens, run ops/agentworker-bootstrap/uninstall.sh and let
# `hybridDispatch.workerUser = "agentworker"` take over instead of leaving this
# behind as unmanaged host state. See docs/runbooks/hybrid-dispatch.md and
# scripts/check-worker-containment.sh (both in this repo) for the contract this
# identity exists to satisfy.
#
# Must run as root. Idempotent -- safe to re-run.
set -euo pipefail

WORKER="agentworker"
WORKER_UID=1101
WORKER_GID=1101
SHARED_GROUP="agentdispatch"
COORDINATOR="${COORDINATOR_USER:-bayleaf}"
WORKER_HOME="/var/lib/agentworker"
STATE_ROOT="/var/lib/agentops/hybrid-dispatch"
WORKTREE_ROOT="$STATE_ROOT/worktrees"
EVIDENCE_ROOT="$STATE_ROOT/evidence"
OPENCODE_BIN="$(command -v opencode || true)"
GITOPS_ROOT="${GITOPS_ROOT:-/projects/dev/gitops-nixos}"
SECRETS_FILE="$GITOPS_ROOT/secrets/common.yaml"
# The secret is decrypted with whatever age identity on this host can already
# read secrets/common.yaml -- default sops lookup location, not a dedicated
# host key. There is no /var/lib/sops-nix/key.txt on Arch; that path is a
# NixOS-only artifact of sops-nix and does not exist here regardless of what
# any prior status report claimed.
#
# Read from the coordinator's own home, not $HOME: this script runs under
# `sudo`, which resets HOME to root's (/root) by default, so $HOME here would
# silently look in the wrong place even when run by the coordinator.
COORDINATOR_HOME="$(getent passwd "$COORDINATOR" | cut -d: -f6)"
AGE_KEY_FILE="${AGE_KEY_FILE:-$COORDINATOR_HOME/.config/sops/age/keys.txt}"
AUTH_JSON_PATH="$WORKER_HOME/.local/share/opencode/auth.json"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (sudo $0)"

# ---- preflight -------------------------------------------------------------
log "Preflight"
command -v sops >/dev/null || die "sops not found (pacman -S sops)"
command -v age >/dev/null || die "age not found (pacman -S age)"
[ -n "$OPENCODE_BIN" ] || die "opencode not found on PATH"
id "$COORDINATOR" >/dev/null 2>&1 || die "coordinator user $COORDINATOR does not exist"
[ -f "$SECRETS_FILE" ] || die "$SECRETS_FILE not found -- set GITOPS_ROOT"

# ---- group + user -----------------------------------------------------------
log "Group/user: $WORKER"
if ! getent group "$WORKER" >/dev/null; then
  groupadd --system --gid "$WORKER_GID" "$WORKER"
else
  log "group $WORKER already exists"
fi

if ! id "$WORKER" >/dev/null 2>&1; then
  # No supplementary groups here deliberately -- the shared group is granted
  # below via `members`-equivalent (gpasswd), never via extraGroups on this
  # identity, so it exists only while hybrid dispatch is enabled on this host.
  useradd --system --uid "$WORKER_UID" --gid "$WORKER_GID" \
    --home-dir "$WORKER_HOME" --create-home \
    --shell /bin/bash "$WORKER"
else
  log "user $WORKER already exists"
fi
chmod 0700 "$WORKER_HOME"
chown "$WORKER:$WORKER" "$WORKER_HOME"

if ! getent group "$SHARED_GROUP" >/dev/null; then
  groupadd --system "$SHARED_GROUP"
else
  log "group $SHARED_GROUP already exists"
fi
gpasswd --add "$COORDINATOR" "$SHARED_GROUP" >/dev/null
gpasswd --add "$WORKER" "$SHARED_GROUP" >/dev/null

# ---- state/worktree/evidence roots ------------------------------------------
# Mirrors modules/system/hybrid-dispatch.nix's systemd.tmpfiles.rules exactly
# (0710 traversal-only root, 2770 setgid jointly-writable workspace).
log "Workspace directories"
install -d -m 0710 -o "$COORDINATOR" -g "$SHARED_GROUP" "$STATE_ROOT"
install -d -m 2770 -o "$COORDINATOR" -g "$SHARED_GROUP" "$WORKTREE_ROOT"
install -d -m 2770 -o "$COORDINATOR" -g "$SHARED_GROUP" "$EVIDENCE_ROOT"
install -d -m 0700 -o "$WORKER" -g "$WORKER" "$WORKER_HOME/.local"
install -d -m 0700 -o "$WORKER" -g "$WORKER" "$WORKER_HOME/.local/share"
install -d -m 0700 -o "$WORKER" -g "$WORKER" "$WORKER_HOME/.local/share/opencode"

# ---- worker OpenCode credential ---------------------------------------------
# Never the coordinator's own key -- see docs/runbooks/hybrid-dispatch.md
# "Credentialing the worker". Decrypted straight to the worker's uid; this
# script (running as root) never leaves the plaintext under $COORDINATOR.
log "Worker OpenCode credential"
if [ ! -f "$AGE_KEY_FILE" ]; then
  die "no age key at $AGE_KEY_FILE -- set AGE_KEY_FILE to an identity that can decrypt $SECRETS_FILE"
fi
tmp_auth="$(mktemp)"
trap 'rm -f "$tmp_auth"' EXIT
if ! SOPS_AGE_KEY_FILE="$AGE_KEY_FILE" sops -d --extract '["opencode"]["agentworker"]["auth"]' \
  "$SECRETS_FILE" >"$tmp_auth" 2>/dev/null; then
  die "sops could not decrypt opencode.agentworker.auth from $SECRETS_FILE with $AGE_KEY_FILE"
fi
install -m 0600 -o "$WORKER" -g "$WORKER" "$tmp_auth" "$AUTH_JSON_PATH"
rm -f "$tmp_auth"
trap - EXIT
log "wrote $AUTH_JSON_PATH"

# ---- sudo: coordinator -> worker, scoped to opencode + test -----------------
# Mirrors security.sudo.extraConfig / extraRules in hybrid-dispatch.nix. A
# blanket ALL would let the coordinator launder arbitrary commands through the
# worker identity and let a compromised worker escalate back out.
log "Sudoers"
SUDOERS_FILE="/etc/sudoers.d/agentworker-hybrid-dispatch"
# `command -v test` returns bash's builtin match ("test", no path) rather than
# /usr/bin/test -- builtins win over externals for that lookup. sudoers needs
# a fully-qualified path, so resolve the external binary explicitly.
TEST_BIN="$(type -P test || true)"
[ -n "$TEST_BIN" ] || die "no external test(1) binary found on PATH (coreutils)"
tmp_sudoers="$(mktemp)"
cat >"$tmp_sudoers" <<EOF
Defaults>${WORKER} umask = 0002, umask_override
${COORDINATOR} ALL=(${WORKER}) NOPASSWD:SETENV: ${OPENCODE_BIN}
${COORDINATOR} ALL=(${WORKER}) NOPASSWD: ${TEST_BIN}
EOF
visudo -cf "$tmp_sudoers" || die "generated sudoers file failed validation"
install -m 0440 -o root -g root "$tmp_sudoers" "$SUDOERS_FILE"
rm -f "$tmp_sudoers"

log "Done. Verify with:"
log "  sudo $GITOPS_ROOT/scripts/check-worker-containment.sh $WORKER $WORKTREE_ROOT /projects/dev"
log "(pass AGENTOPS_COORDINATOR_USER=$COORDINATOR and AGENTOPS_SHARED_GROUP=$SHARED_GROUP if not run as $COORDINATOR)"
log "Dispatch by pointing hybrid_dispatch.py at the live agentops checkout, e.g.:"
log "  AGENTOPS_HYBRID_POLICY=/projects/dev/agentops/templates/dispatch/hybrid/hybrid-dispatch.v1.json \\"
log "  AGENTOPS_HYBRID_WORKER_CONFIG=/projects/dev/agentops/templates/dispatch/hybrid/opencode.hybrid.json \\"
log "  python templates/dispatch/scripts/hybrid_dispatch.py --worker-user $WORKER ..."
