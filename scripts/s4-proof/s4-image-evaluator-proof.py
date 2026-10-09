"""Actual digest-pulled image HTTPS evaluator proof; only own disposable state."""
import atexit
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version, distribution
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import zipfile
import threading
import time
from urllib.parse import urlencode, urlsplit, parse_qs, unquote

import httpx
import jwt
from datetime import UTC, datetime, timedelta
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from sprintctl import pg
from auditctl.central_schema import migrate as audit_migrate

PYTHON = sys.executable
ROOT = Path(tempfile.mkdtemp(prefix='s4-offline-causal-', dir='/tmp'))
ROOT.chmod(0o700)
PACKET = Path(os.environ.get('S4_PROOF_PACKET_ROOT','/tmp/s4-proof-receipts')) / ('attempt-' + ROOT.name.rsplit('-', 1)[-1])
PACKET.mkdir(mode=0o700, parents=True, exist_ok=False)
REPO = 's4-fixture'
PROCESSES = []
CONTAINERS = []
PROXIES = []
RECEIPTS = {'qualification': 'image-loaded read-time evaluator; authenticated execution facts and full S4 remain open', 'checks': []}
PINS_PATH=Path(__file__).with_name('artifact-pins-evaluator.json')
PINS=json.loads(PINS_PATH.read_text())
REPORT_SEQ = 0
def record_failure(exc_type, exc, traceback):
    RECEIPTS['status'] = 'failed; qualification incomplete'
    RECEIPTS['exception_type'] = exc_type.__name__
    sys.__excepthook__(exc_type, exc, traceback)
sys.excepthook = record_failure
# Capture the exact executing source before any fixture operations.
RECEIPTS['harness_sha256'] = {}
for source in (Path(__file__), Path(__file__).with_name('s4-image-evaluator-pg.sh'),PINS_PATH):
    payload = source.read_bytes()
    target = PACKET / source.name
    target.write_bytes(payload)
    target.chmod(0o600)
    RECEIPTS['harness_sha256'][source.name] = hashlib.sha256(payload).hexdigest()


def check(name, condition):
    if not condition:
        RECEIPTS['failed_check'] = name
        RECEIPTS['status'] = 'failed; qualification incomplete'
        raise AssertionError(name)
    RECEIPTS['checks'].append(name)
    print('PASS', name, flush=True)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def command(args, *, cwd=ROOT, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        # Fixture diagnostics may contain temporary fixture paths, never credentials.
        raise RuntimeError(f'{Path(args[0]).name} failed: {result.stderr[-2000:]} {result.stdout[-2000:]}')
    return result.stdout


def dsn(role, database):
    password = os.environ[role.upper() + '_PASSWORD']
    options = {'options': '-csearch_path=work,pg_catalog'} if role.startswith('s4_work') else {}
    return f'postgresql://{role}:{password}@127.0.0.1:{os.environ["S4_DISPOSABLE_PORT"]}/{database}?' + urlencode(options)


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@atexit.register
def cleanup():
    errors=[]
    def guarded(label,action):
        try:
            action()
        except Exception as exc:
            errors.append({'phase':label,'error_type':type(exc).__name__})
    for server in PROXIES:
        guarded('proxy-stop',lambda server=server:(server.shutdown(),server.server_close()))
    def remove_container(name):
        result=subprocess.run(['docker','rm','-f',name],capture_output=True,text=True,timeout=15)
        if result.returncode:
            absent='No such container' in result.stderr
            daemon=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,timeout=15)
            if not absent or daemon.returncode:
                raise RuntimeError('owned container cleanup not confirmed')
    for name in CONTAINERS:
        guarded('container-stop',lambda name=name:remove_container(name))
    for process in PROCESSES:
        guarded('child-stop',lambda process=process:stop(process))
    def capture_files():
        for name in ('binding','reserve','evidence','proposal'):
            path=ROOT/(name+'.json')
            if path.exists():
                shutil.copyfile(path,PACKET/path.name)
                (PACKET/path.name).chmod(0o600)
        if (ROOT/'git-baseline/.git').exists():
            subprocess.run(['git','bundle','create',str(PACKET/'fixture.bundle'),'--all'],cwd=ROOT/'git-baseline',env=git_env,capture_output=True,timeout=15,check=True)
            (PACKET/'fixture.bundle').chmod(0o600)
    guarded('artifact-capture',capture_files)
    RECEIPTS['durability_limit']='PostgreSQL fsync off; client/service interruption proof, not database crash durability. Packet is host-persistent until separately published.'
    if errors:
        RECEIPTS['cleanup_errors']=errors
        RECEIPTS['status']='cleanup or artifact capture incomplete; qualification incomplete'
    try:
        write(PACKET/'receipt.json',RECEIPTS)
        write(PACKET/'manifest.json',{str(p.relative_to(PACKET)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PACKET.rglob('*')) if p.is_file() and p.name!='manifest.json'})
    except Exception:
        print('INCOMPLETE receipt capture; private scratch retained',ROOT,flush=True)
        os._exit(1)
    if errors:
        print('INCOMPLETE cleanup; private scratch retained',ROOT,flush=True)
        os._exit(1)
    else:
        shutil.rmtree(ROOT)


