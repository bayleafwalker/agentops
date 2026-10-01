#!/usr/bin/env bash
# SessionStart. Injects standing homelab facts that agents keep re-deriving
# wrongly from live probes.
#
# Why this exists: faststorage_layer had been reported as a finding in five
# separate sessions before 2026-09-09. It is a single-device scratch pool, it is
# DEGRADED, it is MEANT to be, and the owner has said outright that losing all
# of it is fine. The decision was already written down in
# appservice/docs/migrations/2026-08-30-offsite-backup-plan.md ("Caches -- ISOs,
# faststorage_layer, tdarr cache -- None, by design"), and an agent still quoted
# that table and reported the pool three times in the same session.
#
# A document nobody reads before probing does not prevent this; probing is how
# the wrong conclusion gets formed in the first place. So the fact ships at
# session start, next to the probe results it has to override.
#
# Kept separate from forge-context.sh deliberately: that hook is about forge and
# credentials, this one is about the homelab estate. Two concerns, two files,
# and neither breaks when the other's probes fail.
#
# Output was trimmed on 2026-09-16 (token economy). The rationale that used to
# be emitted, kept here instead: pool HEALTH and backup COVERAGE are the same
# question for a disposable pool, and the answer is recorded. faststorage_layer
# is ~43G single-SSD transcode/download scratch, permanently DEGRADED by design;
# deleting all of it is fine. Media offsite was priced (EUR 30-40/month) and
# rejected; site loss accepted. Reporting a non-finding trains the owner to
# skim. Policy: appservice/docs/migrations/2026-08-30-offsite-backup-plan.md;
# overlap audit: 2026-08-30-backup-coverage-audit.md. EPHEMERAL_POOLS lives in
# backup-status.sh and drives the exporter, NasPoolUnhealthy and the status page.
set -uo pipefail
cat >/dev/null 2>&1

OUT=$(cat <<'TXT'
== HOMELAB STANDING FACTS (decisions, not probes) ==
Ephemeral by design -- never report health, SMART, topology or missing backup as findings:
truenas faststorage_layer (single-disk scratch, permanently DEGRADED), /projects/models, /projects/bindery-vm, ISOs, tdarr cache.
Media: Movies (vault/media) and Series (storage_layer/media) are re-acquirable -- no paid backup, never more than one copy; Music is irreplaceable and IS backed up.
Encoded as EPHEMERAL_POOLS in backup-status; if a surface flags one, fix the encoding.
Backup truth: backups.apps.kotona.app; appservice docs/scripts/rebuild/backup_coverage_baseline.yaml
TXT
)

jq -n --arg c "$OUT" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
exit 0
