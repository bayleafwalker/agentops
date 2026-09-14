"""operator-projection generate | serve | text [--url | --file]."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import contract, render_text  # noqa: F401  (contract asserts renderer coverage on import)
from .generate import generate
from .serve import serve
from .sources import GitHubRest, open_authority

BAKED = Path("/app/registry.yaml")


def default_registry() -> Path:
    return BAKED if BAKED.is_file() else Path(__file__).resolve().parents[2] / "registry.yaml"


def build(registry_path: Path, profile_path: str | None) -> Callable[[], dict]:
    """All configuration is by file; a missing credential or profile yields BLIND panels, never a crash."""
    registry = yaml.safe_load(registry_path.read_text())
    stamp = registry_path.with_suffix(".commit")
    registry["commit"] = stamp.read_text().strip() if stamp.is_file() else "uncommitted"
    token = Path(os.environ.get("OPERATOR_PROJECTION_GITHUB_TOKEN_FILE", "/run/github/token"))
    git = GitHubRest(registry["repos"], token.read_text().strip() if token.exists() else None)
    authority = None
    if profile_path and Path(profile_path).is_file():
        try:
            authority = open_authority(yaml.safe_load(Path(profile_path).read_text()))
        except ImportError:
            authority = None
    return lambda: generate(git, authority, registry, datetime.now(timezone.utc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="operator-projection", description=__doc__)
    parser.add_argument("--registry", type=Path, default=default_registry())
    parser.add_argument("--profile", default=os.environ.get("OPERATOR_PROJECTION_PROFILE"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generate").add_argument("--out", type=Path, help="write v1.json and v1.txt here instead of JSON to stdout")
    commands.add_parser("serve").add_argument("--port", type=int, default=8080)
    source = commands.add_parser("text").add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="a served projection, e.g. https://ops.example")
    source.add_argument("--file", type=Path)
    args = parser.parse_args(argv)
    if args.command == "text":
        url = args.url and (args.url if args.url.endswith(".json") else args.url.rstrip("/") + "/v1.json")
        raw = urllib.request.urlopen(url, timeout=30).read() if url else args.file.read_bytes()
        sys.stdout.write(render_text.render(json.loads(raw)))
        return 0
    produce = build(args.registry, args.profile)
    if args.command == "serve":
        serve(produce, int(os.environ.get("OPERATOR_PROJECTION_CADENCE_S", "900")), port=args.port)
        return 0
    doc = produce()
    if args.out is None:
        sys.stdout.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "v1.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    (args.out / "v1.txt").write_text(render_text.render(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
