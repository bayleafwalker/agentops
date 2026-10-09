"""Actual installed-release HTTPS and CLI proof; only own disposable state."""
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
RECEIPTS = {'qualification': 'disposable-causal-pipeline; not full S4 effective-state evaluation', 'checks': []}
PINS_PATH=Path(__file__).with_name('artifact-pins.json')
PINS=json.loads(PINS_PATH.read_text())
REPORT_SEQ = 0
def record_failure(exc_type, exc, traceback):
    RECEIPTS['status'] = 'failed; qualification incomplete'
    RECEIPTS['exception_type'] = exc_type.__name__
    sys.__excepthook__(exc_type, exc, traceback)
sys.excepthook = record_failure
# Capture the exact executing source before any fixture operations.
RECEIPTS['harness_sha256'] = {}
for source in (Path(__file__), Path(__file__).with_name('s4-offline-causal-pg.sh'),PINS_PATH):
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

editor_token = secrets.token_hex(32)
token = secrets.token_hex(32)
(ROOT / 'token').write_text(token)
(ROOT / 'token').chmod(0o600)
write(ROOT / 'identities.json', {'schema_version': 'vuoro-identities/v1', 'identities': {token: {'actor': REPO, 'environment': 's4-disposable', 'principal_id': 'fixture:s4-fixture:0', 'workspace_id': 's4-disposable', 'repo_ids': [REPO], 'authorities': ['work:read', 'work:write', 'work:evidence', 'work:batch', 'work.effect.propose']}}})
identities = json.loads((ROOT/'identities.json').read_text())
identities['identities'][editor_token] = {'actor':'s4-fixture-editor','environment':'s4-disposable','principal_id':'fixture:editor:0','workspace_id':'s4-disposable','repo_ids':[REPO],'authorities':['work:read','work:lifecycle']}
write(ROOT/'identities.json',identities)
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
write(ROOT / 'bindings.json', {'schema_version': 'vuoro-project-bindings/v1', 'bindings': [{'project_id': '77ce81c5-43e1-4bf9-a77f-a16dc60bab98', 'home_repo': REPO, 'members': [{'repo_id': REPO}], 'source_repository': 'https://github.com/example/s4-fixture', 'source_revision': BASE, 'source_path': 'project.toml', 'source_sha256': hashlib.sha256((git / 'project.toml').read_bytes()).hexdigest()}]})
command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(ROOT / 'tls.key'), '-out', str(ROOT / 'tls.crt'), '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'])
(ROOT / 'tls.key').chmod(0o600)
tls = ssl.create_default_context(cafile=str(ROOT / 'tls.crt'))


class Authority:
    def __init__(self, database, name):
        self.database, self.name = database, name
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.endpoint = f'https://localhost:{self.port}'
        self.process = None
        self.client = httpx.Client(base_url=self.endpoint, verify=tls, trust_env=False, timeout=10, headers={'Authorization': 'Bearer ' + token, 'X-Vuoro-Client-Protocol': '1'})

    def start(self):
        env = dict(VUORO_ENVIRONMENT_NAME='s4-disposable', VUORO_ENVIRONMENT_CLASS='development', VUORO_WORK_REPOSITORY_ID=REPO, VUORO_WORK_RUNTIME_DSN=dsn('s4_work_runtime', self.database), VUORO_AUDIT_RUNTIME_DSN=dsn('s4_audit_runtime', self.database), VUORO_AUDIT_SCHEMA='audit', VUORO_IDENTITIES_FILE='/fixture/identities.json', VUORO_WORK_RESOURCE_OBSERVERS_FILE='/fixture/observers.json')
        envfile = ROOT / (self.name + '-service.env')
        envfile.write_text(''.join(name + '=' + value + '\n' for name,value in env.items()))
        envfile.chmod(0o600)
        mounts = []
        for name,target in [('identities.json','/fixture/identities.json'),('observers.json','/fixture/observers.json'),('bindings.json','/opt/vuoro/composition/project-bindings.json'),('tls.key','/fixture/tls.key'),('tls.crt','/fixture/tls.crt')]:
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
        check(self.name + ' actual composed catalog78', len(catalog['operations']) == PINS['catalog_operations'] and self.revision == PINS['catalog_revision'])

    def invoke(self, operation, arguments, key=None, *, repo=REPO, expected=200, editor=False):
        envelope = {'schema_version': 'invocation/v1', 'request_id': secrets.token_hex(16), 'repo_id': repo, 'catalog_revision': self.revision, 'operation': operation, 'arguments': arguments}
        if key is not None:
            envelope['idempotency_key'] = key
        response = self.client.post('/api/invoke/v1', json=envelope, headers={'Authorization':'Bearer '+editor_token} if editor else None)
        assert response.status_code == expected, (operation, response.status_code, response.json())
        return response.json()['result'] if expected == 200 else response.json()

    def halt(self):
        command(['docker','stop','--time','3',self.container])
        stop(self.process)
        self.process = None