VERSIONS = {name: version(name) for name in PINS['wheels']}
check('installed released distributions',VERSIONS=={name:pin['version'] for name,pin in PINS['wheels'].items()})
RECEIPTS['versions']=VERSIONS
RECEIPTS['artifact_pins']=PINS
for module,package,relative in [(pg,'sprintctl','sprintctl/pg.py'),(sys.modules[audit_migrate.__module__],'auditctl','auditctl/central_schema.py')]:
    check(package+' imported owner origin matches verified distribution',Path(module.__file__).resolve()==distribution(package).locate_file(relative).resolve())
for name,pin in PINS['wheels'].items():
    installed=distribution(name)
    origin=json.loads(installed.read_text('direct_url.json') or '{}')
    parsed=urlsplit(origin.get('url',''))
    check(name+' installed from local immutable wheel',parsed.scheme=='file' and not origin.get('dir_info'))
    wheel=Path(unquote(parsed.path))
    check(name+' actual wheel hash matches pin',wheel.name==pin['wheel'] and hashlib.sha256(wheel.read_bytes()).hexdigest()==pin['sha256'])
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.endswith('/') or member.endswith('.dist-info/RECORD'):
                continue
            assert not member.startswith('/') and '..' not in Path(member).parts
            assert '.data/' not in member, 'unsupported wheel data layout'
            check(name+' installed file '+member,installed.locate_file(member).read_bytes()==archive.read(member))


def validate_admin_url(value):
    parsed = urlsplit(value)
    query = parse_qs(parsed.query)
    sock = Path(query.get('host', [''])[0])
    if parsed.hostname is not None or parsed.username != 'pgadmin_disposable' or parsed.path != '/postgres' or set(query) != {'host','port'}:
        raise ValueError('disposable admin must use the wrapper-owned Unix socket')
    if sock.name != 'sock' or not sock.parent.name.startswith('sprintctl-pg.') or sock.parent.parent != Path('/tmp') or sock.is_symlink():
        raise ValueError('socket must be in the wrapper scratch cluster')
    owner = (sock.parent / 'owner').read_text().split()
    if int(owner[0]) != os.getppid() or query['port'] != [os.environ['S4_DISPOSABLE_PORT']]:
        raise ValueError('cluster ownership/port mismatch')
    return value


try:
    validate_admin_url('postgresql://pgadmin_disposable@production.example/postgres')
except ValueError:
    check('nonlocal disposable admin configuration refused before connecting', True)
else:
    raise AssertionError('nonlocal admin accepted')
validate_admin_url(os.environ['S4_DISPOSABLE_ADMIN_DSN'])
admin = psycopg.connect(os.environ['S4_DISPOSABLE_ADMIN_DSN'], autocommit=True)
assert admin.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='s4_seed_disposable'").fetchone()[0] == 'sprintctl:disposable-integration-test'
check('wrapper-owned disposable socket and database marker verified', True)
with psycopg.connect(dsn('s4_work_migration', 's4_seed_disposable')) as c:
    c.execute('CREATE SCHEMA work AUTHORIZATION s4_work_migration')
