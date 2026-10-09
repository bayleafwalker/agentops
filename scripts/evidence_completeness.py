#!/usr/bin/env python3
"""Read-only MI-1 completeness over an explicit sample and captured owner records.

This measures consistency of supplied records and artifacts, not authenticity,
check execution or whole-estate coverage. Missing invocations stay denominators.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/operator-projection/src'))
from operator_projection import reconstruction

CLASSES = ('capture_failure', 'unattributed_work', 'inaccessible_artifact',
           'missing_receipt', 'binding_conflict')


def known_text(value):
    return type(value) is str and bool(value.strip()) and value.strip().lower() not in ('unknown', 'unavailable')


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique)


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate input field')
        value[key] = item
    return value


def artifact_digest(root, artifact):
    path = (root / artifact['path']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('artifact outside sample root')
    data = path.read_bytes()
    if artifact.get('domain', 'file-bytes') == 'canonical-json':
        value = json.loads(data, object_pairs_hook=unique)
        for key in artifact.get('keys', []):
            value = value[key]
        data = reconstruction.canonical(value)
    elif artifact.get('domain', 'file-bytes') != 'file-bytes':
        raise ValueError('unsupported artifact digest domain')
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def measure(sample, records, root):
    if sample.get('schema') != 'evidence-completeness-sample/v1':
        raise ValueError('unsupported sample')
    entries = sample['entries']
    if len({e['id'] for e in entries}) != len(entries):
        raise ValueError('duplicate sample identity')
    runs = records['runs']
    if len({r['run_id'] for r in runs}) != len(runs):
        raise ValueError('duplicate owner run identity')
    indexed = {r['run_id']: r for r in runs}
    results = []
    for entry in entries:
        kind = entry['kind']
        if kind not in ('run', 'effect') or not entry.get('stratum'):
            raise ValueError('sample kind and stratum required')
        failures = set()
        if kind == 'run':
            run = indexed.get(entry.get('run_id'))
            if run is None:
                failures.add('capture_failure')
            else:
                profile = run.get('observed_profile')
                if (run.get('repo_id') != sample['repo_id'] or
                        any(not known_text(run.get(k)) for k in
                            ('principal_id', 'workspace_id', 'harness_id', 'harness_build', 'model_id', 'recipe_id')) or
                        type(profile) is not dict or
                        type(profile.get('instruction_digest')) is not str or
                        not re.fullmatch(r'sha256:[0-9a-f]{64}', profile['instruction_digest'])):
                    failures.add('unattributed_work')
                if not run.get('evidence'):
                    failures.add('capture_failure')
                evidence = {e['digest'] for e in run.get('evidence', [])}
                if not entry.get('artifacts'):
                    failures.add('inaccessible_artifact')
                for artifact in entry.get('artifacts', []):
                    try:
                        digest = artifact_digest(root, artifact)
                    except (OSError, ValueError, KeyError, TypeError, IndexError):
                        failures.add('inaccessible_artifact')
                        continue
                    if digest != artifact['digest']:
                        failures.add('inaccessible_artifact')
                    if artifact['digest'] not in evidence:
                        failures.add('binding_conflict')
        else:
            if not entry.get('artifacts'):
                failures.add('inaccessible_artifact')
            for artifact in entry.get('artifacts', []):
                try:
                    if artifact_digest(root, artifact) != artifact['digest']:
                        failures.add('inaccessible_artifact')
                except (OSError, ValueError, KeyError, TypeError, IndexError):
                    failures.add('inaccessible_artifact')
            try:
                capture_path = (root / entry['capture']).resolve()
                if not capture_path.is_relative_to(root.resolve()):
                    raise ValueError('capture outside sample root')
                capture = read_json(capture_path)
                if capture['repo_id'] != sample['repo_id'] or capture['intent_id'] != entry['intent_id']:
                    raise ValueError('effect capture identity mismatch')
                report = reconstruction.reconstruct(capture)
                if report['conflicts']:
                    failures.add('binding_conflict')
                if report['links']['effect_receipt']['status'] == 'missing':
                    failures.add('missing_receipt')
                if any(link != 'effect_receipt' for link in report['missing']):
                    failures.add('capture_failure')
            except (OSError, ValueError, KeyError, TypeError):
                failures.add('capture_failure')
        results.append(dict(id=entry['id'], kind=kind, stratum=entry['stratum'],
                            reconstructible=not failures, failures=sorted(failures)))
    groups = {}
    for kind in ('run', 'effect'):
        for stratum in sorted(set(sample.get('strata', [])) | {r['stratum'] for r in results}):
            rows = [r for r in results if r['kind'] == kind and r['stratum'] == stratum]
            n = len(rows)
            good = sum(r['reconstructible'] for r in rows)
            groups[kind + ':' + stratum] = dict(sample_size=n, reconstructible=good,
                percentage=round(100 * good / n, 2) if n else None,
                failure_counts={c: sum(c in r['failures'] for r in rows) for c in CLASSES})
    return dict(schema='evidence-completeness-report/v1', repo_id=sample['repo_id'],
        window=sample['window'], sample_size=len(entries), groups=groups, entries=results,
        assurance='consistency of supplied owner captures and artifact bytes; not authenticated live reads',
        scope=sample['scope'], whole_estate_claim=False,
        note='Failure classes overlap. Empty samples have null percentages; absent invocations count once.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = measure(read_json(args.sample), read_json(args.records), args.root)
    except (OSError, ValueError, KeyError, TypeError):
        print('completeness inputs refused', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