seed = Authority('s4_seed_disposable', 'seed')
seed.start()
seed.invoke('work.read.release', {'item_id': ITEM}, repo='foreign-fixture', expected=403)
check('fixture identity foreign repo refused', True)
RUN = seed.invoke('work.run.register-v1', {'harness_id': 'offline-fixture', 'harness_build': 'released-v0151', 'model_id': 'scripted', 'recipe_id': 's4-causal-http/v1', 'observed_profile': {'instruction_digest': 'sha256:' + 'a' * 64, 'skill_digests': []}, 'idempotency_key': 's4-proof-baseline-run'})['run']['run_id']
BINDING = seed.invoke('work.run.resolve-v1', {'run_id': RUN})
check('actual nullable client/grant binding retained', BINDING['client_id'] is None and BINDING['grant_id'] is None)
pre = seed.invoke('work.reservation.reserve-v1', {'item_id': ITEM, 'actor': REPO, 'session_id': 'preparation', 'expected_revision': REVISION}, key='s4-proof-preparation-reserve')['reservation']
RELEASE = seed.invoke('work.read.release', {'release_digest': pre['release_digest']})['release']
seed.invoke('work.reservation.release', {'reservation_id': pre['id'], 'actor': REPO}, key='s4-proof-preparation-release')
seed.halt()
for database in ('s4_control_disposable', 's4_offline_disposable', 's4_lost_disposable', 's4_stale_disposable', 's4_context_disposable', 's4_tail_disposable'):
    admin.execute(sql.SQL('CREATE DATABASE {} WITH TEMPLATE s4_seed_disposable').format(sql.Identifier(database)))
    admin.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(database), sql.Literal('sprintctl:disposable-integration-test')))
    admin.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO s4_work_runtime, s4_audit_runtime').format(sql.Identifier(database)))
admin.close()

control = Authority('s4_control_disposable', 'control')
offline = Authority('s4_offline_disposable', 'offline')
control.start()
offline.start()
offline.halt()
for route in ('/health/ready', '/api/catalog/v1'):
    try:
        offline.client.get(route)
    except httpx.TransportError:
        check('offline service unavailable ' + route, True)
    else:
        raise AssertionError('offline authority remained reachable')
check('online control remains available during offline capture', control.client.get('/health/ready').status_code == 200)

# The original inputs and a real commit are shared byte-for-byte by both legs.
(git / 'harmless.txt').write_text('after\n')
command(['git', 'add', 'harmless.txt'], cwd=git, env=git_env)
command(['git', 'commit', '-m', 'Harmless fixture change\n\nVuoro-Release: ' + pre['release_digest']], cwd=git, env=git_env)
COMMIT = command(['git', 'rev-parse', 'HEAD'], cwd=git, env=git_env).strip()
DIFF = command(['git', 'diff', BASE, COMMIT], cwd=git, env=git_env)
EVIDENCE = {'run_id': RUN, 'item_id': 's4-offline-harmless-proof', 'kind': 'test', 'ref': 'local:harmless.txt', 'digest': 'sha256:' + hashlib.sha256((git / 'harmless.txt').read_bytes()).hexdigest(), 'collector': 's4-fixture', 'validity': {'basis': 'indefinite', 'valid_from': '2026-10-09T00:00:00Z', 'valid_until': None, 'component_digests': {}}, 'claims': [], 'provenance': {}, 'chain_seq': 0, 'chain_prev_digest': None, 'idempotency_key': 'evidence-1'}
BASIS = {'expected_revision': REVISION, 'release_digest': pre['release_digest'], 'reserve_idempotency_key': 's4-proof-offline-reserve', 'commit_sha': COMMIT, 'evidence_tail': {'item_id': EVIDENCE['item_id'], 'chain_seq': 0, 'entry_digest': pg.evidence_entry_digest(EVIDENCE)}}
RESERVE = {'schema_version': 'native-reserve-request/v1', 'operation': 'work.reservation.reserve-v1', 'idempotency_key': BASIS['reserve_idempotency_key'], 'arguments': {'item_id': ITEM, 'actor': REPO, 'session_id': 'offline-proof', 'role': 'execution', 'interrupt_existing': False, 'expected_revision': REVISION, 'acceptance_contract': RELEASE['acceptance_contract']}}
PROPOSAL = {'schema_version': 'native-bound-proposal-request/v1', 'operation': 'work.effect.propose-bound-v1', 'arguments': {'run_id': RUN, 'item_id': ITEM, 'repository': 'https://github.com/example/s4-fixture', 'base_commit': BASE, 'title': 'Harmless fixture change', 'rationale': 'Exercise offline causal confirmation', 'unified_diff': DIFF, 'idempotency_key': 's4-proof-bound-proposal', 'causal_basis': BASIS}}
for name, value in [('binding', BINDING), ('reserve', RESERVE), ('evidence', EVIDENCE), ('proposal', PROPOSAL)]:
    write(ROOT / (name + '.json'), value)