with psycopg.connect(dsn('s4_audit_migration', 's4_seed_disposable')) as c:
    audit_migrate(c, schema='audit', migration_role='s4_audit_migration', runtime_role='s4_audit_runtime')
store = pg.get_connection(dsn('s4_work_migration', 's4_seed_disposable'))
store.repo_id = REPO
pg.init_db(store)
with store.conn.cursor() as c:
    c.execute('GRANT USAGE ON SCHEMA work TO s4_work_runtime')
    c.execute('REVOKE CREATE ON SCHEMA work FROM s4_work_runtime')
    c.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA work TO s4_work_runtime')
    c.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA work TO s4_work_runtime')
    c.execute('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA work TO s4_work_runtime')
store.conn.commit()
sprint = pg.create_sprint(store, 'Offline causal proof', 'Disposable', '2026-10-09', '2026-10-10', 'active')
track = pg.get_or_create_track(store, sprint, 'proof')
ITEM = pg.create_work_item(store, sprint, track, 'Correct harmless fixture text')
REVISION = pg.item_release_revision(store, ITEM)
store.conn.close()
for role in ('s4_work_runtime', 's4_audit_runtime'):
    with psycopg.connect(dsn(role, 's4_seed_disposable')) as c:
        c.execute('SELECT 1')
        try:
            with c.transaction():
                c.execute('CREATE TABLE ' + ('work' if role.startswith('s4_work') else 'audit') + '.forbidden_s4_runtime_ddl (value integer)')
        except psycopg.errors.InsufficientPrivilege:
            check(role + ' runtime DDL denied', True)
        else:
            raise AssertionError('fixture runtime unexpectedly has DDL')

# Synthetic assertions qualify verifier-to-owner binding, not OAuth issuance.
WORKSPACE='01K11111111111111111111111'
assertion_key=Ed25519PrivateKey.generate()
(ROOT/'gateway-public.pem').write_bytes(assertion_key.public_key().public_bytes(
    serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
writer_identity={'workspace_id':WORKSPACE,'subject':REPO,'principal_epoch':0,
    'client_id':'fixture-client','grant_id':'fixture-grant',
    'authorities':['work:read','work:write','work:evidence','work:batch','work.effect.propose']}
reader_identity={**writer_identity,'authorities':['work:read','work:evidence']}
def assertion_headers(envelope,identity):
    now=datetime.now(UTC)
    claims={'iss':'s4-fixture','aud':'vuoro-service','sub':REPO,'actor':REPO,
        'repo_ids':[REPO],'request_id':envelope['request_id'],'iat':now,
        'nbf':now-timedelta(seconds=2),'exp':now+timedelta(seconds=30),
        'jti':secrets.token_urlsafe(16),**identity}
    return {'X-Vuoro-Identity':jwt.encode(claims,assertion_key,algorithm='EdDSA',
        headers={'typ':'JWT','kid':'gateway-2026-01'}),'X-Request-ID':envelope['request_id']}
write(ROOT / 'observers.json', {'schema_version': 'vuoro-work-resource-observers/v1', 'grants': []})
git = ROOT / 'git-baseline'
git.mkdir()
git_env = os.environ.copy()
for key in list(git_env):
    if key.startswith('GIT_'):
        git_env.pop(key)
git_env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_AUTHOR_NAME='S4 fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_NAME='S4 fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid', GIT_AUTHOR_DATE='2026-10-09T00:00:00Z', GIT_COMMITTER_DATE='2026-10-09T00:00:00Z')
command(['git', 'init', '-b', 'main'], cwd=git, env=git_env)
command(['git', 'config', 'core.hooksPath', '/dev/null'], cwd=git, env=git_env)
command(['git', 'config', 'commit.gpgsign', 'false'], cwd=git, env=git_env)
command(['git', 'remote', 'add', 'origin', 'https://github.com/example/s4-fixture.git'], cwd=git, env=git_env)
(git / 'project.toml').write_text('name = "s4-fixture"\n')
(git / 'harmless.txt').write_text('before\n')
(git / '.gitignore').write_text('.sprintctl/\n')
command(['git', 'add', '.'], cwd=git, env=git_env)
command(['git', 'commit', '-m', 'Initial disposable fixture'], cwd=git, env=git_env)
BASE = command(['git', 'rev-parse', 'HEAD'], cwd=git, env=git_env).strip()
write(ROOT / 'bindings.json', {'schema_version':'vuoro-project-bindings/v1',
    'environment':'s4-disposable','projects':[{'project_id':'01K22222222222222222222222',
    'descriptor_digest':'sha256:'+hashlib.sha256((git/'project.toml').read_bytes()).hexdigest(),
    'repositories':[{'repo_id':REPO,'git_remote':'https://github.com/example/s4-fixture',
    'commit_sha':BASE}]}]})
command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(ROOT / 'tls.key'), '-out', str(ROOT / 'tls.crt'), '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'])
(ROOT / 'tls.key').chmod(0o600)
tls = ssl.create_default_context(cafile=str(ROOT / 'tls.crt'))


