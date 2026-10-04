"""Independent failure histories for frozen, non-authoritative audit attribution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'query_audit_attribution.py'
spec = importlib.util.spec_from_file_location('query_audit_attribution', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(identity='ad:example', **changes):
    return dict(id=identity, type='workflow.session', payload_sha256='a'*64,
                metadata={'project': 'a-misleading-alias'},
                resolved_context={'repo_id': 'original', 'published_from': '/opaque/path'}, **changes)


def fixture(tmp_path, rows=None, *, scope='committed-only', source_id='source', source_repo='original'):
    rows = rows or [row()]
    raw = b''.join(json.dumps(item, sort_keys=True).encode()+b'\n' for item in rows)
    path=tmp_path/(source_id+'.ndjson'); path.write_bytes(raw)
    source=dict(source_id=source_id, source_repo_id=source_repo, kind='committed-shard',
                byte_count=len(raw), line_count=len(rows), sha256=hashlib.sha256(raw).hexdigest(),
                start_line=1, commit='1'*40, blob_id='2'*40)
    entry=dict(event_id=rows[0]['id'],source_id=source_id,line=1,
               raw_line_sha256=hashlib.sha256(raw.splitlines(keepends=True)[0]).hexdigest(),
               attributed_repo_id='target')
    overlay=dict(schema_version='audit-attribution-overlay/v1',scope=scope,sources=[source],entries=[entry])
    overlay['digest']='sha256:'+module.overlay_digest(overlay)
    overlay_path=tmp_path/(source_id+'.json');overlay_path.write_text(json.dumps(overlay))
    return path,overlay_path,overlay


def write_overlay(path, value):
    value['digest']='sha256:'+module.overlay_digest(value)
    path.write_text(json.dumps(value))
    return module.load_overlay(path)


def test_ordinary_command_preserves_original_payload_context_and_source_bytes(tmp_path):
    path, overlay_path, overlay=fixture(tmp_path)
    before=path.read_bytes()
    result=subprocess.run([sys.executable,str(SCRIPT),'--overlay',str(overlay_path),'--source',f'source={path}','--events'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    output=json.loads(result.stdout);event=output['events'][0]
    assert event['original_event']==row()
    assert event['source_repo_id']=='original' and event['attributed_repo_id']=='target'
    assert path.read_bytes()==before
    assert output['coverage']=='committed-only'


def test_identical_physical_copies_are_verified_and_deduplicated(tmp_path):
    path,op,overlay=fixture(tmp_path)
    copy=tmp_path/'copy.ndjson';copy.write_bytes(path.read_bytes())
    result=module.query([module.load_overlay(op)],{'source':[path,copy]})
    assert result['unique_events']==1 and result['mapped_events']==1
    assert result['verified_copy_count']==2 and result['duplicate_records']==1


def test_alias_spelling_cannot_attribute_unmapped_events(tmp_path):
    path,op,overlay=fixture(tmp_path,[row(),row('ad:unmapped')])
    result=module.query([module.load_overlay(op)],{'source':[path]},include_events=True)
    event=next(r for r in result['events'] if r['event_id']=='ad:unmapped')
    assert event['attributed_repo_id']=='original' and not event['mapped']
    assert result['attributed_counts']=={'target':1}


def test_append_extension_is_preserved_but_not_silently_included(tmp_path):
    path,op,overlay=fixture(tmp_path)
    extension=json.dumps(row('ad:later')).encode()+b'\n';path.write_bytes(path.read_bytes()+extension)
    result=module.query([module.load_overlay(op)],{'source':[path]})
    assert result['unique_events']==1 and result['unparsed_bytes_beyond_snapshots']=={'source':True}
    assert path.read_bytes().endswith(extension)


@pytest.mark.parametrize('mutation',['bytes','missing','reordered'])
def test_source_binding_mismatch_fails_closed(tmp_path,mutation):
    path,op,overlay=fixture(tmp_path,[row(),row('ad:other')])
    raw=path.read_bytes()
    if mutation=='bytes':path.write_bytes(raw.replace(b'workflow.session',b'dispatch.exit'))
    elif mutation=='missing':path.unlink()
    else:path.write_bytes(b''.join(reversed(raw.splitlines(keepends=True))))
    with pytest.raises(module.AttributionError):module.query([module.load_overlay(op)],{'source':[path]})


def test_same_identity_with_conflicting_authored_copy_is_refused(tmp_path):
    a,ap,ao=fixture(tmp_path,source_id='a')
    b,bp,bo=fixture(tmp_path,[row(payload='different')],source_id='b')
    bo['entries']=[];write_overlay(bp,bo)
    with pytest.raises(module.AttributionError,match='conflicting physical'):
        module.query([module.load_overlay(ap),module.load_overlay(bp)],{'a':[a],'b':[b]})


@pytest.mark.parametrize('change',['unknown-field','wrong-line','wrong-id','wrong-digest','boolean-count','duplicate-id','bad-source-kind'])
def test_unknown_or_conflicting_mapping_never_becomes_success(tmp_path,change):
    path,op,o=fixture(tmp_path)
    if change=='unknown-field':o['invented']=True
    elif change=='wrong-line':o['entries'][0]['line']=2
    elif change=='wrong-id':o['entries'][0]['event_id']='ad:absent'
    elif change=='wrong-digest':o['entries'][0]['raw_line_sha256']='0'*64
    elif change=='boolean-count':o['sources'][0]['byte_count']=True
    elif change=='duplicate-id':o['entries'].append(dict(o['entries'][0]))
    else:o['sources'][0]['kind']='guessed-alias'
    with pytest.raises(module.AttributionError):
        checked=write_overlay(op,o);module.query([checked],{'source':[path]})


def test_overlay_digest_and_duplicate_json_fields_are_refused(tmp_path):
    path,op,o=fixture(tmp_path)
    o['entries'][0]['attributed_repo_id']='forged';op.write_text(json.dumps(o))
    with pytest.raises(module.AttributionError,match='digest mismatch'):module.load_overlay(op)
    op.write_text('{"schema_version":"first","schema_version":"second"}')
    with pytest.raises(module.AttributionError):module.load_overlay(op)


def test_explicit_tail_requires_exact_committed_prefix_and_reports_full_selected_scope(tmp_path):
    path,op,public=fixture(tmp_path)
    prefix=path.read_bytes();extra=json.dumps(row('ad:tail'),sort_keys=True).encode()+b'\n';path.write_bytes(prefix+extra)
    tail=dict(schema_version='audit-attribution-overlay/v1',scope='protected-tail',sources=[dict(
        source_id='tail',source_repo_id='original',kind='uncommitted-tail',byte_count=len(prefix+extra),
        line_count=2,sha256=hashlib.sha256(prefix+extra).hexdigest(),start_line=2,prefix_source_id='source')],
        entries=[dict(event_id='ad:tail',source_id='tail',line=2,raw_line_sha256=hashlib.sha256(extra).hexdigest(),attributed_repo_id='target')])
    tp=tmp_path/'tail.json';checked=write_overlay(tp,tail)
    result=module.query([module.load_overlay(op),checked],{'source':[path],'tail':[path]})
    assert result['coverage']=='committed-and-explicit-protected-tail'
    assert result['mapped_events']==2 and result['unique_events']==2
    tail['sources'][0]['prefix_source_id']='unknown';checked=write_overlay(tp,tail)
    with pytest.raises(module.AttributionError,match='committed prefix'):
        module.query([module.load_overlay(op),checked],{'source':[path],'tail':[path]})


def test_unknown_supplied_source_and_bad_cli_refuse_without_partial_output(tmp_path):
    path,op,o=fixture(tmp_path)
    with pytest.raises(module.AttributionError):module.query([module.load_overlay(op)],{'source':[path],'extra':[path]})
    result=subprocess.run([sys.executable,str(SCRIPT),'--overlay',str(op),'--source','missing=absent'],capture_output=True,text=True)
    assert result.returncode==2 and not result.stdout
    assert json.loads(result.stderr)['status']=='cannot-determine'


def test_checked_in_committed_projection_is_paths_and_witnesses_free():
    root=SCRIPT.parents[1]
    path=root/'docs/evidence/audit-attribution/2026-09-28-through-30.committed.json'
    overlay=module.load_overlay(path)
    assert len(overlay['entries'])==1017 and overlay['scope']=='committed-only'
    text=path.read_text()
    assert '/projects/' not in text and '/home/' not in text
    assert 'session' not in text and 'toolu_' not in text and 'command' not in text
    assert {source['kind'] for source in overlay['sources']}=={'committed-shard'}
    supplied={source['source_id']:[root/'_artifacts/agentops/audit'/('events-'+source['source_id'][9:19]+'.ndjson')] for source in overlay['sources']}
    result=module.query([overlay],supplied)
    assert result['mapped_events']==1017
    assert result['attributed_counts']=={'vuoro-cloud':810,'vuoro':207}
    assert result['coverage']=='committed-only'


@pytest.mark.parametrize('fault',['overflow-number','lone-surrogate'])
def test_actual_cli_json_domain_failures_have_no_partial_output_or_source_mutation(tmp_path,fault):
    path,op,overlay=fixture(tmp_path);before=path.read_bytes()
    if fault=='overflow-number':
        text=json.dumps(overlay).replace('"byte_count": '+str(overlay['sources'][0]['byte_count']), '"byte_count": 1e400')
    else:
        overlay['entries'][0]['event_id']='\ud800';text=json.dumps(overlay)
    op.write_text(text)
    result=subprocess.run([sys.executable,str(SCRIPT),'--overlay',str(op),'--source',f'source={path}'],capture_output=True,text=True)
    assert result.returncode==2 and not result.stdout
    assert json.loads(result.stderr)['status']=='cannot-determine'
    assert path.read_bytes()==before
    with pytest.raises(module.AttributionError):module.load_overlay(op)
