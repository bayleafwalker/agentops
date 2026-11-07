#!/usr/bin/env python3
"""Cross-tool schema catalog: `agentops schema-catalog [--check] [--stdout]`.

Scans the agentops repository and, read-only, sibling repositories for schema ids
that follow the ``name/vN`` convention (``handoff/v1``, ``credctl-intent/v1``,
``protected-effect-envelope/v1``) and writes ``docs/contracts/SCHEMA-CATALOG.md``:
which repository defines each id, which others only reference it, and a vocabulary
section for the shared terms lease, fence, attempt, receipt and qualification.

Definitions versus references (deterministic heuristics, no guessing):

* definition, ``schema-file`` -- a JSON Schema file (``*.schema.json`` or a JSON
  document with a top-level ``$schema``) whose ``$id`` ends in ``name.vN.schema.json``
  or ``name/vN``, or whose ``schema``/``schema_version``/``kind`` property carries
  ``"const": "name/vN"`` (or a one-value ``enum``);
* definition, ``constant`` -- an upper-case constant assigned the id in source code
  (``SCHEMA = "native-proposal-request/v1"``);
* definition, ``type-literal`` -- a TypeSpec/TypeScript property typed as the id
  literal (``schema: "operator-request/v1";``);
* definition, ``emitter`` (weaker) -- source code that writes the id into a
  ``schema``/``schema_version`` field of a literal it builds. It decides ownership
  only when no repository has a stronger definition;
* reference -- every other mention, and every mention in docs (``*.md`` and ``docs/``),
  plans, evidence, tests and fixtures. Only ids that some repository defines are catalogued.

An id defined by several repositories lists them all and is flagged "multiple
definers", unless the id carries a repository prefix (``sprintctl-``, ``credctl-``,
``cred-broker-``, ``sovite-``, ``vuoro-``, ``agentops-``) naming one of the definers,
which then owns it; the others are listed as non-owning definers. A root that does not
exist is reported as "not available", not an error.

Sources: a git root is read from tracked content only -- this agentops checkout from
its working tree (``git ls-files``), every other root from its upstream commit
(``main@{upstream}``, else ``origin/main``, else ``HEAD``; override with ``--ref``) --
so untracked or ignored local files never enter the scan and an unpulled sibling does
not hide upstream changes. The catalog records each sibling's source sha, which makes
drift visible to ``--check``. Only a non-git directory is walked. The ``vuoro`` root
is ``vuoro/contracts`` only.

The scan skips VCS, dependency, build and artifact directories and any file whose
name suggests secrets; it never prints file contents beyond the matched id.

``--check`` regenerates in memory and exits 1 when the committed catalog differs. It
is a local check: CI has no sibling checkouts, so it is not wired into CI.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("docs/contracts/SCHEMA-CATALOG.md")
DEV = Path("/projects/dev")

# label=path; label is the owning repository name used in the catalog.
DEFAULT_ROOTS: tuple[tuple[str, Path], ...] = (
    ("agentops", REPO_ROOT),
    ("sprintctl", DEV / "sprintctl"),
    ("vuoro", DEV / "vuoro" / "contracts"),
    ("cred-broker", DEV / "cred-broker"),
    ("sovite", DEV / "sovite"),
)

TERMS: tuple[str, ...] = ("lease", "fence", "attempt", "receipt", "qualification")

SKIP_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", "_artifacts", "worktrees",
    ".worktrees", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", ".tox", ".direnv", "result",
})
SECRET_NAME_PATTERNS = (
    ".env", ".env.*", "*.env", "*.secret*", "*secret*.json", "*.key", "*.pem", "*.p12",
    "*.pfx", "*.age", "*.token", "*.state", "id_rsa*", "id_ed25519*", "*credentials*",
)
SCAN_SUFFIXES = frozenset({
    ".py", ".json", ".tsp", ".ts", ".tsx", ".js", ".mjs", ".rs", ".go", ".md",
    ".yaml", ".yml", ".toml", ".sh",
})
CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".mjs", ".rs", ".go", ".tsp", ".sh"})
# Path components whose files can only reference an id: tests and fixtures, plus docs,
# plans and evidence (proposed schemas and recorded probes are not owned contracts).
TEST_DIR_NAMES = frozenset({
    "tests", "test", "fixtures", "__tests__", "testdata", "examples", "docs", "plans",
    "evidence",
})
TYPED_SUFFIXES = frozenset({".ts", ".tsx", ".tsp"})
MAX_FILE_BYTES = 2_000_000
GIT_TIMEOUT = 120
# An id named with a repository prefix belongs to that repository when it is among
# the definers; this breaks "multiple definers" ties such as a consumer's copy of a
# producer's constant.
PREFIX_OWNERS: tuple[tuple[str, str], ...] = (
    ("agentops-", "agentops"), ("cred-broker-", "cred-broker"), ("credctl-", "cred-broker"),
    ("sovite-", "sovite"), ("sovite.", "sovite"), ("sprintctl-", "sprintctl"),
    ("sprintctl.", "sprintctl"), ("vuoro-", "vuoro"),
)

ID_BODY = r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*/v[0-9]+"
ID_RE = re.compile(rf"^{ID_BODY}$")
MENTION_RE = re.compile(rf"(?<![\w./-])({ID_BODY})(?![\w/-])")
CONST_RE = re.compile(
    rf"""^\s*(?:export\s+)?(?:pub\s+)?(?:(?:const|static|readonly|final)\s+)*
        [A-Z][A-Z0-9_]*\s*(?::[^=\n]+)?=\s*(?:r|b)?["']({ID_BODY})["']""",
    re.VERBOSE | re.MULTILINE,
)
TYPE_LITERAL_RE = re.compile(
    rf"""^\s*(?:readonly\s+)?["']?(?:schema|schema_version|schemaVersion)["']?\??\s*:\s*
        ["']({ID_BODY})["']\s*[;,]?\s*$""",
    re.VERBOSE | re.MULTILINE,
)
EMITTER_RE = re.compile(rf"""["'](?:schema|schema_version|schemaVersion)["']\s*:\s*["']({ID_BODY})["']""")
SCHEMA_ID_TAIL_RE = re.compile(r"([a-z][a-z0-9._-]*?)\.(v[0-9]+)\.schema\.json$")
SCHEMA_ID_PATH_RE = re.compile(rf"(?:^|/)({ID_BODY})$")
SCHEMA_KEYS = frozenset({"schema", "schema_version", "schemaVersion", "kind"})
TYPE_DECL_RE = re.compile(
    r"""^\s*(?:export\s+)?(?:pub\s+)?(?:@\w+(?:\([^)]*\))?\s+)*
        (?:class|model|interface|type|enum|union|struct|scalar)\s+([A-Za-z_][A-Za-z0-9_]*)""",
    re.VERBOSE | re.MULTILINE,
)
STRONG_KINDS = ("schema-file", "constant", "type-literal")