write(PACKET/'hosted-binding.json',json.loads((ROOT/'bindings.json').read_text()))
RECEIPTS['synthetic_public_key_sha256']=hashlib.sha256((ROOT/'gateway-public.pem').read_bytes()).hexdigest()


class Authority:
    def __init__(self, database, name):
        self.database, self.name = database, name
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.endpoint = f'https://localhost:{self.port}'
        self.process = None
        self.client = httpx.Client(base_url=self.endpoint, verify=tls, trust_env=False, timeout=10, headers={'X-Vuoro-Client-Protocol': '1'})

    def start(self):
        env = dict(VUORO_ENVIRONMENT_NAME='s4-disposable', VUORO_ENVIRONMENT_CLASS='development', VUORO_WORK_REPOSITORY_ID=REPO, VUORO_WORK_RUNTIME_DSN=dsn('s4_work_runtime', self.database), VUORO_AUDIT_RUNTIME_DSN=dsn('s4_audit_runtime', self.database), VUORO_AUDIT_SCHEMA='audit', VUORO_PROJECT_BINDINGS_FILE='/etc/vuoro/bindings/bindings.json', VUORO_GATEWAY_PUBLIC_KEY_FILE='/etc/vuoro/identity/gateway-public.pem', VUORO_GATEWAY_ASSERTION_ISSUER='s4-fixture', VUORO_GATEWAY_ASSERTION_AUDIENCE='vuoro-service', VUORO_GATEWAY_ASSERTION_KEY_ID='gateway-2026-01', VUORO_WORKSPACE_ID=WORKSPACE, VUORO_WORK_RESOURCE_OBSERVERS_FILE='/fixture/observers.json')
        envfile = ROOT / (self.name + '-service.env')
        envfile.write_text(''.join(name + '=' + value + '\n' for name,value in env.items()))
        envfile.chmod(0o600)
        mounts = []
        for name,target in [('gateway-public.pem','/etc/vuoro/identity/gateway-public.pem'),('observers.json','/fixture/observers.json'),('bindings.json','/etc/vuoro/bindings/bindings.json'),('tls.key','/fixture/tls.key'),('tls.crt','/fixture/tls.crt')]:
            # The host fixture directory remains0700; the nonroot container
            # can read only these explicit readonly bind-mounted files.
            (ROOT / name).chmod(0o444)
            mounts += ['--mount',f'type=bind,src={ROOT/name},dst={target},readonly']
        self.container = 's4-fixture-' + self.name + '-' + secrets.token_hex(6)
        CONTAINERS.append(self.container)
        log = (ROOT / (self.name + '-service.log')).open('a')
        self.process = subprocess.Popen(['docker','run','--rm','--name',self.container,'--network','host','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--env-file',str(envfile),*mounts,'--entrypoint','python',PINS['image'],'-m', 'uvicorn', 'vuoro_service.composition:create_composed_app', '--factory', '--host', '127.0.0.1', '--port', str(self.port), '--workers', '1', '--ssl-keyfile', '/fixture/tls.key', '--ssl-certfile', '/fixture/tls.crt'], cwd=ROOT, stdout=log, stderr=log)
        PROCESSES.append(self.process)
        log.close()
        for _ in range(100):
            if self.process.poll() is not None:
                raise AssertionError((ROOT / (self.name + '-service.log')).read_text()[-2500:])
            try:
                if self.client.get('/health/ready').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.1)
        else:
            raise AssertionError('fixture readiness timeout')
        catalog = self.client.get('/api/catalog/v1').json()
        self.revision = catalog['revision']
        check(self.name + ' actual composed catalog79', len(catalog['operations']) == PINS['catalog_operations'] and self.revision == PINS['catalog_revision'])

    def invoke(self, operation, arguments, key=None, *, repo=REPO, expected=200):
        envelope = {'schema_version': 'invocation/v1', 'request_id': secrets.token_hex(16), 'repo_id': repo, 'catalog_revision': self.revision, 'operation': operation, 'arguments': arguments}
        if key is not None:
            envelope['idempotency_key'] = key
        response = self.client.post('/api/invoke/v1', json=envelope, headers=assertion_headers(envelope,writer_identity))
        assert response.status_code == expected, (operation, response.status_code, response.json())
        return response.json()['result'] if expected == 200 else response.json()

    def halt(self):
        command(['docker','stop','--time','3',self.container])
        stop(self.process)
        self.process = None


