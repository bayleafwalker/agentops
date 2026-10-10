"""Compare two supplied P1 captures: python -m operator_projection.comparison_cli."""
import argparse
import json
from pathlib import Path
import sys

from .comparison import compare, render_text
from .reconstruction_cli import unique_object


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args(argv)
    try:
        captures = [json.loads(path.read_text(), object_pairs_hook=unique_object) for path in (args.left, args.right)]
        report = compare(*captures)
    except (OSError, ValueError, ImportError, KeyError, TypeError, RecursionError) as error:
        print(f"comparison refused ({type(error).__name__})", file=sys.stderr)
        return 2
    sys.stdout.write(render_text(report) if args.text else json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
