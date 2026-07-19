# Deterministic project rendering

`templates/dispatch/scripts/render_project.py` materializes the project-binding
contract without adding a runtime project service or changing standalone
repositories. It acts only when given a canonical `project.toml`.

## Inputs and mapping

The canonical project file lives at the home repository root. Member repositories
resolve as siblings under the workspace root (the home repository's parent):

- baseline/full fragments: `<home>/.project/sources/*.md`, sorted lexically;
- member override: `<member>/.agents/overlays/<repo_id>.project-overrides.md`;
- generated output: `<member>/.agents/project.generated.md`;
- pointer: one sentinel-delimited block in `<member>/AGENTS.md`.

There is no hidden golden-child source map. Repository and source locations come
only from `project.toml` plus the accepted fixed layout above; this keeps the
projection reproducible on hosts that have no personal maintenance skill.

`render: baseline` selects fragments tagged `baseline`; `render: full` selects
fragments tagged `full`. The selected bodies are concatenated in lexical order,
then the member override is appended. `render: none` produces no output and
removes only previously agentops-managed output and pointer blocks.

The provenance digest is SHA-256 over the raw bytes of the selected source files
in render order, followed by the member override bytes when present. Including
frontmatter and the override makes any authored input change stale the prior
render. Timestamps and filesystem paths are excluded.

## Check and apply

From the agentops repository, or with the script's absolute path:

```bash
python templates/dispatch/scripts/render_project.py check \
  --project /projects/dev/<home-repo>/project.toml

python templates/dispatch/scripts/render_project.py check \
  --project /projects/dev/<home-repo>/project.toml \
  --apply
```

`check` is the Tier-0 hook surface. Exit `0` means every generated file and
pointer is current, exit `1` means a member finding requires attention, and exit
`2` means the project contract could not be parsed or an apply was unsafe.
Findings distinguish:

- `stale`: the current source-bundle hash differs from the generated header;
- `hand-edited`: the hash is current but deterministic output differs;
- `missing` or `unexpected`: managed output does not match the member's render
  mode;
- `invalid` or `conflict`: the tool cannot safely interpret or replace a path.

Before writing, `--apply` refuses uncommitted changes in `project.toml`, project
sources, member overrides, `AGENTS.md`, or generated output. This keeps authored
changes and mechanical projection changes reviewable as separate commits.

## Commit workflow

1. Commit changes to `project.toml`, `.project/sources/`, or a member override in
   their owning repository.
2. Run `check --apply`.
3. Review every member diff.
4. In each changed member repository, commit only `AGENTS.md` and
   `.agents/project.generated.md` with a `chore(render)` commit.
5. Run `check` again from the home repository.

Do not hand-edit generated output. Use the canonical `golden-child` skill only
when a real semantic ownership or precedence conflict cannot be expressed as
project baseline followed by an additive member override.