import jsonschema
from sprintctl.vuoro_adapter import WORK_OPERATION_CONTRACTS
callers={label:{**reader_identity,'authorities':scopes} for label,scopes in
    [('read-only',['work:read']),('evidence-only',['work:evidence']),('neither',[])]}
for field,value in [('subject','foreign'),('workspace_id','01K33333333333333333333333'),
                    ('client_id','foreign-client'),('grant_id','foreign-grant')]:
    callers[field]={**reader_identity,field:value}
seed=Authority('s4_seed_disposable','image-evaluator')
seed.start()
RUN=seed.invoke('work.run.register-v1',{'harness_id':'image-fixture','harness_build':'test',
    'model_id':'scripted','recipe_id':'image-evaluator/v1',
    'observed_profile':{'instruction_digest':'sha256:'+'a'*64,'skill_digests':[]},
    'idempotency_key':'run-0001'})['run']['run_id']
reserve=seed.invoke('work.reservation.reserve-v1',{'item_id':ITEM,'actor':REPO,
    'session_id':'image-fixture','expected_revision':REVISION},key='reserve-1')['reservation']
ARGS={'run_id':RUN,'subject':'effect','basis':{'item_id':ITEM,'expected_revision':REVISION,
    'release_digest':reserve['release_digest']},'as_of':'2026-10-09T12:00:00Z',
    'current_input_digests':{},'expected_tail':None}
OP='work.evidence.evaluate-v1'
CONTRACT=next(c for c in WORK_OPERATION_CONTRACTS if c.name==OP)

def state():
    rows={}
    with psycopg.connect(dsn('s4_work_runtime','s4_seed_disposable'),row_factory=dict_row) as conn:
        for table in ('run','work_item','evidence_item','work_release','reservation',
                      'work_effect_intent','work_decision','work_idempotency_ledger'):
            values=conn.execute(sql.SQL('SELECT to_jsonb(t) AS row FROM work.{} t WHERE repo_id=%s').format(sql.Identifier(table)),(REPO,)).fetchall()
            rows[table]=sorted([v['row'] for v in values],key=lambda v:json.dumps(v,sort_keys=True))
    return rows

