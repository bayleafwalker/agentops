"""Missing invocations and changed bytes must reduce an explicit denominator."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_completeness import measure, read_json


def setup_sample(tmp_path):
    artifact = tmp_path / 'result.txt'
    artifact.write_text('actual result\n')
    digest = 'sha256:' + hashlib.sha256(artifact.read_bytes()).hexdigest()
    sample = dict(schema='evidence-completeness-sample/v1', repo_id='agentops',
        window={'since': '2026-10-08', 'until': '2026-10-09'}, scope='two expected invocations',
        strata=['proof', 'ordinary'], entries=[
            dict(id='captured', kind='run', stratum='proof', run_id='r1',
                artifacts=[dict(path='result.txt', digest=digest)]),
            dict(id='never-captured', kind='run', stratum='proof', run_id=None)])
    run = dict(run_id='r1', repo_id='agentops', principal_id='native:producer',
        workspace_id='native:workspace', harness_id='native', harness_build='1', model_id='model',
        recipe_id='recipe', observed_profile={'instruction_digest': 'sha256:' + 'a' * 64},
        evidence=[dict(digest=digest)])
    return sample, dict(runs=[run])


def test_missing_invocation_counts_and_empty_window_has_no_percentage(tmp_path):
    sample, records = setup_sample(tmp_path)
    report = measure(sample, records, tmp_path)
    assert report['groups']['run:proof']['sample_size'] == 2
    assert report['groups']['run:proof']['percentage'] == 50
    assert report['groups']['run:proof']['failure_counts']['capture_failure'] == 1
    assert report['groups']['run:ordinary']['sample_size'] == 0
    assert report['groups']['run:ordinary']['percentage'] is None
    assert report['whole_estate_claim'] is False


def test_changed_or_inaccessible_bytes_never_count_as_reconstructible(tmp_path):
    sample, records = setup_sample(tmp_path)
    (tmp_path / 'result.txt').write_text('changed despite same reference\n')
    report = measure(sample, records, tmp_path)
    assert report['groups']['run:proof']['reconstructible'] == 0
    assert report['entries'][0]['failures'] == ['inaccessible_artifact']
    (tmp_path / 'result.txt').unlink()
    assert measure(sample, records, tmp_path)['entries'][0]['failures'] == ['inaccessible_artifact']


def test_forged_complete_label_does_not_replace_missing_owner_receipt(tmp_path):
    sample, records = setup_sample(tmp_path)
    root = Path(__file__).resolve().parents[2]
    capture = json.loads((root / 'docs/evidence/2026-10-09-mi1-protected-proof/live-owner-reconstruction-capture.json').read_text())
    capture['status'] = 'complete'
    capture['results']['work.effect.get-v1']['value']['intent']['application'] = None
    (tmp_path / 'effect.json').write_text(json.dumps(capture))
    sample['entries'] = [dict(id='effect', kind='effect', stratum='proof',
        intent_id=capture['intent_id'], capture='effect.json', artifacts=sample['entries'][0]['artifacts'])]
    report = measure(sample, records, tmp_path)
    assert report['groups']['effect:proof']['reconstructible'] == 0
    assert report['entries'][0]['failures'] == ['missing_receipt']


def test_unknown_attribution_and_unbound_artifact_are_separate_failures(tmp_path):
    sample, records = setup_sample(tmp_path)
    records['runs'][0]['harness_build'] = 'unknown'
    records['runs'][0]['evidence'][0]['digest'] = 'sha256:' + '0' * 64
    assert measure(sample, records, tmp_path)['entries'][0]['failures'] == ['binding_conflict', 'unattributed_work']


@pytest.mark.parametrize('build', [True, 7, 'unavailable', '   '])
def test_missing_or_untyped_manifest_fact_is_not_attribution(tmp_path, build):
    sample, records = setup_sample(tmp_path)
    records['runs'][0]['harness_build'] = build
    assert measure(sample, records, tmp_path)['entries'][0]['failures'] == ['unattributed_work']


def test_duplicate_identity_and_path_escape_refuse_or_fail_closed(tmp_path):
    sample, records = setup_sample(tmp_path)
    sample['entries'][0]['artifacts'][0]['path'] = '../outside'
    assert 'inaccessible_artifact' in measure(sample, records, tmp_path)['entries'][0]['failures']
    sample['entries'].append(copy.deepcopy(sample['entries'][0]))
    with pytest.raises(ValueError):
        measure(sample, records, tmp_path)
    path = tmp_path / 'duplicate.json'
    path.write_text('{"runs":[],"runs":[{}]}')
    with pytest.raises(ValueError):
        read_json(path)