@dataclass(frozen=True)
class Root:
    label: str
    path: Path
    # None: the agentops checkout reads its working tree, siblings their upstream.
    ref: str | None = None


@dataclass
class Scan:
    available: list[str] = field(default_factory=list)
    unavailable: list[tuple[str, str]] = field(default_factory=list)
    # id -> repo -> set of (kind, relpath)
    definitions: dict[str, dict[str, set[tuple[str, str]]]] = field(default_factory=dict)
    # id -> set of repos mentioning it
    mentions: dict[str, set[str]] = field(default_factory=dict)
    # term -> repo -> set of (type name, relpath)
    types: dict[str, dict[str, set[tuple[str, str]]]] = field(default_factory=dict)
    files_scanned: dict[str, int] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)


def is_secret_name(name: str) -> bool:
    lower = name.lower()
    return any(fnmatch.fnmatch(lower, pattern) for pattern in SECRET_NAME_PATTERNS)


def wanted(rel: PurePosixPath, size: int | None) -> bool:
    """Shared filter for every source: skip dirs, scanned suffixes, secret names, size."""
    if any(part in SKIP_DIRS for part in rel.parts[:-1]):
        return False
    if rel.suffix not in SCAN_SUFFIXES or is_secret_name(rel.name):
        return False
    return size is None or size <= MAX_FILE_BYTES


