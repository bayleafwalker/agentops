# Authority UUID and principal binding — contract for R1

**Item:** agentops #2308 (sprint #551, cross-repo-dogfood-r0)
**Status:** contract, for `vuoro` served auth to implement in R1
**Supersedes in practice:** the split between `repo_id` and `authority_repo_uuid`

## 1. What is true today, measured

Verified against `vuoro-service` at `1b1ac48` and `sprintctl` 0.3.4 on 2026-08-29.

**Isolation on the work path is real, and it is a string comparison.**
`app.py:369` rejects any `repo_scoped` operation with `repo-unauthorized` unless
`identity.authorizes_repo(repo_id)`. `authorizes_repo` is
`ALL_REPOS in self.repo_ids or repo_id in self.repo_ids` — set membership over
human-readable names. Two further call sites gate dispatch-enqueue provenance
(`execution_provenance.py:86`) and project binding (`project_binding.py:240`).
`composition.py:626` refuses to load an identity that holds any `work:` authority
without `repo_ids`, so the boundary cannot be left empty by accident.

**The repo id is client-supplied.** `InvocationContext.repo_id` is documented as
"Client-supplied, not identity-bound: the repository this invocation targets. The
identity only authorizes it; it does not dictate it."

**The authority UUID is not checked by anything served.** `_authority_repo_uuid()`
(`sprintctl/commands/operations.py:551`) globs `*.dispatch.json` in the caller's own
repository, requires exactly one, and parses `authority_repo_uuid`, falling back to
`repo_id`. `authority.py:465` compares it against `store.authority_repo_uuid` **only
when that is set**, which happens solely on the legacy direct-PostgreSQL path. On
the served path there is no repo-UUID registry to compare against, by design.

**Therefore the UUID is self-asserted.** On 2026-08-29 `homelab-analytics` was
unblocked by minting one locally (`dda443a`) and committing it. Nothing verified it,
nothing could have rejected it, and any other value would have worked identically.
It is today a local identifier for the command journal, not an authority.

**And the sentinel is a real hole.** `ALL_REPOS = "*"` in an identity's `repo_ids`
authorizes every repository, present and future — including repositories that do not
exist yet at the time the grant is written. The code comment notes this "matches how
the two production identities today are bound to a host, not a single repository."
A host-bound grant with `*` cannot express least privilege at all.

## 2. The contract

### 2.1 One immutable authority UUID

A repository has exactly one **authority UUID**: an opaque, immutable UUID that
names the repository as an authority tenant. It is minted once and never changes —
not on rename, not on fork, not on transfer between forges, not on migration between
hosts. Nothing may be derived from it, and it carries no structure to parse.

Repository names, slugs, directory names and forge paths become **display metadata**.
They may change freely and are never compared for an authorization decision.

`repo_id` and `authority_repo_uuid` collapse into this one field. The transition is
covered in §3.

### 2.2 The principal is bound to the UUID, not to the name

Served authorization binds the **authenticated principal** to a set of authority
UUIDs. `Identity.repo_ids` becomes a set of authority UUIDs, and `authorizes_repo`
compares UUIDs.

A caller-supplied repository identifier — name or UUID — is a **routing hint**. It
selects which tenant's data the invocation addresses. It is never the isolation
boundary. The boundary is: does the authenticated principal hold a grant for the
authority UUID this invocation resolves to?

This inverts today's trust. Today a caller names a repository and the server checks
that name against a list. Under this contract the server resolves the hint to an
authority UUID and checks the principal's grant against that UUID; an unresolvable
hint is rejected, and a resolvable hint the principal lacks a grant for is rejected.

### 2.3 The UUID is issued, not asserted

The authority UUID is **minted by the authority and recorded server-side**. A
client-supplied UUID that the authority does not know is rejected — it is not
created on first use, and it is not trusted because it appeared in a manifest.

