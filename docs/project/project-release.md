# Project release and evidence packages

`project.toml` and the member repositories remain authoritative.  A
`project-release/v1` descriptor is an immutable, Git-derived portability
description: it records the home binding commit and raw bytes digest, the
ordered member topology, selected member commits, document hashes, and an
exact durability proof for each member.

The descriptor creator requires every member to declare a credential-free
canonical HTTPS `repository` and a canonical `default_ref`.  Existing v1
bindings may omit those fields and continue to work with render/materialize;
they cannot create a portable release until the binding is explicitly
completed.

Supported workflows are:

1. `create` independently verifies each declared remote ref in an empty
   temporary bare repository; a caller-supplied verifier is only a test
   double and its exact proof is checked.
2. Create standalone Git bundles with `pack`, verify their bytes and exact
   advertised selected commits with `verify-package`, and use that evidence
   for a rebuild plan.  Ancestor-only bundle proofs are not modeled by v1.

`verify-package` requires the exact descriptor it is bound to and an explicit
source host when emitting a receipt; package members, bundle heads, document
hashes, and descriptor/topology digests are checked before verification is
reported.

The dependency-free entry point is
`templates/dispatch/scripts/project_release.py`.  Its commands are
`create`, `verify` (also accepted as `verify-remote`), `pack`,
`verify-package`, and `rebuild-plan`; every file-producing command requires an
explicit output path and refuses to overwrite it.

`rebuild-plan` validates evidence and reports missing members/documents/proofs;
it never creates a project folder, lock, worktree, or Git ref.  Filesystem
copying is not synchronization, and local `origin/*` tracking refs or an
object-only local commit do not prove portability.

`materialize_project.py rebuild` consumes a descriptor (and optionally a
verified package) directly; it does not accept a local project file as
authority. It preflights canonical Git anchors and origin URLs, acquires
transaction-scoped private refs, creates exact detached/branch worktrees, and
records release provenance in the marker and context. It never renders member
documents. Existing release-pinned instances refuse legacy `sync` and
`refresh-context`; use a new descriptor for a changed release.

Replication receipts record what a verifier observed at a time and may state
`pinned` or `expires` retention intent.  They do not prove persistence,
signature, remote retention enforcement, or a distributed lock.

This slice deliberately does not add automatic materializer rebuild,
registry/storage APIs, uploads/downloads, ref pushes, cloud authority,
signatures, or cross-host lease semantics.  Git refs and explicitly verified
bundles remain the continuation boundary.