def git(path: Path, *args: str, stdin: bytes | None = None) -> bytes | None:
    """Read-only git query; None when git is unavailable or the command fails."""
    try:
        result = subprocess.run(["git", "-C", str(path), *args], input=stdin,
                                capture_output=True, timeout=GIT_TIMEOUT, check=False,
                                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0",
                                     "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def git_text(path: Path, *args: str) -> str | None:
    raw = git(path, *args)
    return raw.decode("utf-8", "replace").strip() if raw is not None else None


def is_git_root(path: Path) -> bool:
    return git_text(path, "rev-parse", "--is-inside-work-tree") == "true"


def resolve_ref(path: Path, ref: str) -> tuple[str, str] | None:
    """(display name, commit sha) for `upstream` (main@{upstream}, else origin/main,
    else HEAD) or any explicit revision."""
    candidates = ["main@{upstream}", "origin/main", "HEAD"] if ref == "upstream" else [ref]
    for candidate in candidates:
        sha = git_text(path, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}")
        if sha:
            name = candidate
            if candidate == "main@{upstream}":
                name = git_text(path, "rev-parse", "--abbrev-ref", candidate) or candidate
            return name, sha
    return None


def walk_files(root: Path):
    """Non-git roots only: every regular file, without following symlinks."""
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
                continue
            rel = PurePosixPath(entry.relative_to(root).as_posix())
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if wanted(rel, size):
                yield rel, entry


def worktree_files(root: Path):
    """Tracked files only (`git ls-files`), read from disk: untracked and ignored local
    clutter never enters the scan."""
    listing = git(root, "ls-files", "-z", "--cached")
    for name in sorted(filter(None, (listing or b"").decode("utf-8", "replace").split("\0"))):
        rel = PurePosixPath(name)
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        if wanted(rel, path.stat().st_size):
            yield rel, path


def read_sources(root: "Root", exclude: frozenset[str]):
    """Yield (relpath, text) for every scannable file of the root, plus a description
    of the source. Git roots read tracked content (working tree or a commit); only a
    non-git directory is walked."""
    if not is_git_root(root.path):
        return "directory walk", (
            (rel, path.read_text(encoding="utf-8")) for rel, path in walk_files(root.path)
            if rel.as_posix() not in exclude and readable(path))
    ref = root.ref or ("worktree" if root.path.resolve() == REPO_ROOT else "upstream")
    if ref == "worktree":
        return "working tree, tracked files", (
            (rel, path.read_text(encoding="utf-8")) for rel, path in worktree_files(root.path)
            if rel.as_posix() not in exclude and readable(path))
    resolved = resolve_ref(root.path, ref)
    if resolved is None:
        return f"unresolvable ref {ref}", iter(())
    name, sha = resolved
    return f"{name} @ {sha[:12]}", tree_files(root.path, sha, exclude)


def readable(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True


def tree_files(root: Path, sha: str, exclude: frozenset[str]):
    """Blobs of the commit's subtree for this root (a root may be a subdirectory, such
    as vuoro/contracts), read with `git ls-tree` and `git cat-file --batch`."""
    prefix = git_text(root, "rev-parse", "--show-prefix") or ""
    # From the top level: run inside a subdirectory, ls-tree would also apply that
    # subdirectory as a path filter inside the already-narrowed tree.
    top = Path(git_text(root, "rev-parse", "--show-toplevel") or root)
    listing = git(top, "ls-tree", "-r", "-z", "--long", f"{sha}:{prefix}")
    blobs: list[tuple[PurePosixPath, str]] = []
    for entry in filter(None, (listing or b"").decode("utf-8", "replace").split("\0")):
        meta, _, name = entry.partition("\t")
        mode, kind, blob, size = meta.split()
        if kind != "blob" or mode == "120000":
            continue
        rel = PurePosixPath(name)
        if wanted(rel, int(size)) and rel.as_posix() not in exclude:
            blobs.append((rel, blob))
    blobs.sort()
    if not blobs:
        return
    raw = git(root, "cat-file", "--batch", stdin="".join(f"{b}\n" for _, b in blobs).encode())
    if raw is None:
        return
    offset = 0
    for rel, _ in blobs:
        header_end = raw.index(b"\n", offset)
        size = int(raw[offset:header_end].split()[2])
        body = raw[header_end + 1: header_end + 1 + size]
        offset = header_end + 1 + size + 1
        try:
            yield rel, body.decode("utf-8")
        except UnicodeDecodeError:
            continue


def is_reference_only(rel: PurePosixPath) -> bool:
    """Docs, tests and fixtures can only reference an id, never define it."""
    if rel.suffix == ".md":
        return True
    parts = rel.parts[:-1]
    if any(part in TEST_DIR_NAMES for part in parts):
        return True
    name = rel.name
    return name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".spec.ts", "_test.go"))