def evaluate(arguments=ARGS,*,caller=reader_identity,expected=200,code=None,key=None,repo=REPO):
    before=state()
    envelope={'schema_version':'invocation/v1','request_id':secrets.token_hex(16),'repo_id':repo,
        'catalog_revision':seed.revision,'operation':OP,'arguments':arguments}
    if key is not None: envelope['idempotency_key']=key
    response=seed.client.post('/api/invoke/v1',json=envelope,headers=assertion_headers(envelope,caller))
    check('HTTPS evaluator expected status '+str(expected),response.status_code==expected)
    body=response.json()
    seq=len(list(PACKET.glob('evaluation-*.json')))+1
    write(PACKET/f'evaluation-{seq:02}.json',{'request':envelope,'signed_fixture_identity':caller,
        'http_status':response.status_code,'response':body,
        'before_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        'after_sha256':hashlib.sha256(json.dumps(state(),sort_keys=True).encode()).hexdigest()})
    check('HTTPS evaluator preserves eight full owner tables',state()==before)
    if expected!=200:
        check('HTTPS evaluator explicit refusal '+str(code),body['error']['code']==code and body.get('result') is None)
        return body
    value=body['result']
    jsonschema.validate(value,CONTRACT.result_schema)
    check('HTTPS result matches closed published schema',True)
    check('HTTPS result retains unsupported execution coverage',value['authority_coverage']=='unsupported'
        and value['authenticated_execution_facts']==[] and value['effect_state']=='unknown'
        and value['recommendation']=='reconcile' and value['authorizes_execution'] is False)
    return value

# One assertion is one-use even when the protected operation is read-only.
replay_envelope={'schema_version':'invocation/v1','request_id':secrets.token_hex(16),
    'repo_id':REPO,'catalog_revision':seed.revision,'operation':OP,'arguments':ARGS}
replay_headers=assertion_headers(replay_envelope,reader_identity)
before=state()
accepted=seed.client.post('/api/invoke/v1',json=replay_envelope,headers=replay_headers)
replayed=seed.client.post('/api/invoke/v1',json=replay_envelope,headers=replay_headers)
check('image gateway exact signed assertion replay refused',accepted.status_code==200 and
    replayed.status_code==401 and replayed.json()['error']['code']=='identity-replayed')
check('image gateway replay history preserves eight owner tables',state()==before)
write(PACKET/'assertion-replay.json',{'request':replay_envelope,
    'first_status':accepted.status_code,'replay_status':replayed.status_code,
    'replay_response':replayed.json()})
# Signature and correlation discriminators reach the actual image verifier.
for case in ('bad-signature','request-correlation'):
    envelope={**replay_envelope,'request_id':secrets.token_hex(16)}
    headers=assertion_headers(envelope,reader_identity)
    if case=='bad-signature':
        claims=jwt.decode(headers['X-Vuoro-Identity'],options={'verify_signature':False})
        headers['X-Vuoro-Identity']=jwt.encode(claims,Ed25519PrivateKey.generate(),
            algorithm='EdDSA',headers={'typ':'JWT','kid':'gateway-2026-01'})
    else:
        headers['X-Request-ID']=secrets.token_hex(16)
    before=state()
    response=seed.client.post('/api/invoke/v1',json=envelope,headers=headers)
    check('image gateway '+case+' refused',response.status_code==401 and
        response.json()['error']['code']=='identity-required')
    check('image gateway '+case+' preserves eight owner tables',state()==before)
    write(PACKET/(case+'.json'),{'request':envelope,'status':response.status_code,
        'response':response.json(),'fixture_fault':case})
empty=evaluate()
resolved=seed.invoke('work.run.resolve-v1',{'run_id':RUN})
check('image evaluator full authenticated binding matches owner run resolve',empty['run_binding']==resolved)
check('image evaluator preserves nonempty client and grant',empty['run_binding']['client_id']=='fixture-client' and empty['run_binding']['grant_id']=='fixture-grant')
check('image evaluator empty chain/current Release',empty['basis_status']=='current' and empty['evidence_validity']==[])
for label in ('read-only','evidence-only'):
    evaluate(caller=callers[label],expected=403,code='authority-required')
evaluate(caller=callers['neither'],expected=401,code='identity-required')
evaluate(caller=callers['workspace_id'],expected=401,code='identity-required')
for field in ('subject','client_id','grant_id'):
    evaluate(caller=callers[field],expected=404,code='run-not-found')
for field in ('identity','trusted','authenticated_execution_facts'):
    evaluate({**ARGS,field:{}},expected=422,code='schema-validation-failed')
evaluate(key='read-key-1',expected=400,code='idempotency-key-not-allowed')
evaluate(repo='foreign-fixture',expected=403,code='repo-unauthorized')
evidence={'run_id':RUN,'item_id':'image-evidence-1','kind':'test','ref':'local:fixture',
    'digest':'sha256:'+'d'*64,'collector':'fixture',
    'validity':{'basis':'indefinite','valid_from':'2026-10-09T00:00:00Z','valid_until':None,'component_digests':{}},
    'claims':[{'claim_type':name,'subject':'effect','grant_id':'claimed-grant','freshness':None,
        'confirms':True,'detail':{'trusted':True,'grant_used':True,'non_invocation_proven':True}}
        for name in ('effect_completed','observation','effect_not_invoked')],
    'provenance':{'authority':'owner'},'chain_seq':0,'chain_prev_digest':None,'idempotency_key':'evidence-1'}
item=seed.invoke('work.evidence.append-v1',evidence)['item']
ARGS['expected_tail']={'item_id':item['item_id'],'chain_seq':item['chain_seq'],'entry_digest':pg.evidence_entry_digest(item)}
first=evaluate();second=evaluate()
check('image evaluator deterministic fixed-clock snapshot',
    {k:v for k,v in first.items() if k!='observed_at'}=={k:v for k,v in second.items() if k!='observed_at'})
check('schema-valid forged trust remains three authored assertions',len(first['authored_assertions'])==3
    and all(a['authority']=='authored-assertion' for a in first['authored_assertions']))
evaluate({**ARGS,'expected_tail':None},expected=409,code='evidence-tail-mismatch')
for case,window,status in [('expired',{'basis':'bounded','valid_from':'2026-10-08T00:00:00Z','valid_until':'2026-10-08T01:00:00Z','component_digests':{}},'expired'),
    ('missing-input',{'basis':'until_inputs_change','valid_from':'2026-10-08T00:00:00Z','valid_until':None,'component_digests':{'tree':'sha256:'+'e'*64}},'unknown'),
    ('invalid-legacy',{'basis':'unsupported-legacy'},'invalid')]:
    # Legacy source setup is restricted to the wrapper-owned migration fixture.
    with psycopg.connect(dsn('s4_work_migration','s4_seed_disposable')) as c:
        c.execute('UPDATE work.evidence_item SET validity=%s::jsonb WHERE repo_id=%s AND run_id=%s',
            (json.dumps(window),REPO,RUN))
    value=evaluate()
    check('image evaluator distinguishes '+case,value['evidence_validity'][0]['status']==status)
# Independent owner fixture edit uses only the disposable migration role.
edit_store=pg.get_connection(dsn('s4_work_migration','s4_seed_disposable'))
edit_store.repo_id=REPO
pg.update_work_item_description(edit_store,ITEM,'Changed independently')
edit_store.conn.commit()
edit_store.conn.close()
stale=evaluate()
check('image evaluator reports stale full Release basis',stale['basis_status']=='stale')
ARGS['basis']['expected_revision']=stale['current_basis']['expected_revision']
check('image evaluator old frozen Release remains stale with new caller revision',evaluate()['basis_status']=='stale')
RECEIPTS.update(evaluator_revision=first['evaluator_revision'],image=PINS['image'],
    identity_qualification='synthetic signed gateway assertion verifier to owner binding; OAuth issuance, revocation and MCP forwarding unqualified',
    status='image-loaded HTTPS evaluator and separate runtime-role refusal histories passed; fullS4 remains open')
admin.close()
print('GREEN actual digest-pulled HTTPS evaluator; full S4 execution facts remain unsupported',flush=True)
