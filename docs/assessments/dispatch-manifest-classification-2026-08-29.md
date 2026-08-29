# Dispatch manifest classification — 2026-08-29

**Item:** agentops #2309 (sprint #551, cross-repo-dogfood-r0)
**Question:** classify every dispatch manifest as executable, guidance-only or archived.

Eighteen manifests exist across `/projects/dev`. The declared `adoption_level` is
not by itself the answer: five manifests declare a level the repository cannot
actually sustain. The classification below is what each manifest *is*, with the
declaration recorded separately where the two disagree.

## Classification

| Repository | Declared | **Actual** | Why |
|---|---|---|---|
| appservice | dispatchable | **executable** | git ok, served, remote live |
| bindery-core | dispatchable | **executable** | git ok, served, remote live |
| homelab-analytics | dispatchable | **executable** | git ok, served, remote live; `authority_repo_uuid` minted 2026-08-29 (`dda443a`) |
| actionq | guidance-only | guidance-only | served, UUID present |
| agentops | guidance-only | guidance-only | served, UUID present |
| auditctl | guidance-only | guidance-only | served, UUID present |
| kctl | guidance-only | guidance-only | served, UUID present |
| sprintctl | guidance-only | guidance-only | served, legacy UUID `repo_id` |
| vuoro | guidance-only | guidance-only | served, legacy UUID `repo_id` |
| aligned-equity | guidance-only | guidance-only | served, no UUID — authority commands unavailable |
| actionq-dispatcher | guidance-only | guidance-only | served, no UUID — authority commands unavailable |
| scribectl | observable | observable | served, no UUID — authority commands unavailable |
| frontier-weave | observable | observable | served, no UUID; on the internal forge |
| **hostproto** | guidance-only | **archived** | GitHub repo archived 2026-08-28, read-only; split into six successors |
| **outctl** | guidance-only | **unsound** | no work-authority declaration |
| **local-inference** | guidance-only | **unsound** | no work authority, and no git remote at all |
| **homelab-gitops-template** | guidance-only | **unsound** | no work authority; template repo |
| **vuoro-bounded-output-starter** | guidance-only | **broken** | `.git` is an empty directory; manifest is `outctl.dispatch.json`, copied from another repo |

Three executable, eleven guidance-only or observable, one archived, three unsound,
one broken.

## The findings that matter

**1. Four manifests declare participation with no work authority.** `outctl`,
`local-inference`, `homelab-gitops-template` and `vuoro-bounded-output-starter`
have no `.sprintctl/backend.json` and no `SPRINTCTL_BACKEND` in `.envrc`. This is
the cred-broker defect exactly: sprintctl resolves `backend=local` from the working
directory and writes work to a local database **while appearing to succeed**.

`outctl` is the live one. It was pushed to on 2026-08-29, its manifest selects
`item-done` and `dispatch-build`, and any session closing an item there writes to
`~/.sprintctl/sprintctl.db` where nobody will find it. The other three are a
template, a local-only repo, and a broken checkout.

**2. `hostproto` is archived, and its six successors have no manifest at all.**
The repository was archived on GitHub on 2026-08-28 after its last push, and the
work split into `hostproto-a2a-worker`, `hostproto-dap-core`,
`hostproto-dap-debugpy`, `hostproto-dap-delve`, `hostproto-mcp-playwright` and
`hostproto-semantics` — all active, all pushed the same day. None of the six has a
dispatch manifest, a skills directory, or a work-authority marker. Wave 1 is
running with no dispatch participation, and the manifest classification cannot
follow the work because the work left the repository the manifest describes.

**3. `vuoro-bounded-output-starter` carries another repository's manifest.** The
file is named `outctl.dispatch.json`. `_authority_repo_uuid()` globs `*.dispatch.json`
and requires exactly one, so it resolves — against outctl's identity. The broken
`.git` masks this today by making every git-dependent operation fail first.

**4. Schema version is not tracking capability.** Six manifests are
`schema_version: 2`, twelve are `1`, and the split does not correspond to anything:
`homelab-analytics` is `1` and executable; `sprintctl` and `vuoro` are `2` but carry
a legacy UUID `repo_id` rather than the schema-2 `authority_repo_uuid` field. Three
`schema_version: 1` manifests (`aligned-equity`, `actionq-dispatcher`, `scribectl`)
have no UUID by either route and therefore cannot run authority commands at all —
the same gap `homelab-analytics` hit on 2026-08-29 and closed by minting one.

## Disposition

Classification is complete and answers #2309. The four unsound manifests and the
six unonboarded successors are **not** fixed here — each is a participation change
that belongs to the repository that owns it, and fixing them by hand is the
event-shaped bootstrap that §9.2a rejects.

They are the first corpus for `align-and-converge`
(`templates/dispatch/acceptance/align-and-converge.scenario.json`): a declared
participation, an actual state that disagrees, and a reconciliation that must report
the delta rather than assume the declaration is true. The
`silent-local-fallback-refused` gate is finding (1); `schema-migration-by-rerun` is
finding (4).