ORIGINAL = {name: hashlib.sha256((ROOT / (name + '.json')).read_bytes()).hexdigest() for name in ('binding', 'reserve', 'evidence', 'proposal')}
RECEIPTS.update(original_request_sha256=ORIGINAL, causal_basis=BASIS, binding=BINDING, original_release=RELEASE, base_commit=BASE, commit=COMMIT)


def producer(authority):
    checkout = ROOT / ('producer-' + authority.name)
    shutil.copytree(git, checkout)
    write(checkout / '.sprintctl/backend.json', {'backend': 'served', 'repo_id': REPO})
    write(checkout / '.sprintctl/authority-command.json', {'version': 1, 'mode': 'enforce'})
    profile = ROOT / (authority.name + '-profile.json')
    write(profile, {'schema_version': 'vuoro-client-profile/v1', 'id': 's4-' + authority.name, 'revision': 1, 'source_environment_id': 's4-fixture', 'target': {'environment_id': 's4-disposable', 'environment_class': 'development', 'endpoint': authority.endpoint}, 'credential_ref': 'file:' + str(ROOT / 'token'), 'required_authorities': ['work:read', 'work:write', 'work:evidence', 'work:batch'], 'production_endpoint_denied': True})
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('VUORO_', 'SPRINTCTL_', 'S4_', 'GIT_')) or key in ('PYTHONPATH','PYTHONHOME','PYTHONUSERBASE','PYTHONSTARTUP'):
            env.pop(key)
    env.update(SPRINTCTL_BACKEND='served', SPRINTCTL_VUORO_PROFILE=str(profile), SPRINTCTL_RUNTIME_SESSION_ID='s4-causal-fixture', SSL_CERT_FILE=str(ROOT / 'tls.crt'), NO_PROXY='localhost,127.0.0.1', no_proxy='localhost,127.0.0.1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', PYTHONNOUSERSITE='1')
    def cli(*args, expected_exit=0):
        global REPORT_SEQ
        result = subprocess.run([str(Path(PYTHON).parent / 'sprintctl'), 'authority', *args], cwd=checkout, env=env, capture_output=True, text=True, timeout=45)
        assert (result.returncode == 0) if expected_exit == 0 else (result.returncode != 0), (args,result.returncode,result.stdout,result.stderr)
        report = json.loads(result.stdout)
        REPORT_SEQ += 1
        write(PACKET / 'cli-results' / f'{REPORT_SEQ:03d}-{authority.name}-{args[0]}.json',{'exit_code':result.returncode,'stderr':result.stderr,'report':report})
        REPORT_SEQ += 1
        write(PACKET / 'reports' / f'{REPORT_SEQ:03d}-{authority.name}-{args[0]}.json',report)
        return report
    cli.checkout, cli.env = checkout, env
    return checkout, cli


def capture(authority):
    checkout, cli = producer(authority)
    captured = {}
    for stage in ('reserve', 'evidence', 'proposal'):
        captured[stage] = cli(stage + '-queue', '--request', str(ROOT / (stage + '.json')), '--run-binding', str(ROOT / 'binding.json'))
        status = cli(stage + '-status')
        check(authority.name + ' durable pending ' + stage, status['pending_' + stage + '_request_ids'] == [captured[stage]['request_id']])
    with psycopg.connect(dsn('s4_work_runtime', authority.database), row_factory=dict_row) as c:
        check(authority.name + ' offline capture has no owner native effects', c.execute("SELECT count(*) AS n FROM work.work_idempotency_ledger WHERE repo_id=%s AND tool IN ('reservation.reserve-v1','propose_effect')", (REPO,)).fetchone()['n'] == 1)
        check(authority.name + ' capture has no admitted proposal', c.execute('SELECT count(*) AS n FROM work.work_effect_intent WHERE repo_id=%s', (REPO,)).fetchone()['n'] == 0)
    return checkout, cli, captured


