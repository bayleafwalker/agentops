"""Offline P1 bundle export/verify: python -m operator_projection.bundle_cli."""
import argparse
import json
from pathlib import Path
import sys

from . import bundle


def read(path, limit):
    with path.open("rb") as stream:
        blob = stream.read(limit + 1)
    bundle.require(len(blob) <= limit, "input exceeds bound")
    return blob


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("export")
    create.add_argument("--capture", type=Path, required=True)
    create.add_argument("--artifact", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            blob = bundle.export(read(args.capture, bundle.CAPTURE_LIMIT), read(args.artifact, bundle.ARTIFACT_LIMIT))
            output = blob.decode("utf-8")
        else:
            output = json.dumps(bundle.verify(read(args.bundle, bundle.LIMIT)), ensure_ascii=False, allow_nan=False)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        # Avoid echoing sensitive source bytes, paths, URLs or raw exceptions.
        print("bundle refused: malformed, inconsistent or over limit", file=sys.stderr)
        return 2
    sys.stdout.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
