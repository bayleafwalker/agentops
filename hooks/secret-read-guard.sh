#!/usr/bin/env bash
# PreToolUse/Bash. Refuses commands that would print secret material into the
# transcript.
#
# Written 2026-09-09 after this session's own planner subagent read
# ~/.config/Code/User/History/.../cluster-secrets snapshot to VERIFY that the
# file held live secrets -- and in doing so put 13 live values into an agent
# transcript that had never contained them. The investigation created the
# exposure it was investigating. No malice and no carelessness: it was reading
# a file to check a claim, which is the single most normal thing an agent does.
#
# SCOPE, stated honestly. This is a guardrail against ACCIDENT, not a control
# against an adversary. It pattern-matches the command string; anything that
# reads bytes through a language runtime, renames a variable, or base64s in a
# subshell walks straight past it. It exists because the failure it addresses
# was accidental, and accidents match patterns.
#
# It also only sees the Bash tool. The Read tool is covered by permissions, not
# by this.
set -uo pipefail
EVENT="$(cat 2>/dev/null || true)"

# FAIL CLOSED. An earlier version exited 0 when jq was absent, so the guard
# silently disappeared on any host without it -- a control that reports nothing
# and blocks nothing, which is this estate's signature defect.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: secret-read-guard cannot run because jq is missing, so it cannot judge this command. Failing closed. Install jq, or re-issue with SECRET_READ_APPROVED=1 if you have confirmed with the operator that this command prints no secret material."}}'
  exit 0
fi
CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // ""' 2>/dev/null)"
[ -z "$CMD" ] && exit 0

deny() {
  jq -n --arg why "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",
    permissionDecision:"deny",permissionDecisionReason:$why}}'
  exit 0
}

# An explicit, auditable escape hatch. Requires the operator to have asked for
# the value in this turn -- not a flag an agent should set on its own judgement.
case "$CMD" in *SECRET_READ_APPROVED=1*) exit 0 ;; esac

# RULES. Narrowed 2026-09-09 after an adversarial review found the first
# version was net-harmful: it denied `kubectl get secret -A -o json | jq
# .metadata.name` (listing NAMES, the first command of any investigation), it
# denied the very remediation its own message advised, it denied merely WRITING
# the string into a runbook -- and it ALLOWED `sops -d file > /tmp/x`, which
# lands cleartext in a directory the Read tool can read. A guard that blocks
# ordinary work gets switched off, and one with a blessed laundering path is
# worse than none.
#
# So: few rules, each aimed at a command whose ONLY outcome is secret bytes on
# stdout or on disk. Listing names and keys is never blocked. This does not
# attempt completeness -- `kubectl exec -- env`, `helm get values`,
# `kubectl describe secret` and `-o go-template` all still print values and are
# NOT caught. The durable control is that there is nothing left to read, not
# this file.

is_read_target() {  # $1 = path fragment; true only if a reader ACTS on it
  # Only the portion BEFORE any redirect counts. `cat /new/key >> keys.txt` is
  # the operator ADDING an identity -- a write to a guarded path, not a read of
  # one -- and the first version denied it, which is the single command needed
  # to unblock every rotation in this estate.
  local pre="${CMD%%>*}"
  printf '%s' "$pre" | grep -qE "(^|[|;&]|[[:space:]])(cat|less|more|head|tail|xxd|strings|od|base64|cp|rsync|tar|zip)([[:space:]]+-[^[:space:]]+)*[[:space:]]+[^|;&]*$1"
}

# 1. Content reads of the local-history store. Mentioning the path, listing it,
#    counting it, or scripting its deletion are all fine -- only reading the
#    bytes is not.
if is_read_target 'Code/User/History'; then
  deny "BLOCKED: reading ~/.config/Code/User/History contents. It holds cleartext snapshots of SOPS-decrypted files; on 2026-09-09 reading one put 13 live values into a transcript.

Listing, counting, stat-ing and DELETING it are not blocked. To compare values, hash them (sha256sum) and report key names."
fi

# 2. Private key material at rest, including ssh keys, which the first version
#    missed entirely -- ~/.ssh/id_ed25519_remote is itself in the history store.
if is_read_target '(\.ssh/id_|age-identity|sops/age/keys\.txt|\.agekey|talsecret)' \
   && ! printf '%s' "$CMD" | grep -qE 'public key|\.pub([[:space:]]|$)|age-keygen -y'; then
  deny "BLOCKED: reading private key material. Custody is the operator's; an agent never needs the bytes. Presence: ls/stat. Identity: age-keygen -y, or grep 'public key:'. Appending a key you were given is not a read and is not blocked."
fi

# 3. SOPS/age/gpg decryption whose output is bytes you keep -- stdout, a file,
#    or a subshell. `> /tmp/x` is NOT an exemption: that was the laundering
#    path. Digest-only pipelines are fine, and so is `sops updatekeys`, which
#    re-encrypts without ever exposing plaintext.
if printf '%s' "$CMD" | grep -qE '(^|[|;&[:space:]])(sops[[:space:]]+(-d|--decrypt|exec-env|exec-file)|age[[:space:]]+(-d|--decrypt)|gpg[[:space:]]+(-d|--decrypt))'; then
  case "$CMD" in
    *sha256sum*|*'| wc'*|*'|wc'*|*'grep -c'*|*'| yq'*'keys'*|*'| jq'*'keys'*) ;;
    *) deny "BLOCKED: this puts decrypted secret material where it persists (stdout, a file, or a variable). Redirecting to /tmp is NOT safer -- the Read tool can read /tmp.

Allowed: digests (| sha256sum), counts (| grep -c), key-name listings (| yq '.stringData | keys'), and sops updatekeys / sops set, which never expose plaintext. If you need a VALUE, you do not -- the operator reads it in their own shell." ;;
  esac
fi

# 4. Kubernetes Secret VALUES specifically. Narrow: only when .data is actually
#    dereferenced or decoded. Listing names, keys, or metadata is untouched.
if printf '%s' "$CMD" | grep -qE 'kubectl[^|]*get[[:space:]]+(secret|secrets)' \
   && printf '%s' "$CMD" | grep -qE "jsonpath[^|]*\.data\.|base64[[:space:]]+(-d|--decode)|go-template[^|]*\.data|custom-columns[^|]*\.data"; then
  case "$CMD" in
    *sha256sum*|*hashlib*|*'| wc'*|*'grep -c'*) ;;
    *) deny "BLOCKED: this dereferences Kubernetes Secret VALUES. Listing names and key names is not blocked. Compare digests instead and report key names." ;;
  esac
fi

exit 0
