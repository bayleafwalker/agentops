#!/usr/bin/env bash
# Run only this actual-image evaluator proof against a wrapper-owned disposable PG16 cluster.
# Credentials are generated per attempt. No shared authority or database is used.
# PostgreSQL is pinned below; fsync is off, so this tests client/service recovery.
# Run under timeout --foreground -k 30s 900s. A hard-kill orphan must be inspected
# using its owner PID/start-time marker; this runner never sweeps other clusters.
set -euo pipefail

PG_NIX_REF="github:NixOS/nixpkgs/b4fd65b198c599cbe814fcb9f42d25d021595ec9#postgresql_16"

if ! command -v initdb >/dev/null 2>&1 || ! command -v pg_ctl >/dev/null 2>&1; then
  command -v nix >/dev/null 2>&1 || { echo "pg-disposable-tests: need postgres binaries or nix" >&2; exit 2; }
  exec nix shell "$PG_NIX_REF" -c "$0" "$@"
fi

# libpq reads every PG* variable (PGHOSTADDR, PGSERVICE, PGSERVICEFILE, PGPASSFILE,
# PGSSL*, ...), and any of them could redirect a connection. Clear them all so
# only the explicit host, port and URLs below are used.
while IFS= read -r name; do unset "$name"; done < <(compgen -e | grep '^PG' || true)

script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
proof_python="${S4_PROOF_PYTHON:?Set S4_PROOF_PYTHON to the qualified installed-release Python interpreter}"
# The server socket path must stay under the unix-socket length limit (~107
# bytes), so fall back to /tmp when TMPDIR is long.
tmp_base=/tmp
[ "${#tmp_base}" -le 60 ] || tmp_base=/tmp
work="$(mktemp -d "$tmp_base/sprintctl-pg.XXXXXX")"
# Owner file for the sweep: this script's pid and its start time (field 22 of
# /proc/<pid>/stat, counted after the last ")"), or "unknown" without /proc.
owner_start=unknown
if [ -r "/proc/$$/stat" ]; then
  owner_stat="$(cat "/proc/$$/stat")"
  read -ra owner_fields <<<"${owner_stat##*) }"
  owner_start="${owner_fields[19]:-unknown}"
fi
echo "$$ $owner_start" >"$work/owner.tmp"
mv "$work/owner.tmp" "$work/owner"
data="$work/data"
sock="$work/sock"
mkdir -p "$sock"
started=0

cleanup() {
  local rc=$?
  # A second signal must not abort cleanup halfway and leave the dir behind.
  trap '' INT TERM
  set +e
  if [ "$rc" != 0 ] && [ -s "$work/server.log" ]; then
    echo "pg-disposable-tests: server log (exit $rc):" >&2
    tail -n 40 "$work/server.log" >&2
  fi
  if [ "$started" = 1 ]; then
    pg_ctl -D "$data" -m immediate -w stop >/dev/null 2>&1
  fi
  # Belt and braces: a postmaster that outlived pg_ctl still owns this pid file.
  if [ -f "$data/postmaster.pid" ]; then
    kill -9 "$(head -1 "$data/postmaster.pid")" 2>/dev/null
  fi
  rm -rf "$work"
  exit $rc
}
trap cleanup EXIT
trap 'exit 130' INT TERM

port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
test_pw="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
probe_pw="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"

initdb -D "$data" -U pgadmin_disposable --auth-local=trust --auth-host=scram-sha-256 -E UTF8 >/dev/null
pg_ctl -D "$data" -w -l "$work/server.log" \
  -o "-c listen_addresses=127.0.0.1 -c port=$port -c unix_socket_directories=$sock -c fsync=off" start >/dev/null
started=1

admin() { psql -X -v ON_ERROR_STOP=1 -h "$sock" -p "$port" -U pgadmin_disposable -d postgres "$@"; }

server_version_num="$(admin -tA -c 'SHOW server_version_num')"
server_version="$(admin -tA -c 'SHOW server_version')"
case "$server_version_num" in
  16[0-9][0-9][0-9][0-9]) ;;
  *) echo "pg-disposable-tests: FAIL: server_version_num $server_version_num is not PostgreSQL major 16" >&2; exit 1 ;;
esac
echo "pg-disposable-tests: PostgreSQL server version $server_version (server_version_num $server_version_num)"

audit_migration_pw="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
audit_runtime_pw="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
admin >/dev/null <<SQL
CREATE ROLE s4_work_migration LOGIN PASSWORD '$test_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE s4_work_runtime LOGIN PASSWORD '$probe_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE s4_audit_migration LOGIN PASSWORD '$audit_migration_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE s4_audit_runtime LOGIN PASSWORD '$audit_runtime_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE s4_seed_disposable;
COMMENT ON DATABASE s4_seed_disposable IS 'sprintctl:disposable-integration-test';
GRANT CONNECT, CREATE ON DATABASE s4_seed_disposable TO s4_work_migration, s4_audit_migration;
GRANT CONNECT ON DATABASE s4_seed_disposable TO s4_work_runtime, s4_audit_runtime;
SQL
export S4_DISPOSABLE_ADMIN_DSN="postgresql://pgadmin_disposable@/postgres?host=$sock&port=$port"
export S4_DISPOSABLE_PORT="$port"
export S4_WORK_MIGRATION_PASSWORD="$test_pw" S4_WORK_RUNTIME_PASSWORD="$probe_pw"
export S4_AUDIT_MIGRATION_PASSWORD="$audit_migration_pw" S4_AUDIT_RUNTIME_PASSWORD="$audit_runtime_pw"
cd "$repo_root"
unset PYTHONPATH PYTHONHOME PYTHONUSERBASE PYTHONSTARTUP
"$proof_python" -I "$script_dir/s4-image-evaluator-proof.py"