def schema_id_from_dollar_id(value: str) -> str | None:
    match = SCHEMA_ID_TAIL_RE.search(value)
    if match:
        candidate = f"{match.group(1)}/{match.group(2)}"
        return candidate if ID_RE.match(candidate) else None
    match = SCHEMA_ID_PATH_RE.search(value)
    return match.group(1) if match else None


def schema_file_ids(document: object) -> set[str]:
    found: set[str] = set()
    if isinstance(document, dict):
        dollar_id = document.get("$id")
        if isinstance(dollar_id, str):
            derived = schema_id_from_dollar_id(dollar_id)
            if derived:
                found.add(derived)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in SCHEMA_KEYS and isinstance(value, dict):
                    const = value.get("const")
                    if isinstance(const, str) and ID_RE.match(const):
                        found.add(const)
                    enum = value.get("enum")
                    if isinstance(enum, list) and len(enum) == 1 and isinstance(enum[0], str) \
                            and ID_RE.match(enum[0]):
                        found.add(enum[0])
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return found


def scan_root(root: Root, scan: Scan, exclude: frozenset[str] = frozenset()) -> None:
    count = 0
    source, files = read_sources(root, exclude)
    scan.sources[root.label] = source
    for rel, text in files:
        count += 1
        relstr = rel.as_posix()
        for match in MENTION_RE.finditer(text):
            scan.mentions.setdefault(match.group(1), set()).add(root.label)
        if is_reference_only(rel):
            continue
        found: set[tuple[str, str]] = set()
        if rel.suffix == ".json":
            if rel.name.endswith(".schema.json") or '"$schema"' in text:
                try:
                    document = json.loads(text)
                except ValueError:
                    document = None
                if rel.name.endswith(".schema.json") or (
                        isinstance(document, dict) and "$schema" in document):
                    found |= {(sid, "schema-file") for sid in schema_file_ids(document)}
        elif rel.suffix in CODE_SUFFIXES:
            found |= {(m.group(1), "constant") for m in CONST_RE.finditer(text)}
            if rel.suffix in TYPED_SUFFIXES:
                found |= {(m.group(1), "type-literal") for m in TYPE_LITERAL_RE.finditer(text)}
            if rel.suffix != ".tsp":
                found |= {(m.group(1), "emitter") for m in EMITTER_RE.finditer(text)}
            for match in TYPE_DECL_RE.finditer(text):
                name = match.group(1)
                for term in TERMS:
                    if term in type_words(name):
                        scan.types.setdefault(term, {}).setdefault(root.label, set()).add(
                            (name, relstr))
        for sid, kind in found:
            scan.definitions.setdefault(sid, {}).setdefault(root.label, set()).add((kind, relstr))
    scan.files_scanned[root.label] = count


