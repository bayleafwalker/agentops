"""Launcher provenance, immutable conflicts and the derived consumer boundary."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import session_binding as subject
import profile_comparison
import schema_check


def invoke(tmp_path, harness=None, event=None):
    args = [sys.executable, str(ROOT / 'scripts/session_binding.py'),
            '--bindings-dir', str(tmp_path), '--no-publish']
    if harness:
        args += ['--harness', harness]
    return subprocess.run(args, input=json.dumps(event or {'session_id': 'native-session',
                          'cwd': str(ROOT), 'source': 'startup'}),
                          text=True, capture_output=True)


def load(tmp_path):
    return json.loads((tmp_path / 'native-session.json').read_text())


def test_launcher_is_explicit_and_event_claims_and_id_shape_cannot_select_it(tmp_path):
    result = invoke(tmp_path, event={'session_id': '01a-native-looking', 'harness': 'codex',
                                   'source': 'claude-hook', 'cwd': str(ROOT)})
    assert result.returncode == 0
    value = json.loads((tmp_path / '01a-native-looking.json').read_text())
    assert value['harness']['name'] == 'unknown'
    assert value['attribution'] == {'source': 'unknown-session', 'actor': 'unknown-session',
                                   'resolution_source': 'unobserved'}
    assert value['entitlement']['settings_sources'] == []
    assert schema_check.validate(value, json.loads((ROOT / 'schemas/session-binding.schema.json').read_text())) == []


def test_codex_records_its_declared_config_and_resume_is_byte_stable(tmp_path):
    assert invoke(tmp_path, 'codex').returncode == 0
    path = tmp_path / 'native-session.json'
    before = path.read_bytes()
    value = load(tmp_path)
    assert value['harness']['name'] == 'codex'
    assert value['attribution']['source'] == value['attribution']['actor'] == 'codex-hook'
    assert all('/.claude/' not in s['path'] for s in value['entitlement']['settings_sources'])
    assert any(s['path'].endswith('/.codex/hooks.json') for s in value['entitlement']['settings_sources'])
    assert invoke(tmp_path, 'codex', {'session_id': 'native-session', 'cwd': str(ROOT),
                                    'source': 'resume'}).returncode == 0
    assert path.read_bytes() == before


def test_actor_uses_os_identity_and_publish_uses_launcher_not_event_claim(tmp_path):
    with patch.dict(os.environ, {'USER': 'spoofed', 'LOGNAME': 'spoofed'}):
        value = subject.build({'session_id': 's', 'cwd': str(ROOT), 'source': 'claude-hook'},
                              records_dir=ROOT/'environment-record', harness='codex')
    assert value['actor']['os_user'] != 'spoofed'
    for harness in ['codex', 'claude', 'unknown']:
        value = subject.build({'session_id': 's', 'cwd': str(ROOT), 'source': 'forged-hook'},
                              records_dir=ROOT/'environment-record', harness=harness)
        with patch.object(subject.auditctl_resolve, 'resolve', return_value='/fixture/auditctl'), \
             patch.object(subject.subprocess, 'run') as run:
            subject.publish(value)
        args = run.call_args.args[0]
        collector = harness + '-hook' if harness != 'unknown' else 'unknown-session'
        assert args[args.index('--source') + 1] == args[args.index('--actor') + 1] == collector
        assert json.loads(args[args.index('--metadata') + 1])['harness'] == harness
        assert 'forged-hook' not in args


def test_conflict_is_digest_bound_idempotent_and_preserves_original_bytes(tmp_path):
    assert invoke(tmp_path, 'claude').returncode == 0
    path = tmp_path / 'native-session.json'
    before = path.read_bytes()
    for _ in range(2):
        result = invoke(tmp_path, 'codex')
        assert result.returncode == 1
        assert 'harness' in result.stderr and 'contradiction' in result.stderr
    assert path.read_bytes() == before
    files = list((tmp_path / '.attribution-conflicts/native-session').glob('*.json'))
    assert len(files) == 1
    conflict = json.loads(files[0].read_text())
    assert conflict['binding_sha256'] == hashlib.sha256(before).hexdigest()
    observation = subject.read_attribution(path, load(tmp_path))
    assert observation['harness'] == 'unknown' and observation['status'] == 'contradicted'
    assert observation['recorded_harness'] == 'claude'
    assert observation['conflicts'][0]['observed_harness'] == 'codex'
    assert observation['conflicts'][0]['binding_matches'] is True
    # If a historical file is subsequently tampered with, the flag stays explicit.
    path.write_bytes(before + b' ')
    assert subject.read_attribution(path, load(tmp_path))['conflicts'][0]['binding_matches'] is False


def test_legacy_attribution_is_unverified_and_missing_opencode_remains_unobserved(tmp_path):
    assert invoke(tmp_path, 'claude').returncode == 0
    value = load(tmp_path)
    value.pop('attribution')
    path = tmp_path / 'native-session.json'
    path.write_text(json.dumps(value))
    assert subject.read_attribution(path, value)['harness'] == 'unknown'
    result = subprocess.run([sys.executable, str(ROOT/'scripts/session_binding.py'),
                             '--bindings-dir', str(tmp_path), '--read-attribution', 'absent-opencode'],
                            capture_output=True, text=True)
    assert json.loads(result.stdout) == {'harness': 'unknown', 'status': 'unobserved', 'binding_found': False}
    assert not (tmp_path / 'absent-opencode.json').exists()


def test_derived_join_never_groups_contradicted_codex_as_claude(tmp_path):
    invoke(tmp_path, 'claude')
    invoke(tmp_path, 'codex')
    report = profile_comparison.build_report([{'session_id': 'native-session', 'ts': '2026-10-10T06:00:00Z',
                                              'minutes': 10}], [], tmp_path)
    assert report['rows'][0]['harness'] == 'unknown'
    assert report['rows'][0]['attribution_status'] == 'contradicted'


def test_wrapper_preserves_event_and_pins_each_launcher(tmp_path):
    stub = tmp_path / 'agentops'
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ATTR_ARGS"\ncat > "$ATTR_EVENT"\n')
    stub.chmod(0o755)
    args_path, event_path = tmp_path/'args', tmp_path/'event'
    env = {**os.environ, 'PATH': str(tmp_path) + ':' + os.environ['PATH'],
           'ATTR_ARGS': str(args_path), 'ATTR_EVENT': str(event_path)}
    payload = '{"session_id":"fixture","harness":"forged","source":"resume"}\n'
    for name, expected in [('session-binding.sh', 'claude'), ('codex-session-binding.sh', 'codex')]:
        result = subprocess.run([str(ROOT/'hooks'/name)], input=payload, env=env,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert args_path.read_text().splitlines() == ['session-binding', '--harness', expected]
        assert event_path.read_text() == payload


def test_parallel_different_launchers_preserve_one_binding_and_a_conflict(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda harness: invoke(tmp_path, harness), ['claude', 'codex']))
    assert sorted(result.returncode for result in results) == [0, 1]
    value = load(tmp_path)
    result = subject.read_attribution(tmp_path/'native-session.json', value)
    assert result['status'] == 'contradicted' and result['harness'] == 'unknown'
    assert len(result['conflicts']) == 1 and result['conflicts'][0]['binding_matches']


def test_known_native_legacy_join_reports_missing_profile_and_unobserved_attribution(tmp_path):
    invoke(tmp_path, 'claude')
    value = load(tmp_path)
    value.pop('instructions')
    value.pop('attribution')
    (tmp_path/'native-session.json').write_text(json.dumps(value))
    invoke(tmp_path, 'codex')
    report = profile_comparison.build_report([{'session_id': 'native-session',
                                             'ts': '2026-10-10T06:00:00Z', 'minutes': 10}], [], tmp_path)
    assert report['rows'] == [] and report['no_profile'] == 1
    assert report['session_attributions']['native-session']['harness'] == 'unknown'
    assert report['session_attributions']['native-session']['status'] == 'contradicted'
