"""Cross-attempt bindings, stale-source and no-authority histories."""
from copy import deepcopy
import hashlib
import json
import pytest
from operator_projection import comparison as c, reconstruction as p1
from operator_projection.comparison_cli import main
from test_reconstruction import protected_capture, intent

def competing_capture():
    doc=protected_capture();doc['intent_id']='effect_other';row=intent(doc)
    row['intent_id']=doc['intent_id'];row['run_id']='run_other';row['acceptance']['intent_id']=doc['intent_id']
    proof=row['acceptance']['verification'];proof['receipt']['intent_id']=doc['intent_id']
    proof['evidence_digest']='sha256:'+hashlib.sha256(p1.canonical(proof['receipt'])).hexdigest()
    doc['results'][p1.EFFECT]['arguments']['intent_id']=doc['intent_id'];return doc

def test_exact_comparison_never_chooses_or_settles():
    left,right=protected_capture(),competing_capture();before=deepcopy((left,right));report=c.compare(left,right)
    assert report['binding_status']=='exact' and not report['same_recorded_intent'] and report['recorded_run_relation']=='different'
    assert report['settlement_owner']=='Sprintctl' and not report['settlement_inferred'] and not report['authorizes_effects']
    assert not {'winner','chosen','terminal_status','decision','ready_to_settle'} & report.keys()
    assert report['candidates']['left']['links']['artifact']['value']['digest']==intent(left)['canonical_intent_digest']
    assert report['candidates']['right']['links']['verification_evidence']['value']['receipt']['intent_id']=='effect_other'
    assert all(v['freshness']['status']=='unknown' for v in report['candidates'].values());assert (left,right)==before

def test_stale_proposal_and_valid_candidate_remain_unordered():
    stale,valid=protected_capture(),competing_capture();intent(stale)['unified_diff']+='\n+changed-after-review\n';report=c.compare(stale,valid)
    assert report['candidates']['left']['stale_markers'] and report['candidates']['left']['reconstruction_status']=='conflict'
    assert not report['candidates']['right']['stale_markers'] and report['candidates']['right']['reconstruction_status']=='complete'
    assert 'Sprintctl alone settles' in c.render_text(report) and not report['settlement_inferred']

@pytest.mark.parametrize('field',['repo','repository','item','release'])
def test_scope_mismatch_refuses(field):
    left,right=protected_capture(),competing_capture()
    if field=='repo':
        right['repo_id']='other'
        for entry in right['results'].values():entry['value']['repo_id']='other'
    if field=='repository':
        row=intent(right);row['repository']='other/repo';row['canonical_intent_digest']=p1.intent_digest(row)
    if field=='item':
        intent(right)['item_id']=43
        for operation in (p1.RELEASE,p1.DECISIONS,p1.LEASES):
            right['results'][operation]['arguments']['item_id']=43
            if operation==p1.RELEASE:right['results'][operation]['value']['release']['work_item_id']=43
            else:right['results'][operation]['value']['item_id']=43
    if field=='release':right['results'][p1.RELEASE]['value']['release']['release_digest']='0'*64
    with pytest.raises(p1.ReconstructionError,match='binding mismatch'):c.compare(left,right)

def test_source_revision_changes_projection_without_ranking_time():
    left,right=protected_capture(),competing_capture();initial=c.compare(left,right)
    right['results'][p1.RELEASE]['value']['release']['item_revision']='item:demo@description:v2@revise:0'
    right['results'][p1.RELEASE]['observed_at']='2099-01-01T00:00:00Z';report=c.compare(left,right)
    assert report!=initial and report['candidates']['right']['capture_sha256']!=initial['candidates']['right']['capture_sha256']
    source=next(s for s in report['candidates']['right']['sources'] if s['operation']==p1.RELEASE)
    assert source['owner_revisions']['item_revision'].endswith('v2@revise:0') and report['changed_sources'][0]['status']=='changed'
    assert all(v['freshness']['status']=='unknown' for v in report['candidates'].values())

def test_missing_links_remain_explicit():
    left,right=protected_capture(),competing_capture();del right['results'][p1.RELEASE];intent(left)['application']=None;report=c.compare(left,right)
    assert report['missing_bindings']==['release_digest'] and report['binding_status']=='partial'
    assert 'effect_receipt' in report['candidates']['left']['missing'] and 'work_release' in report['candidates']['right']['missing']
    assert any(s['status']=='unknown' for s in report['changed_sources'])

def test_same_attempt_and_unavailable_claims_cannot_self_assert_currentness():
    left=protected_capture();right=deepcopy(left);right['source_mode']='live-owner-reads';right['results'][p1.LEASES]={'status':'unavailable','reason':'refused'};report=c.compare(left,right)
    assert report['same_recorded_intent'] and report['recorded_run_relation']=='same' and 'attempts_and_claims' in report['candidates']['right']['missing']
    assert report['candidates']['right']['freshness']['status']=='unknown'

def test_cli_reads_without_file_writes(tmp_path,capsys):
    paths=[tmp_path/'left.json',tmp_path/'right.json']
    for path,capture in zip(paths,[protected_capture(),competing_capture()]):path.write_text(json.dumps(capture))
    before=[p.read_bytes() for p in paths];assert main(['--left',str(paths[0]),'--right',str(paths[1])])==0
    report=json.loads(capsys.readouterr().out);assert report['schema']==c.SCHEMA and not report['authorizes_effects']
    assert [p.read_bytes() for p in paths]==before and sorted(p.name for p in tmp_path.iterdir())==['left.json','right.json']

def test_cli_malformed_refusal_has_no_partial_output(tmp_path,capsys):
    path=tmp_path/'capture.json';doc=protected_capture();doc['results']['work.effect.accept-v1']={};path.write_text(json.dumps(doc))
    assert main(['--left',str(path),'--right',str(path)])==2
    output=capsys.readouterr();assert not output.out and 'refused' in output.err
    path.write_text(json.dumps(protected_capture()).replace('"intent_revision": 1','"intent_revision": 1, "intent_revision": 2'))
    assert main(['--left',str(path),'--right',str(path)])==2
    output=capsys.readouterr();assert not output.out and 'refused' in output.err


def test_same_run_with_two_intents_reports_same_recorded_run():
    left,right=protected_capture(),competing_capture()
    intent(right)['run_id']=intent(left)['run_id']
    report=c.compare(left,right)
    assert not report['same_recorded_intent']
    assert report['recorded_run_relation']=='same'


def test_missing_owner_intents_do_not_infer_run_equality():
    left=protected_capture();right=deepcopy(left)
    for doc in (left,right):
        doc['results'][p1.EFFECT]={'status':'unavailable','reason':'owner read unavailable'}
    report=c.compare(left,right)
    assert report['same_recorded_intent']
    assert report['recorded_run_relation']=='unknown'
    assert all(side['run_id'] is None for side in report['candidates'].values())


def test_one_missing_owner_run_is_unknown():
    left,right=protected_capture(),competing_capture()
    right['results'][p1.EFFECT]={'status':'unavailable','reason':'owner read unavailable'}
    assert c.compare(left,right)['recorded_run_relation']=='unknown'
