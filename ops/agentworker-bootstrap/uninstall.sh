#!/usr/bin/env bash
# Reverse ops/agentworker-bootstrap/install.sh. Run this at NixOS cutover so the
# imperative bridge does not survive as unmanaged Arch-side state once
# gitops-nixos/hosts/workstation (hybridDispatch.workerUser = "agentworker") is
# applied for real.
#
# Must run as root. Does not touch /projects/dev or any coordinator checkout --
# only the worker identity, its workspace, credential, and sudoers grant.
set -euo pipefail

WORKER="agentworker"
SHARED_GROUP="agentdispatch"
COORDINATOR="${COORDINATOR_USER:-bayleaf}"
STATE_ROOT="/var/lib/agentops/hybrid-dispatch"

[ "$(id -u)" -eq 0 ] || { echo "must run as root (sudo $0)" >&2; exit 1; }

rm -f /etc/sudoers.d/agentworker-hybrid-dispatch
rm -rf "$STATE_ROOT"
id "$COORDINATOR" >/dev/null 2>&1 && gpasswd -d "$COORDINATOR" "$SHARED_GROUP" >/dev/null 2>&1 || true
if id "$WORKER" >/dev/null 2>&1; then
  userdel --remove "$WORKER" 2>/dev/null || userdel "$WORKER"
fi
getent group "$WORKER" >/dev/null && groupdel "$WORKER" || true
getent group "$SHARED_GROUP" >/dev/null && groupdel "$SHARED_GROUP" || true

echo "removed. bindery-core/agentops checkouts under /projects/dev were NOT touched."
