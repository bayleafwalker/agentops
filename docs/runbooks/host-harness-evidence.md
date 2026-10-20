# Private host evidence store

`scripts/harness_evidence/store.py` implements the host-local opt-in artifact
boundary in the harness evidence policy. It captures only a named private
regular file after explicit `--opt-in`, writes a private per-object directory,
and returns a paired `evidence_uri` / `transcript_sha256`. No hook discovers or
captures transcripts automatically. Each artifact has its own creation time
and retention policy, even when two sessions retained identical bytes.

```bash
python3 scripts/harness_evidence/store.py capture /path/to/private-evidence \
  --session-id SESSION --opt-in
python3 scripts/harness_evidence/store.py verify FILE_URI SHA256
python3 scripts/harness_evidence/store.py cleanup
python3 scripts/harness_evidence/store.py delete OBJECT_UUID
```

The default root is `$XDG_STATE_HOME/agentops/harness-evidence`, falling back
to `~/.local/state/agentops/harness-evidence`. A global `--root` argument may
select an isolated store. Files are0600, directories0700; symlinks, hardlinks,
foreign ownership and public permissions are refused. A single artifact is
bounded to64MiB. Capture requires an existing private source file.

Retention defaults to30days from the stored creation timestamp. A positive
`--retention-days` sets a per-object period. `--keep-indefinitely` is an explicit
per-object opt-in and cannot be combined with a finite period. Cleanup uses
that immutable timestamp, never an access time or payload modification time.
Explicit deletion applies even to an indefinite object. Each successful delete
removes both payload and its reference record; retrieval then fails.

`verify` retrieves and re-hashes the bytes, matching both the caller's digest
and the private record, and prints only a verified flag and byte count.
The Python `retrieve` API returns verified bytes to its caller. Malformed
records, unexpected files and links are preserved and counted as refused;
the cleanup command exits2 if any refusal remains. It owns no files outside
its UUID directories, and does not rewrite another producer's immutable
capsules or audit records. The input source and any other copies retain their
own lifecycle. Caller-owned records that copied a reference need their own
expiry/tombstone handling before claiming all-copy deletion.

A scheduled cleanup service is delivered separately by gitops-nixos. Source
code and unit tests alone do not establish that a host timer is active.
This store does not resolve the separate retained database/restic-copy gap
tracked in agentops2828, and continuous native export remains disabled.