This is the substantive change. It closes the hole in §1: today a repository can
mint any UUID and be believed. The manifest field becomes a *cache of an issued
value*, useful for offline command journalling and for detecting drift, and it is
never the source of truth.

Consequence for onboarding: minting is an explicit act with a principal attached —
who requested this tenant, and when. A repository that has never been issued a UUID
is unonboarded, and that is a detectable state rather than a silent one.

### 2.4 `*` is not a grant

The `ALL_REPOS` sentinel is removed from the authorization path. A principal holds
an enumerated set of authority UUIDs. A host that legitimately serves many
repositories enumerates them, and adding a repository is an explicit grant change.

Where a wildcard is genuinely needed (a platform-internal reconciler, say), it is a
distinct, named authority — not a value smuggled into the repository set, where it
is indistinguishable from an enumerated grant on inspection.

### 2.5 What must be rejected

An implementation satisfies this contract only if all of these fail closed:

| Case | Required outcome |
|---|---|
| Client supplies an authority UUID the authority never issued | rejected, `repo-unknown` |
| Client supplies a valid UUID the principal has no grant for | rejected, `repo-unauthorized` |
| Client supplies a routing hint that resolves to no tenant | rejected, `repo-unresolvable` |
| Identity holds a `work:` authority with an empty UUID set | refused at load, as today |
| Identity holds `*` in its UUID set | refused at load |
| Repository is renamed | every existing grant continues to work unchanged |
| Two repositories claim the same authority UUID | rejected; the UUID is unique per tenant |

The rename row is the one that proves the design: if renaming a repository breaks a
grant, the name was still the boundary.

## 3. Migration

Because the UUID becomes issued rather than asserted, existing self-minted values
cannot simply be trusted forward.

1. **Ratify what exists.** Eight repositories carry a UUID today — six as
   `authority_repo_uuid`, two (`sprintctl`, `vuoro`) as a legacy UUID `repo_id`. Each
   is adopted as that repository's issued authority UUID by an explicit act recorded
   with a principal, or replaced. Nothing is grandfathered by silence.
2. **Issue for the rest.** Ten manifests have no UUID by either route. See
   `docs/assessments/dispatch-manifest-classification-2026-08-29.md`; three of those
   repositories are unsound and one is broken, and issuing a UUID for them is not the
   first problem to solve.
3. **Dual-read, then cut.** Served auth accepts a name or a UUID as the routing hint
   throughout the transition, resolving both to the authority UUID, and logs which
   form each caller used. When no caller sends a name, names stop resolving.
4. **Drift is reported, not repaired.** A manifest whose cached UUID disagrees with
   the issued one is drift for `align-and-converge` to report — the
   `schema-migration-by-rerun` gate. Silent correction would re-open exactly the hole
   §2.3 closes.

## 4. What this contract does not decide

- **Where the registry lives.** It must be server-side and authoritative; whether it
  is a table in the work database, a control-plane service, or part of the identity
  registry is an R1 implementation decision.
- **How minting is authorized.** Creating a tenant is a privileged act and needs its
  own authority; naming it is outside this contract.
- **Project bindings spanning repositories.** `project_binding.py` already requires an
  identity authorized for *every* repository in a project; that generalizes to UUIDs
  unchanged, and the project's own identity is a separate question.
- **Whether the work database re-keys on UUID.** Rows may keep a name column as
  display metadata; only the authorization path is specified here.

## 5. Why this is worth the migration

The failure this prevents is not hypothetical. On 2026-08-28 a repository with no
backend marker resolved `backend=local` and wrote a sprint and four items to a local
database while appearing to succeed — a repository left the shared authority and
nothing noticed. On 2026-08-29 a repository minted its own authority UUID and was
believed. In both cases the system's answer to "which tenant is this, and may you act
on it?" was assembled from strings the client supplied about itself.

An issued, immutable UUID bound to an authenticated principal makes that question
answerable by the authority alone, which is the only place it can be answered
correctly.