def run_scan(roots: list[Root], exclude: frozenset[Path] = frozenset()) -> Scan:
    """Scan every available root; ``exclude`` (absolute paths) keeps the catalog and
    this script out of their own input, so regeneration is idempotent."""
    scan = Scan()
    for root in roots:
        if root.path.is_dir():
            scan.available.append(root.label)
            base = root.path.resolve()
            rels = frozenset(p.resolve().relative_to(base).as_posix() for p in exclude
                             if p.resolve().is_relative_to(base))
            scan_root(root, scan, rels)
        else:
            scan.unavailable.append((root.label, str(root.path)))
    return scan


def strongest(entries: set[tuple[str, str]]) -> bool:
    return any(kind in STRONG_KINDS for kind, _ in entries)


def owners_of(sid: str, per_repo: dict[str, set[tuple[str, str]]]) -> list[str]:
    """Repos with a strong definition (else every emitter), narrowed to the repo the
    id's prefix names when that repo is among them."""
    strong = sorted(repo for repo, entries in per_repo.items() if strongest(entries))
    candidates = strong or sorted(per_repo)
    if len(candidates) > 1:
        for prefix, repo in PREFIX_OWNERS:
            if sid.startswith(prefix) and repo in candidates:
                return [repo]
    return candidates


def primary_path(entries: set[tuple[str, str]]) -> str:
    """The defining path for a repo: strongest kind first, then lexical order."""
    rank = {kind: index for index, kind in enumerate((*STRONG_KINDS, "emitter"))}
    return sorted(entries, key=lambda e: (rank.get(e[0], 99), e[1]))[0][1]


def id_name(sid: str) -> str:
    return sid.rsplit("/", 1)[0]


def term_in_id(term: str, sid: str) -> bool:
    return term in re.split(r"[._-]", id_name(sid))