offline_producer = capture(offline)
control_producer = capture(control)
offline.start()


def confirm(authority, producer_state, before_proposal=None):
    checkout, cli, captured = producer_state
    reserve_report = cli('reserve-sync')
    check(authority.name + ' native reserve confirmed', not reserve_report['pending_reserve_request_ids'])
    outbox = checkout / '.sprintctl/authority-command-outbox.db'
    def receipt(table):
        with sqlite3.connect(outbox) as c:
            row = c.execute(f"SELECT result_json FROM {table} WHERE phase='confirmed' ORDER BY sequence DESC LIMIT 1").fetchone()
            assert row is not None, table
            return json.loads(row[0])
    reservation = receipt('native_reserve_attempt')['reservation_response']['reservation']
    observed = authority.invoke('work.read.release', {'release_digest': reservation['release_digest']})['release']
    check(authority.name + ' exact previously observed full Release barrier', reservation['release_digest'] == BASIS['release_digest'] and observed == RELEASE and observed['item_revision'] == REVISION)
    synced = cli('sync', '--json')
    check(authority.name + ' real trailer harvested and uploaded', synced['release_trailers']['status'] == 'harvested' and synced['release_trailers']['malformed'] == 0 and synced['uploaded_observation_count'] == 1)
    release_read = authority.invoke('work.read.release', {'release_digest': BASIS['release_digest']})
    check(authority.name + ' actual Git commit confirmed by owner', any(c['commit_sha'] == COMMIT for c in release_read['commits']))
    evidence_report = cli('evidence-sync')
    check(authority.name + ' evidence confirmed', not evidence_report['pending_evidence_request_ids'])
    tail_response = authority.invoke('work.evidence.tail-v1', {'run_id': RUN})
    tail = tail_response['item']
    check(authority.name + ' exact original evidence tail barrier', tail['item_id'] == EVIDENCE['item_id'] and tail['digest'] == EVIDENCE['digest'] and tail['chain_seq'] == 0 and tail['chain_prev_digest'] is None and pg.evidence_entry_digest(tail) == BASIS['evidence_tail']['entry_digest'])
    if before_proposal is not None:
        return before_proposal(authority,producer_state,reservation,observed,tail)
    proposal_report = cli('proposal-sync')
    check(authority.name + ' bound proposal confirmed', not proposal_report['pending_proposal_request_ids'])
    proposal = receipt('native_proposal_attempt')
    check(authority.name + ' admission correlated with original basis and authenticated binding', proposal['admission']['causal_basis'] == BASIS and proposal['admission']['run_binding'] == BINDING and proposal['admission']['reservation_id'] == reservation['id'] and proposal['intent']['release_digest'] == BASIS['release_digest'])
    for stage in ('reserve', 'evidence', 'proposal'):
        check(authority.name + ' exact confirmed repeat ' + stage, not cli(stage + '-sync')['pending_' + stage + '_request_ids'])
    repeated = cli('sync', '--json')
    check(authority.name + ' trailer cursor exact repeat adds no capture', repeated['release_trailers']['enqueued'] == 0)
    replay_reserve = authority.invoke('work.reservation.reserve-v1', RESERVE['arguments'], key=RESERVE['idempotency_key'])['reservation']
    check(authority.name + ' actual owner native reserve retry replays original admission', replay_reserve['replayed'] is True and replay_reserve['admission_snapshot'] == reservation['admission_snapshot'])
    authority.invoke('work.evidence.append-v1', EVIDENCE)
    replay_proposal = authority.invoke('work.effect.propose-bound-v1', PROPOSAL['arguments'])
    check(authority.name + ' actual owner native proposal retry exact receipt', replay_proposal == proposal)
    legacy = {key:value for key,value in PROPOSAL['arguments'].items() if key != 'causal_basis'}
    refused = authority.invoke('work.effect.propose-v1', legacy, expected=409)
    check(authority.name + ' actual shared legacy/bound key collision refused', refused['error']['code'] == 'idempotency-conflict')
    with sqlite3.connect(outbox) as c:
        for stage in ('reserve', 'evidence', 'proposal'):
            request = c.execute(f'SELECT source,source_sha256 FROM native_{stage}_request').fetchone()
            check(authority.name + ' retained original bytes ' + stage, request[0] == (ROOT / (stage + '.json')).read_bytes() and request[1] == ORIGINAL[stage])
    with psycopg.connect(dsn('s4_work_runtime', authority.database), row_factory=dict_row) as c:
        counts = c.execute("SELECT (SELECT count(*) FROM work.reservation WHERE repo_id=%s) AS reservations,(SELECT count(*) FROM work.work_effect_intent WHERE repo_id=%s) AS intents,(SELECT count(*) FROM work.evidence_item WHERE repo_id=%s) AS evidence,(SELECT count(*) FROM work.release_commit WHERE repo_id=%s) AS commits,(SELECT count(*) FROM work.work_idempotency_ledger WHERE repo_id=%s AND tool='reservation.reserve-v1') AS reserve_keys,(SELECT count(*) FROM work.work_idempotency_ledger WHERE repo_id=%s AND tool='propose_effect') AS proposal_keys", (REPO,) * 6).fetchone()
        item_state = c.execute('SELECT to_jsonb(w) AS state FROM work.work_item w WHERE repo_id=%s AND id=%s',(REPO,ITEM)).fetchone()['state']
        decisions = c.execute('SELECT count(*) AS n FROM work.work_decision WHERE repo_id=%s',(REPO,)).fetchone()['n']
        ingested = c.execute('SELECT count(*) AS n FROM work.ingest_record WHERE repo_id=%s',(REPO,)).fetchone()['n']
    check(authority.name + ' no fabricated terminal Decision and one trailer observation', decisions == 0 and ingested == 1)
    with sqlite3.connect(outbox) as c:
        cursor = c.execute('SELECT ref,commit_sha FROM release_trailer_cursor').fetchall()
        stream_position = c.execute('SELECT next_origin_seq FROM outbox_stream').fetchone()[0]
        record_count = c.execute('SELECT count(*) FROM outbox_record').fetchone()[0]
    check(authority.name + ' original single trailer stream and exact cursor', cursor == [('refs/heads/main',COMMIT)] and stream_position == 2 and record_count == 1)
    check(authority.name + ' one effect per native durable key', counts == {'reservations': 2, 'intents': 1, 'evidence': 1, 'commits': 1, 'reserve_keys': 2, 'proposal_keys': 1})
    return {'release': observed, 'tail': tail, 'proposal': proposal, 'reservation': reservation, 'counts': counts, 'commits': release_read['commits'],'item_state':item_state,'decisions':decisions,'trailer_cursor':cursor,'stream_position':stream_position}


