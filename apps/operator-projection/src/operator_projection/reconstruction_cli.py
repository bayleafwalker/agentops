"""Explicit reconstruction CLI; separate from the front-page generator."""
import json
import sys
from pathlib import Path

import yaml

from . import reconstruction
from .sources import open_authority


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate capture field")
        result[key] = value
    return result


def run(args, parser):
    if args.intent_id and not args.repo_id:
        parser.error("--repo-id is required with --intent-id")
    try:
        if args.snapshot:
            capture = json.loads(args.snapshot.read_text(), object_pairs_hook=unique_object)
            report = reconstruction.reconstruct(capture)
        else:
            authority = None
            if args.profile and Path(args.profile).is_file():
                authority = open_authority(yaml.safe_load(Path(args.profile).read_text()), reconstruction.READ_OPS)
            try:
                report = reconstruction.reconstruct(reconstruction.collect(authority, args.repo_id, args.intent_id), live=True)
            finally:
                if authority is not None:
                    authority.loop.run_until_complete(authority.client.aclose())
                    authority.loop.close()
    except (OSError, ValueError, ImportError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"reconstruction refused ({type(error).__name__})", file=sys.stderr)
        return 2
    sys.stdout.write(reconstruction.render_text(report) if args.text else json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0