def type_words(name: str) -> list[str]:
    """`WorkerExecutionLease` -> ["worker", "execution", "lease"]; `Release` stays one word."""
    return [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+", name)]


def head_noun(term: str, sid: str) -> bool:
    """The id names the term itself: `lease/v1` or `<qualifier>-lease/v1`."""
    return re.split(r"[._-]", id_name(sid))[-1] == term


def owning_definition(repo: str, term: str, heads: dict, id_repos: dict, type_repos: dict,
                      scan: Scan) -> str:
    """Path of the repo's defining id (head-noun id first, then shortest id), else its
    type named for the term (exact name first)."""
    if repo in heads:
        sid, path = sorted(heads[repo], key=lambda d: (len(d[0]), d[0]))[0]
        return f"{repo}: `{path}` (`{sid}`)"
    if repo in id_repos:
        sid = sorted(id_repos[repo], key=lambda s: (len(s), s))[0]
        return f"{repo}: `{primary_path(scan.definitions[sid][repo])}` (`{sid}`)"
    name, path = sorted(type_repos[repo],
                        key=lambda e: (type_words(e[0])[-1] != term, len(e[0]), e))[0]
    return f"{repo}: `{path}` (type `{name}`)"


def vocabulary(scan: Scan) -> list[dict]:
    rows = []
    for term in TERMS:
        id_repos: dict[str, list[str]] = {}
        heads: dict[str, list[tuple[str, str]]] = {}
        for sid in sorted(scan.definitions):
            if not term_in_id(term, sid):
                continue
            per_repo = scan.definitions[sid]
            for repo in owners_of(sid, per_repo):
                id_repos.setdefault(repo, []).append(sid)
                if head_noun(term, sid):
                    heads.setdefault(repo, []).append((sid, primary_path(per_repo[repo])))
        type_repos = {repo: sorted(entries) for repo, entries in scan.types.get(term, {}).items()}
        repos = sorted(set(id_repos) | set(type_repos))
        # Types named for the term itself (`Lease`, `WorkerExecutionLease`) also claim it.
        head_types = {repo for repo, entries in type_repos.items()
                      if any(type_words(name)[-1] == term for name, _ in entries)}
        claimants = sorted(set(heads) | head_types)
        if not repos:
            owner = "no definitions found"
        elif len(repos) == 1 or (len(heads) == 1 and claimants == sorted(heads)):
            owner = owning_definition(repos[0] if len(repos) == 1 else next(iter(heads)),
                                      term, heads, id_repos, type_repos, scan)
        else:
            owner = "owner undetermined (" + ", ".join(claimants or repos) + ")"
        rows.append({
            "term": term,
            "repos": repos,
            "id_repos": {repo: sids for repo, sids in sorted(id_repos.items())},
            "type_repos": type_repos,
            "owner": owner,
        })
    return rows


def render(scan: Scan, roots: list[Root], date: str | None) -> str:
    lines = [
        "# Schema catalog",
        "",
        "<!-- Generated by scripts/schema_catalog.py. Do not edit by hand. -->",
        "",
        "Generated by `scripts/schema_catalog.py`; regenerate with "
        "`python3 scripts/schema_catalog.py` from the agentops repository root, and verify "
        "with `python3 scripts/schema_catalog.py --check`. The check is local only: it needs "
        "the sibling checkouts, which CI does not have.",
        "",
    ]
    if date:
        lines += [f"Generated on {date}.", ""]
    lines += [
        "A definition is a JSON Schema `$id` or `const`, an upper-case source constant, or a "
        "TypeSpec/TypeScript literal-typed `schema` property; `emitter` (code that writes the id "
        "into a `schema` field it builds) counts only when no repository has a stronger "
        "definition. Among several definers, an id prefixed with a repository name "
        "(`sprintctl-`, `credctl-`, `cred-broker-`, `sovite-`, `vuoro-`, `agentops-`) is owned by "
        "that repository when it is one of them. Mentions in docs, plans, evidence, tests and "
        "fixtures are references.",
        "",
        "## Roots",
        "",
        "Git roots are read from tracked content only: agentops from its working tree "
        "(`git ls-files`), siblings from their upstream commit (`main@{upstream}`, else "
        "`origin/main`, else `HEAD`), so local clutter and unpulled checkouts do not change "
        "the catalog. The source sha makes sibling drift visible to `--check`. The vuoro root "
        "covers only `vuoro/contracts`, not the rest of the vuoro repository.",
        "",
        "| Repository | Status | Source | Files scanned | Ids defined |",
        "|---|---|---|---|---|",
    ]
    defined_count: dict[str, int] = {}
    for sid, per_repo in scan.definitions.items():
        for repo in owners_of(sid, per_repo):
            defined_count[repo] = defined_count.get(repo, 0) + 1
    unavailable = dict(scan.unavailable)
    for root in roots:
        if root.label in unavailable:
            lines.append(f"| {root.label} | not available | - | - | - |")
        else:
            lines.append(f"| {root.label} | scanned | {scan.sources.get(root.label, '-')} "
                         f"| {scan.files_scanned.get(root.label, 0)} "
                         f"| {defined_count.get(root.label, 0)} |")
    lines += ["", "Ids defined counts each id once per owning repository.", ""]

    multi = sorted(sid for sid, per in scan.definitions.items() if len(owners_of(sid, per)) > 1)
    lines += ["## Schema ids", "",
              f"{len(scan.definitions)} ids; {len(multi)} with multiple definers.", "",
              "| Id | Owner | Definition | Other definers (not owning) | Also referenced by | Flag |",
              "|---|---|---|---|---|---|"]
    for sid in sorted(scan.definitions):
        per_repo = scan.definitions[sid]
        owners = owners_of(sid, per_repo)

        def describe(repo: str) -> str:
            kinds = ", ".join(sorted({kind for kind, _ in per_repo[repo]}))
            return f"{repo}: `{primary_path(per_repo[repo])}` ({kinds})"

        definition = "<br>".join(describe(repo) for repo in owners)
        others = "<br>".join(describe(repo) for repo in sorted(set(per_repo) - set(owners)))
        refs = sorted(scan.mentions.get(sid, set()) - set(per_repo))
        flag = "multiple definers" if len(owners) > 1 else ""
        lines.append(f"| `{sid}` | {', '.join(owners)} | {definition} | {others or '-'} | "
                     f"{', '.join(refs) or '-'} | {flag} |")

    lines += ["", "## Vocabulary", "",
              "Repositories that define schema ids or types (class/model/interface/enum names) "
              "containing the term as a word. The owning definition is either the only "
              "repository with any such id or type, or the only repository naming an id or "
              "type for the term itself (`<qualifier>-<term>/vN`, `<Qualifier><Term>`) when it "
              "also defines such an id; anything else is marked owner undetermined.", "",
              "| Term | Repositories | Owning definition |", "|---|---|---|"]
    vocab = vocabulary(scan)
    for row in vocab:
        lines.append(f"| {row['term']} | {', '.join(row['repos']) or '-'} | {row['owner']} |")
    for row in vocab:
        lines += ["", f"### {row['term']}", ""]
        if not row["repos"]:
            lines.append("No ids or types found.")
            continue
        for repo in row["repos"]:
            sids = row["id_repos"].get(repo, [])
            types = row["type_repos"].get(repo, [])
            type_names = sorted({name for name, _ in types})
            lines.append(f"- {repo}: {len(sids)} ids"
                         + (f" ({', '.join(f'`{s}`' for s in sids)})" if sids else "")
                         + f"; {len(type_names)} types"
                         + (f" ({', '.join(f'`{t}`' for t in type_names)})" if type_names else ""))
    return "\n".join(lines) + "\n"


def parse_roots(values: list[str] | None, refs: list[str] | None = None) -> list[Root]:
    pairs = [(label, path) for label, path in DEFAULT_ROOTS] if not values else []
    for value in values or []:
        label, sep, path = value.partition("=")
        if not sep or not label or not path:
            raise SystemExit(f"schema-catalog: --root expects NAME=PATH, got {value!r}")
        pairs.append((label, Path(path).expanduser()))
    ref_by_label: dict[str, str] = {}
    for value in refs or []:
        label, sep, ref = value.partition("=")
        if not sep or not label or not ref:
            raise SystemExit(f"schema-catalog: --ref expects NAME=REF, got {value!r}")
        ref_by_label[label] = ref
    return [Root(label, path, ref_by_label.get(label)) for label, path in pairs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentops schema-catalog",
        description="Generate the cross-tool schema catalog (docs/contracts/SCHEMA-CATALOG.md) "
                    "from agentops and, read-only, sibling repositories.")
    parser.add_argument("--root", action="append", metavar="NAME=PATH",
                        help="repository to scan (repeatable; replaces the defaults: "
                             + ", ".join(f"{label}={path}" for label, path in DEFAULT_ROOTS) + ")")
    parser.add_argument("--ref", action="append", metavar="NAME=REF",
                        help="what to read for a git root: 'worktree' (tracked files on disk), "
                             "'upstream' (main@{upstream}, else origin/main, else HEAD) or any "
                             "revision; default worktree for this agentops checkout, upstream "
                             "for every other root")
    parser.add_argument("--output", type=Path, default=None,
                        help=f"catalog path (default: <agentops>/{DEFAULT_OUTPUT})")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed catalog differs from regeneration "
                             "(local check; needs the sibling checkouts)")
    parser.add_argument("--date", help="stamp this date in the header (omitted by default)")
    args = parser.parse_args(argv)

    roots = parse_roots(args.root, args.ref)
    output = args.output or REPO_ROOT / DEFAULT_OUTPUT
    text = render(run_scan(roots, frozenset({output.resolve(), Path(__file__).resolve()})), roots, args.date)
    if args.stdout:
        sys.stdout.write(text)
        return 0
    if args.check:
        try:
            current = output.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current != text:
            print(f"schema-catalog: {output} is stale; run python3 scripts/schema_catalog.py",
                  file=sys.stderr)
            return 1
        print(f"schema-catalog: {output} is current")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"schema-catalog: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