control_result = confirm(control, control_producer)
offline_result = confirm(offline, offline_producer)

# Explicit field-specific normalization: map the single generated intent ID
# to its original request key and remove only the intent creation timestamp.
# Canonical digests, revisions, authority and all lifecycle fields remain.
def semantic_intent(result):
    intent = copy.deepcopy(result['proposal']['intent'])
    original_id = intent['intent_id']
    assert isinstance(original_id,str) and original_id
    intent['intent_id'] = PROPOSAL['arguments']['idempotency_key']
    assert isinstance(intent.pop('created_at'),str)
    return intent


def semantic_reservation(result):
    reservation = copy.deepcopy(result['reservation'])
    for field in ('created_at','last_activity_at','activity_age_seconds'):
        reservation.pop(field)
        reservation['admission_snapshot'].pop(field)
    assert isinstance(reservation.pop('replayed'), bool)
    # The expected replay discriminator is asserted separately.
    # Only observational receipt/heartbeat times and measured activity age
    # differ; keep stale/state, original ID/basis and every authority field.
    return reservation
check('online/offline full Release equivalent', control_result['release'] == offline_result['release'])
check('online/offline evidence and counts equivalent', control_result['tail'] == offline_result['tail'] and control_result['counts'] == offline_result['counts'])
check('online/offline original admission exactly equivalent', control_result['proposal']['admission'] == offline_result['proposal']['admission'])
check('online/offline proposal content and current state equivalent', semantic_intent(control_result) == semantic_intent(offline_result))
check('online/offline current reservation and original snapshot equivalent',semantic_reservation(control_result)==semantic_reservation(offline_result))
check('online/offline item and Decision state exactly equivalent',control_result['item_state']==offline_result['item_state'] and control_result['decisions']==offline_result['decisions'])
check('online/offline trailer cursors and stream position equivalent',control_result['trailer_cursor']==offline_result['trailer_cursor'] and control_result['stream_position']==offline_result['stream_position'])
check('authored request bytes never changed', ORIGINAL == {name: hashlib.sha256((ROOT / (name + '.json')).read_bytes()).hexdigest() for name in ORIGINAL})
RECEIPTS['results'] = {'control': control_result, 'offline': offline_result}
RECEIPTS['normalization'] = {'intent_id':'one-to-one correspondence through original proposal key','intent.created_at':'receipt timestamp omitted; every other intent field preserved','reservation.created_at/last_activity_at/activity_age_seconds':'observational times/age omitted on current and admission snapshot; stale/state/identity/Release retained'}


