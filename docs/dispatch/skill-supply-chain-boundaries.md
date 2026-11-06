# Skill supply-chain boundaries: onboarding, inheritance and retirement

Status: published rules, source side only (AO-K04, agentops#2650, W41-R4),
2026-11-06. These rules and `scripts/skill_boundary.py` produce source-side
observations. They do not show that any native provider loaded a skill, and
they do not stand in for owner qualification.

## 1. What the inventory records

`python3 scripts/skill_boundary.py inventory skills/<name> [--load-path <rel>]`
prints a deterministic JSON report (`agentops-skill-boundary-inventory/v1`,
`qualification_status: source-observed-not-qualified`). The report has no
timestamps and its arrays are sorted, so the same tree gives the same bytes on
every run.

| Field | Meaning | Unknown handling |
|---|---|---|
| `source` | git origin URL, `HEAD` revision, skill-tree and whole-repository clean state | `unknown` when there is no git, no origin or a failed read. Not inferred. |
| `files[]`, `tree_sha256` | raw-byte SHA-256, size and executable bit of every file in the skill directory | A symlink or non-regular file stops the inventory with an error. |
| `frontmatter` | parsed values, a digest, and `permission_metadata` (every key except `name`, `description`, `license`, `version`, `argument-hint`) | Frontmatter the parser cannot read is `unparsed`. |
| `adapter_files` | vendor adapter metadata such as `agents/openai.yaml` | Digested like any other file. Never treated as authority. |
| `dependencies[]` | repository-relative path references and Markdown links in the body: `observed` (digested), `within-skill-tree`, `missing`, `dynamic`, `directory-not-digested`, `refused-path-escape`, `refused-symlink` | Anything that is not observed stays non-observed and is never treated as unused. |
| `dependency_coverage` | whether every declared path reference resolved, plus the dependency classes this tool cannot discover (executables, transitive imports, environment and credentials, network/MCP endpoints) | Classes it cannot discover are always `unknown`. |
| `load_paths[]` | repository links or copies such as `.claude/skills/<name>`, with their targets | `observation: source-link-only`. A link that escapes the repository is refused. |
| `provider_load_coverage` | `skill-tool`, `native-slash`, `preloaded`, `codex` (the #2488 coverage design) | Always `unknown` here. Only native observations, such as the session binding's `skill_coverage`, can change it. |
| `provenance` | publisher, trust class | `unknown` until an owner record supplies them. Repository location does not imply either. |
| `host_execution_policy` | not recorded | The policy and its revision belong to the grant, not to distribution metadata. |

## 2. Inheritance rule

A grant (`agentops-skill-boundary-grant/v1`) holds `host_policy_ref`,
`host_policy_revision`, `granted_by`, an optional
`accepted_dynamic_references` list and the exact inventory that was approved.
`compare --grant <file> --current <inventory>|--skill-dir <dir>` returns
`inherit: true` only when none of these denials apply. The exit code is 0 when
the skill inherits, 2 when it is denied and 1 when an input is malformed.

- **Changed bytes:** a file is added, removed or changed, or its mode changes
  (`file-*`); a dependency's digest changes (`dependency-bytes-changed`); or a
  dependency reference is added or removed.
- **Unverified content:** a dependency is missing, refused or a directory. A
  dynamic reference is accepted only if the grant lists that exact reference
  and the prior inventory already held it. Unparsed frontmatter is denied too.
- **Missing or changed origin:** the origin or revision is unknown, the
  origin has changed, or the skill tree is not clean.
- **Transitive closure unknown:** the skill references files outside its own
  tree, and either the revision has changed or the repository is not clean.
  Identical bytes in a new revision carry the grant over only for a
  self-contained skill.
- **Permission metadata:** any added, removed or changed non-inert
  frontmatter key, including keys this tool does not recognise. The tool
  cannot tell widening from narrowing, so every change counts as possible
  widening.
- **Identity:** the skill name is unknown or has changed, or the skill
  directory has moved.

Metadata never grants authority. A successful comparison passes on only the
grant's host policy reference. `allowed-tools` or adapter fields in the skill
add nothing, and changing them removes inheritance. A tampered grant is
malformed input: an inventory whose `tree_sha256` does not match its files,
or whose `qualification_status` was raised.

## 3. Onboarding checklist for a skill or a native provider package

1. Inventory the canonical source directory, not a link to it. Pass each
   harness load location as `--load-path`.
2. Resolve every `missing`, `refused-*` and `directory-not-digested`
   dependency, or remove the reference. Make each `dynamic` reference
   concrete, or have the host-policy owner list it in the grant as runtime
   data.
3. Record the required environment, tools and endpoints by name only. Never
   embed credentials in a skill, an adapter file or a grant.
4. The host-policy owner writes the grant with its own policy reference and
   revision. A skill's frontmatter, adapter file or package manifest is never
   the grant.
5. Native provider packaging (a Claude plugin or skill bundle, a Codex
   `agents/openai.yaml` and similar) is an adapter over the same canonical
   bytes. When native packaging replaces the adapter, inventory the native
   package as a new source and compare it against the existing grant. It
   inherits only if bytes, metadata and dependencies match. Otherwise it is
   onboarded fresh. Package install, OAuth consent and directory approval
   are separate decisions (#2639). None of them is a grant.
6. Live load evidence comes from native observation (#2481 Skill tool, #2488
   native slash). Until that evidence exists, `provider_load_coverage` stays
   `unknown`, and nobody claims the skill is loaded or unused.

## 4. Retirement rules

- Retire a grant when its inventory no longer matches. Do not edit the
  recorded inventory to match new bytes. Re-inventory and grant again.
- Retire a skill by removing its load-path links and canonical directory in
  the same change. A link left pointing at a removed or different source
  appears with `resolves_to_skill: false` and must be removed.
- Do not reuse a retired skill's grant for a successor that has the same name
  or directory. The successor goes through onboarding from scratch (O06:
  successor identity must not inherit authority).
- Retiring a vendor adapter, for example when native packaging replaces it,
  changes the file set, so the existing grant no longer matches. The
  replacement is onboarded under step 5.
- Retirement needs no global registry, compiled profile or retirement of the
  dispatch manifest (W41-R4 non-goals).

## 5. Ambiguities and the stricter readings chosen

- W41-R4 names `skills/recording-acceptance/SKILL.md`. On 2026-11-06 it does
  not exist in this repository or in the workstation skill directories, so
  the recorded evidence substitutes `workflow-artifact-capture`. The reason
  is in the evidence file.
- "Permission-widening" has no defined order across harness keys. Any change
  to a non-inert or unrecognised key denies inheritance.
- A new revision with identical bytes is not mentioned in W41-R4. It denies
  inheritance whenever the skill references files outside its own tree,
  because the transitive dependencies of those files are not digested.
- Synced skills resolve their references in the consuming repository. A
  dependency inventory is therefore valid only for the repository it was run
  in.

## 6. Evidence and limits

`docs/plans/agentops/evidence/2026-11-06-ao-k04-workflow-artifact-capture-inventory.json`
records one real run. It is a source-only observation: there is no live
provider-load proof, no owner qualification and no actual grant. Tests:
`scripts/tests/test_skill_boundary.py`. Still unproven: native-provider
acceptance, observed load paths, discovery of transitive and executable
dependencies, publisher and trust-class records, and a native package
replacing the adapter in practice.