class LostReplyProxy:
    """Fixture-only TLS proxy: commit upstream, kill the owned CLI, drop reply."""
    def __init__(self, authority):
        self.authority = authority
        self.remaining = {'work.reservation.reserve-v1','work.batch.apply','work.evidence.append-v1','work.effect.propose-bound-v1'}
        self.receipts = {}
        self.child = None
        proxy = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def forward(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length','0')))
                headers = {k:v for k,v in self.headers.items() if k.lower() not in {'host','connection'}}
                with httpx.Client(verify=tls,trust_env=False,timeout=15) as upstream:
                    response = upstream.request(self.command,proxy.authority.endpoint+self.path,headers=headers,content=raw)
                op = json.loads(raw).get('operation') if raw else None
                if op in proxy.remaining and response.status_code == 200:
                    proxy.remaining.remove(op)
                    proxy.receipts[op] = response.json()['result']
                    assert proxy.child is not None and proxy.child.poll() is None
                    os.kill(proxy.child.pid,signal.SIGKILL)
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                self.send_response(response.status_code)
                self.send_header('Content-Type',response.headers.get('content-type','application/json'))
                self.send_header('Content-Length',str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)
            do_GET = forward
            do_POST = forward
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_tls.load_cert_chain(ROOT/'tls.crt',ROOT/'tls.key')
        self.server.socket = server_tls.wrap_socket(self.server.socket,server_side=True)
        self.endpoint = f'https://localhost:{self.server.server_address[1]}'
        PROXIES.append(self.server)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def install(self, cli):
        profile_path = Path(cli.env['SPRINTCTL_VUORO_PROFILE'])
        profile = json.loads(profile_path.read_text())
        profile['target']['endpoint'] = self.endpoint
        write(profile_path,profile)
        stages = {'reserve-sync':'work.reservation.reserve-v1','sync':'work.batch.apply','evidence-sync':'work.evidence.append-v1','proposal-sync':'work.effect.propose-bound-v1'}
        def faulted_cli(*args):
            operation = stages.get(args[0])
            if operation in self.remaining:
                self.child = subprocess.Popen([str(Path(PYTHON).parent/'sprintctl'),'authority',*args],cwd=cli.checkout,env=cli.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                PROCESSES.append(self.child)
                try:
                    self.child.communicate(timeout=45)
                    check('actual CLI killed after committed '+operation,self.child.returncode == -signal.SIGKILL and operation in self.receipts)
                finally:
                    stop(self.child)
                    self.child = None
            return cli(*args)
        return faulted_cli


lost = Authority('s4_lost_disposable','lost')
lost.start()
lost.halt()
lost_state = capture(lost)
lost.start()
proxy = LostReplyProxy(lost)
lost_cli = proxy.install(lost_state[1])
lost_result = confirm(lost,(lost_state[0],lost_cli,lost_state[2]))
RECEIPTS['results']['lost_reply'] = lost_result
check('control reserve is initial and lost-response reserve is exact replay',control_result['reservation']['replayed'] is False and lost_result['reservation']['replayed'] is True)
check('all four committed-response losses actually exercised',not proxy.remaining)
check('lost proposal receipt recovered byte-for-byte',lost_result['proposal']==proxy.receipts['work.effect.propose-bound-v1'])
check('lost native reserve retains committed original snapshot',lost_result['reservation']['admission_snapshot']==proxy.receipts['work.reservation.reserve-v1']['reservation']['admission_snapshot'])
check('lost-response history and online control reach same admission',lost_result['proposal']['admission']==control_result['proposal']['admission'])
check('lost-response current reservation and snapshot equivalent',semantic_reservation(lost_result)==semantic_reservation(control_result))
check('lost-response intent, evidence and item state equivalent',semantic_intent(lost_result)==semantic_intent(control_result) and lost_result['tail']==control_result['tail'] and lost_result['item_state']==control_result['item_state'])
check('lost-response Decision state and cursors equivalent',lost_result['decisions']==control_result['decisions'] and lost_result['trailer_cursor']==control_result['trailer_cursor'] and lost_result['stream_position']==control_result['stream_position'])
with sqlite3.connect(lost_state[0]/'.sprintctl/authority-command-outbox.db') as c:
    for stage in ('reserve','evidence','proposal'):
        rows = c.execute(f'SELECT attempt_id,phase FROM native_{stage}_attempt ORDER BY sequence').fetchall()
        attempts = {a for a,_ in rows}
        check('lost CLI preserves started and separate recovered '+stage,len(attempts)==2 and any(p=='started' for _,p in rows) and rows[-1][1]=='confirmed')
RECEIPTS['results']['lost_reply'] = lost_result
RECEIPTS['lost_after_commit_operations'] = sorted(proxy.receipts)



# Independent refusal histories never repair captured requests.
def retained_requests(state):
    checkout, cli, captured = state
    with sqlite3.connect(checkout/'.sprintctl/authority-command-outbox.db') as c:
        for stage in ('reserve','evidence','proposal'):
            source,digest=c.execute(f'SELECT source,source_sha256 FROM native_{stage}_request').fetchone()
            check('refusal original bytes retained '+stage,source==(ROOT/(stage+'.json')).read_bytes() and digest==ORIGINAL[stage])

def owner_counts(authority):
    with psycopg.connect(dsn('s4_work_runtime',authority.database),row_factory=dict_row) as c:
        return c.execute("SELECT (SELECT count(*) FROM work.work_effect_intent WHERE repo_id=%s) AS intents,(SELECT count(*) FROM work.work_idempotency_ledger WHERE repo_id=%s AND tool='propose_effect') AS proposal_keys,(SELECT count(*) FROM work.evidence_item WHERE repo_id=%s) AS evidence,(SELECT count(*) FROM work.release_commit WHERE repo_id=%s) AS commits",(REPO,)*4).fetchone()

def owner_state(authority):
    state={}
    with psycopg.connect(dsn('s4_work_runtime',authority.database),row_factory=dict_row) as c:
        for table,order in [('reservation','id'),('evidence_item','chain_seq'),('work_item','id'),('work_decision','id')]:
            state[table]=[row['value'] for row in c.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM work.{} t WHERE repo_id=%s ORDER BY {}').format(sql.Identifier(table),sql.Identifier(order)),(REPO,)).fetchall()]
    state['tail']=authority.invoke('work.evidence.tail-v1',{'run_id':RUN})['item']
    return state

def rejected_proposal(authority,state,reservation,observed,tail,code,expected_evidence):
    before=owner_counts(authority)
    before_state=owner_state(authority)
    checkout,cli,captured=state
    reports=[]
    for attempt in range(2):
        report=cli('proposal-sync',expected_exit=1)
        reports.append(report)
        check(authority.name+' proposal remains pending',report['pending_proposal_request_ids']==[captured['proposal']['request_id']])
        check(authority.name+' exact causal refusal code',any(a['phase']=='rejected' and a['code']==code and a['operation']=='work.effect.propose-bound-v1' for a in report['proposal_attempts']))
    after=owner_counts(authority)
    after_state=owner_state(authority)
    check(authority.name+' full owner state unchanged by both refusals',before_state==after_state)
    with sqlite3.connect(checkout/'.sprintctl/authority-command-outbox.db') as c:
        attempts=c.execute("SELECT operation,code,http_status FROM native_proposal_attempt WHERE phase='rejected' ORDER BY sequence").fetchall()
        check(authority.name+' two durable exact HTTP409 refusal receipts',attempts==[('work.effect.propose-bound-v1',code,409)]*2)
    check(authority.name+' no proposal effects on refusal',before==after=={'intents':0,'proposal_keys':0,'evidence':expected_evidence,'commits':1})
    retained_requests(state)
    check(authority.name+' original Release remains recorded',authority.invoke('work.read.release',{'release_digest':BASIS['release_digest']})['release']==RELEASE)
    with sqlite3.connect(checkout/'.sprintctl/authority-command-outbox.db') as c:
        saved=json.loads(c.execute("SELECT result_json FROM native_reserve_attempt WHERE phase='confirmed' ORDER BY sequence DESC LIMIT 1").fetchone()[0])['reservation_response']['reservation']
        check(authority.name+' earlier reservation receipt unchanged',saved==reservation)
    RECEIPTS['results'][authority.name]={'reports':reports,'before':before,'after':after,'before_state':before_state,'after_state':after_state,'rejected_attempts':attempts,'reservation':reservation,'original_tail':tail}

context=Authority('s4_context_disposable','context-refusal')
context.start()
context.halt()
context_state=capture(context)
context.start()
ref=context.invoke('work.item.ref.add',{'item_id':ITEM,'ref_type':'doc','url':'https://example.invalid/changed-context','label':'Independent context change'},editor=True)
check('context fault applied by separate fixture editor',isinstance(ref['ref_id'],int))
context_state[1]('reserve-sync')
with sqlite3.connect(context_state[0]/'.sprintctl/authority-command-outbox.db') as c:
    reservation=json.loads(c.execute("SELECT result_json FROM native_reserve_attempt WHERE phase='confirmed' ORDER BY sequence DESC LIMIT 1").fetchone()[0])['reservation_response']['reservation']
    check('context barrier no proposal attempt',c.execute('SELECT count(*) FROM native_proposal_attempt').fetchone()[0]==0)
    check('context barrier no evidence attempt',c.execute('SELECT count(*) FROM native_evidence_attempt').fetchone()[0]==0)
observed=context.invoke('work.read.release',{'release_digest':reservation['release_digest']})['release']
check('changed Release includes actual injected doc reference',any(ref['url']=='https://example.invalid/changed-context' and ref['ref_type']=='doc' for ref in observed['context_refs']))
check('context changed Release despite same full revision',observed['item_revision']==REVISION and reservation['release_digest']!=BASIS['release_digest'] and observed!=RELEASE)
check('context barrier halts all dependent owner effects',owner_counts(context)=={'intents':0,'proposal_keys':0,'evidence':0,'commits':0})
for stage in ('evidence','proposal'):
    check('context dependent request retained pending '+stage,context_state[1](stage+'-status')['pending_'+stage+'_request_ids']==[context_state[2][stage]['request_id']])
retained_requests(context_state)
RECEIPTS['results']['context_refusal']={'reservation':reservation,'changed_release':observed,'fault_receipt':ref,'barrier':'explicit orchestrator full Release comparison; no dependent sync invoked'}

def description_fault(authority,state,reservation,observed,tail):
    edit=authority.invoke('work.item.edit',{'item_id':ITEM,'description':'Changed after original prerequisites confirmed','expected_revision':REVISION.rsplit('@revise:',1)[0]},editor=True)
    check('description fault applied and revision changed',edit['previous_revision']!=edit['revision'])
    RECEIPTS['description_fault_receipt']=edit
    return rejected_proposal(authority,state,reservation,observed,tail,'effect-causal-stale-revision',1)

def evidence_fault(authority,state,reservation,observed,tail):
    competing=copy.deepcopy(EVIDENCE)
    competing.update(item_id='s4-competing-evidence',chain_seq=1,chain_prev_digest=BASIS['evidence_tail']['entry_digest'],idempotency_key='evidence-2',ref='local:competing.txt')
    appended=authority.invoke('work.evidence.append-v1',competing)
    current=authority.invoke('work.evidence.tail-v1',{'run_id':RUN})['item']
    check('competing evidence actually became exact next head',current['item_id']==competing['item_id'] and current['chain_seq']==1 and current['chain_prev_digest']==BASIS['evidence_tail']['entry_digest'] and pg.evidence_entry_digest(current)==pg.evidence_entry_digest(competing))
    RECEIPTS['competing_evidence_fault_receipt']=appended
    check('competing append response equals complete stored tail',appended['item']==current)
    return rejected_proposal(authority,state,reservation,observed,tail,'effect-causal-evidence-head-mismatch',2)

for database,name,hook in [('s4_stale_disposable','description-refusal',description_fault),('s4_tail_disposable','evidence-head-refusal',evidence_fault)]:
    authority=Authority(database,name)
    authority.start()
    authority.halt()
    state=capture(authority)
    authority.start()
    confirm(authority,state,before_proposal=hook)
RECEIPTS['status']='offline equivalence, four committed-response-loss recoveries and three independent causal refusal histories passed; evaluator and full S4 gates remain'
print('GREEN narrow causal pipeline, lost-response recoveries and independent refusal histories',flush=True)
