"""Offline plan and privacy tests; no optional client dependency or network."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import signal
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import observe_owner_workload as cohort

PLAN = Path(__file__).resolve().parents[2] / 'verification/fixtures/ec01-controlled-read-cohort-2733.json'


def test_shape_retains_no_keys_values_ids_or_hashes():
    private = {'SECRET-KEY': [{'id': 'SECRET-ID', 'token': 'SECRET-TOKEN', 'cursor': 12345}], 'empty': None}
    result = cohort.shape(private)
    assert result['objects'] == 2
    assert result['arrays'] == 1
    assert result['strings'] == 2
    assert result['numbers'] == 1
    assert result['nulls'] == 1
    assert not any(value in json.dumps(result) for value in ('SECRET', '12345', 'token', 'cursor'))


def test_shape_distinguishes_null_empty_zero_and_false():
    result = cohort.shape([None, '', [], {}, 0, False])
    assert {key:result[key] for key in ('nulls','strings','arrays','objects','numbers','booleans')} == {
        'nulls':1,'strings':1,'arrays':2,'objects':1,'numbers':1,'booleans':1}


def test_approved_plan_parses_with_exact_digest():
    assert cohort.load_plan(PLAN, hashlib.sha256(PLAN.read_bytes()).hexdigest())['bounds'] == cohort.BOUNDS


def test_plan_digest_mismatch_refuses():
    with pytest.raises(cohort.Refusal, match='plan-digest-mismatch'):
        cohort.load_plan(PLAN, '0'*64)


@pytest.mark.parametrize('alter', [
    lambda p:p['bounds'].update(trials_per_mode=6),
    lambda p:p['modes']['served-cli-inbox-read'].update(owner_operations=['work.message.send-v1']),
    lambda p:p['modes']['served-cli-inbox-read']['arguments'].update(limit=True),
    lambda p:p['modes']['served-cli-inbox-read']['arguments'].update(after_seq=False),
    lambda p:p['modes']['host-adapter-metadata']['allowed_requests_per_trial'].append('POST /api/invoke/v1'),
    lambda p:p['bindings'].update(private_token='SECRET'),
    lambda p:p['bindings']['source_files']['sprintctl.cli'].update(path='/private/path'),
    lambda p:p['bindings']['versions'].update(httpx='SECRET'),
])
def test_modified_allowlist_or_private_binding_fields_refuse(tmp_path, alter):
    plan = json.loads(PLAN.read_text())
    alter(plan)
    path=tmp_path/'plan.json';path.write_text(json.dumps(plan))
    with pytest.raises(cohort.Refusal):
        cohort.load_plan(path,hashlib.sha256(path.read_bytes()).hexdigest())


def test_bad_plan_cli_emits_bounded_failure_without_raw_exception(tmp_path, capsys):
    assert cohort.main(['--plan',str(tmp_path/'PRIVATE'),'--plan-sha256','0'*64,
                        '--mode','host-adapter-metadata','--profile','PRIVATE',
                        '--adapter-script','PRIVATE']) == 2
    rendered=capsys.readouterr().out
    assert 'PRIVATE' not in rendered
    assert json.loads(rendered)['status']=='refused'


def _plan_digest(tmp_path, plan):
    path = tmp_path / 'plan.json'; path.write_text(json.dumps(plan))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_request_budget_is_derived_from_the_handshake_sequence():
    assert cohort.CLI_READ == [('GET', '/api/meta/v1/handshake'), ('GET', '/api/catalog/v1'), ('POST', '/api/invoke/v1')]
    assert cohort.REQUEST_BUDGET == {'host-adapter-metadata': 2 + 5 * 2, 'served-cli-inbox-read': 2 + 5 * 3}
    plan = json.loads(PLAN.read_text())
    for mode in cohort.MODES:
        row = plan['modes'][mode]['request_budget']
        assert row['total'] == row['preflight_requests'] + row['trials'] * row['requests_per_trial']
        assert plan['bounds']['max_http_requests_per_mode'][mode] == row['total']


@pytest.mark.parametrize('alter,reason', [
    # The 0.20.0 per-trial sequence (no handshake) and its 12-request cap.
    (lambda p: p['modes']['served-cli-inbox-read'].update(allowed_requests_per_trial=['GET /api/catalog/v1', 'POST /api/invoke/v1']),
     'plan-sequence-mismatch'),
    (lambda p: p['bounds'].update(max_http_requests_per_mode=12), 'plan-bounds-mismatch'),
    (lambda p: p['modes']['served-cli-inbox-read']['request_budget'].update(requests_per_trial=2, total=12),
     'plan-request-budget-mismatch'),
    (lambda p: p['bindings']['versions'].update(sprintctl='0.20.0'), 'sprintctl-version-unsupported'),
])
def test_pre_handshake_plan_refuses(tmp_path, alter, reason):
    plan = json.loads(PLAN.read_text()); alter(plan)
    with pytest.raises(cohort.Refusal, match=reason):
        cohort.load_plan(*_plan_digest(tmp_path, plan))


def test_installed_sprintctl_0_20_refuses_before_network(tmp_path, monkeypatch):
    adapter = tmp_path / 'adapter.py'; adapter.write_text('raise AssertionError("adapter must not load")\n')
    plan = json.loads(PLAN.read_text())
    plan['bindings']['adapter_source_sha256'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    installed = {'sprintctl': '0.20.0', 'vuoro-client': '0.1.1', 'httpx': '0.28.1'}
    monkeypatch.setattr(cohort.importlib.metadata, 'version', installed.__getitem__)
    with pytest.raises(cohort.Refusal, match='sprintctl-version-unsupported'):
        cohort.check_bindings(plan, adapter, 'served-cli-inbox-read')


# --- Guard bounds with fake request/response objects; no optional client. ---

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeRequest:
    def __init__(self, method, path, body=b'', url=None):
        self.method, self.content = method, body
        self.url = url or 'https://fixture.invalid' + path
        self.headers, self.extensions = {}, {}


class FakeResponse:
    """Mimics the httpx.Response surface the guard reads and reconstructs."""
    closed = []

    def __init__(self, status_code, headers=None, content=b'', request=None, extensions=None, chunks=None, delay=0):
        self.status_code, self.headers, self.content = status_code, headers or {}, content
        self.extensions = extensions or {}
        self.chunks, self.delay = [content] if chunks is None else chunks, delay
        self.http_version = 'HTTP/1.1'

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return json.loads(self.content)

    async def aiter_raw(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        FakeResponse.closed.append(self)


def _fixture_plan():
    plan = json.loads(PLAN.read_text())
    plan['bindings']['service_release_sha256'] = cohort.digest({'version': 'fixture'})
    plan['bindings']['catalog_revision_sha256'] = cohort.digest('fixture')
    return plan


def _invoke_body():
    return json.dumps({'schema_version': 'invocation/v1', 'request_id': 'r', 'operation': cohort.READ_OPERATION,
                       'arguments': dict(cohort.READ_ARGUMENTS), 'catalog_revision': 'fixture',
                       'basis_revision': None, 'idempotency_key': None, 'repo_id': 'agentops'}).encode()


class FakeServer:
    def __init__(self):
        self.calls, self.delay, self.chunks, self.slow_at = [], 0, None, None
        self.raw, self.history, self.interrupt_at, self.sigint_at = {}, [], None, None

    async def __call__(self, request):
        path = cohort.urlsplit(str(request.url)).path
        self.calls.append((request.method, path))
        if self.delay or len(self.calls) == self.slow_at:
            await asyncio.sleep(self.delay or 1)
        if len(self.calls) == self.interrupt_at:
            raise KeyboardInterrupt
        if len(self.calls) == self.sigint_at:
            signal.raise_signal(signal.SIGINT)
            await asyncio.sleep(0)  # the runner's cancellation lands here, in flight
        body = {'/api/meta/v1/handshake': {'service_release': {'version': 'fixture'}},
                '/api/catalog/v1': {'revision': 'fixture'}}.get(path, {'status': 'accepted'})
        response = FakeResponse(200, content=self.raw.get(path, json.dumps(body).encode()), chunks=self.chunks)
        response.history = self.history
        return response


def _request(pair):
    return FakeRequest(*pair, body=_invoke_body() if pair[0] == 'POST' else b'')


def _send(guard, server, pair):
    return asyncio.run(guard.send(_request(pair), server))


def _guard(mode='served-cli-inbox-read'):
    clock = FakeClock()
    return cohort.RequestGuard('https://fixture.invalid', 'agentops', _fixture_plan(), mode, clock=clock), clock, FakeServer()


def test_guard_admits_exactly_the_handshake_budget_then_refuses_count():
    guard, _, server = _guard()
    guard.begin('preflight', cohort.PREFLIGHT)
    for pair in cohort.PREFLIGHT:
        _send(guard, server, pair)
    guard.finish()
    for trial in range(5):
        guard.begin('trial', cohort.CLI_READ, trial)
        for pair in cohort.CLI_READ:
            _send(guard, server, pair)
        guard.finish()
    assert len(server.calls) == len(guard.events) == 17
    assert all(event['outcome'] == 'ok' for event in guard.events)
    # A sixth in-sequence trial would be the 18th request: refused before transport.
    guard.begin('trial', cohort.CLI_READ, 5)
    with pytest.raises(cohort.Refusal, match='request-count-limit'):
        _send(guard, server, cohort.HANDSHAKE)
    assert len(server.calls) == 17


def test_metadata_mode_budget_is_twelve():
    guard, _, server = _guard('host-adapter-metadata')
    for trial in range(6):
        guard.begin('trial', cohort.METADATA, trial)
        for pair in cohort.METADATA:
            _send(guard, server, pair)
    guard.begin('trial', cohort.METADATA, 6)
    with pytest.raises(cohort.Refusal, match='request-count-limit'):
        _send(guard, server, cohort.HANDSHAKE)
    assert len(server.calls) == 12


@pytest.mark.parametrize('sent', [
    [cohort.CATALOG],                     # 0.20.0 order: catalog without handshake
    [cohort.HANDSHAKE, cohort.INVOKE],    # invoke without catalog
    [cohort.HANDSHAKE, cohort.HANDSHAKE],  # repeated handshake
])
def test_trial_outside_handshake_sequence_never_reaches_transport(sent):
    guard, _, server = _guard()
    guard.begin('trial', cohort.CLI_READ, 0)
    with pytest.raises(cohort.Refusal, match='request-sequence-refused'):
        for pair in sent:
            _send(guard, server, pair)
    assert server.calls == sent[:-1]


def test_trial_stopping_before_invoke_is_an_incomplete_sequence():
    guard, _, server = _guard()
    guard.begin('trial', cohort.CLI_READ, 0)
    _send(guard, server, cohort.HANDSHAKE); _send(guard, server, cohort.CATALOG)
    with pytest.raises(cohort.Refusal, match='incomplete-request-sequence'):
        guard.finish()


def test_explicit_five_second_request_timeout_refuses(monkeypatch):
    guard, _, server = _guard()
    server.delay = 1
    seen = []
    real = asyncio.wait_for
    async def short_wait_for(awaitable, timeout):
        seen.append(timeout)
        return await real(awaitable, timeout=0.01)
    monkeypatch.setattr(cohort.asyncio, 'wait_for', short_wait_for)
    guard.begin('trial', cohort.CLI_READ, 0)
    request = _request(cohort.HANDSHAKE)
    with pytest.raises(cohort.Refusal, match='request-timeout'):
        asyncio.run(guard.send(request, server))
    assert seen == [5]
    assert request.extensions['timeout'] == dict.fromkeys(('connect', 'read', 'write', 'pool'), 5)
    assert request.headers['Accept-Encoding'] == 'identity'
    assert guard.events[0]['outcome'] == 'request-timeout' and 'status_code' not in guard.events[0]
    assert guard.in_flight == 0


def test_request_timeout_shrinks_to_the_remaining_wall_time():
    guard, clock, server = _guard()
    clock.now = guard.deadline - 0.5
    guard.begin('trial', cohort.CLI_READ, 0)
    request = _request(cohort.HANDSHAKE)
    assert asyncio.run(guard.send(request, server)).status_code == 200
    assert request.extensions['timeout']['read'] == 0.5


def test_wall_cap_refuses_before_transport():
    guard, clock, server = _guard()
    guard.begin('trial', cohort.CLI_READ, 0)
    clock.now = guard.started + 60
    with pytest.raises(cohort.Refusal, match='wall-time-limit'):
        _send(guard, server, cohort.HANDSHAKE)
    assert server.calls == [] and guard.events == []
    guard, clock, server = _guard()
    clock.now = guard.started + 60
    with pytest.raises(cohort.Refusal, match='wall-time-limit'):
        guard.begin('trial', cohort.CLI_READ, 1)


def test_response_and_request_body_caps_refuse():
    guard, _, server = _guard()
    server.chunks = [b'x' * 2097152, b'x']
    guard.begin('trial', cohort.CLI_READ, 0)
    FakeResponse.closed.clear()
    with pytest.raises(cohort.Refusal, match='response-size-limit'):
        _send(guard, server, cohort.HANDSHAKE)
    assert len(FakeResponse.closed) == 1 and guard.events[0]['outcome'] == 'response-size-limit'
    guard, _, server = _guard()
    guard.begin('trial', [cohort.INVOKE], 0)
    with pytest.raises(cohort.Refusal, match='request-size-limit'):
        asyncio.run(guard.send(FakeRequest('POST', '/api/invoke/v1', body=b' ' * 4097), server))
    assert server.calls == []


# --- run() with fake released-client modules: statuses, windows, no local writes. ---

FAKE_ADAPTER = '''
import asyncio
def _declared_owner_operations(): return []
def _owner_inventory(names): return {'work.message.read-v1': {}}, {'inventory_sha256': 'fixture'}
def _file_credential(ref): raise AssertionError('fixture client reads no credential')
def _owner_catalog_rows(expected, catalog, supported): return [{'status': 'exact-match'}]
def inspect_owner(profile_path):
    from vuoro_client import AsyncVuoroClient
    async def inspect():
        async with AsyncVuoroClient(None, None) as client:
            await client.handshake(); await client.catalog(force_refresh=True)
    asyncio.run(inspect())
    return {'status': 'exact-match', 'operations': [{}] * 14}
'''


@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    """A read-only HOME/XDG/cwd plus fake httpx and vuoro_client modules."""
    import types
    server = FakeServer()
    class AsyncClient:
        async def send(self, request, stream=False, follow_redirects=True):
            return await server(request)
    class AsyncVuoroClient:
        supported_schema_features = frozenset()
        def __init__(self, profile, resolver):
            pass
        async def __aenter__(self):
            self.http = sys.modules['httpx'].AsyncClient(); return self
        async def __aexit__(self, *exc):
            return False
        async def _get(self, pair):
            return (await self.http.send(FakeRequest(*pair))).json()
        async def handshake(self):
            return await self._get(cohort.HANDSHAKE)
        async def catalog(self, force_refresh=False):
            return await self._get(cohort.CATALOG)
    httpx = types.ModuleType('httpx'); httpx.AsyncClient = AsyncClient
    client = types.ModuleType('vuoro_client'); client.AsyncVuoroClient = AsyncVuoroClient
    profile = types.ModuleType('vuoro_client.profile')
    profile.load_profile = lambda path: types.SimpleNamespace(endpoint='https://fixture.invalid')
    for name, module in (('httpx', httpx), ('vuoro_client', client), ('vuoro_client.profile', profile)):
        monkeypatch.setitem(sys.modules, name, module)
    adapter_dir = tmp_path / 'adapter'; adapter_dir.mkdir()
    adapter = adapter_dir / 'fake_host_adapter.py'; adapter.write_text(FAKE_ADAPTER)
    profile_path = tmp_path / 'profile.json'; profile_path.write_text('{}')
    def bindings(plan, adapter_path, mode):
        loaded = cohort.load_adapter(adapter_path)
        return loaded, loaded._owner_inventory([])[0]
    monkeypatch.setattr(cohort, 'check_bindings', bindings)
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    state = {name: tmp_path / name for name in ('home', 'xdg-state', 'xdg-cache', 'xdg-config', 'xdg-data', 'cwd')}
    for directory in state.values():
        directory.mkdir()
    for key, name in (('HOME', 'home'), ('XDG_STATE_HOME', 'xdg-state'), ('XDG_CACHE_HOME', 'xdg-cache'),
                      ('XDG_CONFIG_HOME', 'xdg-config'), ('XDG_DATA_HOME', 'xdg-data')):
        monkeypatch.setenv(key, str(state[name]))
    monkeypatch.chdir(state['cwd'])
    # State dirs are read-only; the adapter dir stays writable so a bytecode write would show.
    for directory in state.values():
        directory.chmod(0o500)
    clock = FakeClock()
    def sleep(seconds):
        clock.now += seconds
    def run(**kwargs):
        return cohort.run(_fixture_plan(), 'fixture-plan', 'host-adapter-metadata', profile_path, adapter,
                          clock=clock, sleep=sleep, **kwargs)
    yield types.SimpleNamespace(run=run, server=server, clock=clock, state=state, adapter_dir=adapter_dir,
                                client=AsyncVuoroClient)
    for directory in state.values():
        directory.chmod(0o700)


def _assert_no_local_writes(env):
    assert sys.dont_write_bytecode is False
    for directory in env.state.values():
        assert list(directory.rglob('*')) == [], directory
    assert [p.name for p in env.adapter_dir.iterdir()] == ['fake_host_adapter.py']


def _assert_window_complete(report, trials):
    window = report['window']
    assert set(window) == {'started_at_utc', 'ended_at_utc', 'elapsed_seconds', 'max_wall_seconds', 'request_budget',
                           'request_budget_derivation', 'requests_sent', 'trials_planned', 'trials_completed'}
    assert window['requests_sent'] == len(report['events']) and window['trials_completed'] == trials == len(report['samples'])
    assert window['ended_at_utc'] >= window['started_at_utc'] and window['elapsed_seconds'] >= 0
    assert [row['trial'] for row in report['samples']] == list(range(trials))
    offsets = [event['started_offset_seconds'] for event in report['events']]
    assert offsets == sorted(offsets)
    for event in report['events']:
        assert {'phase', 'trial', 'method', 'route', 'outcome', 'duration_seconds', 'request_body_bytes'} <= set(event)


def test_fake_run_complete_has_exact_budget_window_and_no_local_writes(fake_run):
    report = fake_run.run()
    assert report['status'] == 'complete', report
    assert 'reason' not in report
    assert fake_run.server.calls == cohort.METADATA * 6
    assert report['window']['request_budget'] == report['window']['requests_sent'] == 12
    assert all(row['requests'] == 2 for row in report['samples'])
    assert report['workflow_acceptance'] == report['estate_completeness'] == 'unknown'
    assert report['traffic_kind'] == 'controlled qualification; not natural usage'
    _assert_window_complete(report, 5)
    _assert_no_local_writes(fake_run)


def test_fake_run_failure_after_traffic_is_incomplete_with_samples_kept(fake_run, monkeypatch):
    real = asyncio.wait_for
    async def short_wait_for(awaitable, timeout):
        return await real(awaitable, timeout=min(timeout, 0.05))
    monkeypatch.setattr(cohort.asyncio, 'wait_for', short_wait_for)
    fake_run.server.slow_at = 2 + 2 * 2 + 1  # first request of the third trial stalls
    report = fake_run.run()
    assert report['status'] == 'incomplete', report
    assert report['reason'] == 'request-timeout'
    assert len(report['samples']) == 2
    assert report['events'][-1]['outcome'] == 'request-timeout' and report['events'][-1]['trial'] == 2
    _assert_window_complete(report, 2)
    _assert_no_local_writes(fake_run)


def test_fake_run_wall_cap_between_trials_is_incomplete(fake_run, monkeypatch):
    monkeypatch.setitem(cohort.BOUNDS, 'inter_trial_seconds', 30)
    report = fake_run.run()
    assert report['status'] == 'incomplete' and report['reason'] == 'wall-time-limit'
    assert len(report['samples']) == 2
    _assert_window_complete(report, 2)


def test_fake_run_refusal_before_traffic_is_refused_and_restores_bytecode_flag(fake_run, monkeypatch):
    seen = []
    def refuse(plan, adapter_path, mode):
        seen.append(sys.dont_write_bytecode)
        raise cohort.Refusal('client-source-mismatch')
    monkeypatch.setattr(cohort, 'check_bindings', refuse)
    report = fake_run.run()
    assert seen == [True]
    assert report['status'] == 'refused' and report['reason'] == 'client-source-mismatch'
    assert fake_run.server.calls == [] and report['events'] == []
    _assert_window_complete(report, 0)
    _assert_no_local_writes(fake_run)


# --- Review follow-ups: final refusals, redirects, payload/shape guards, interrupts. ---

def test_refusal_is_final_for_later_valid_requests():
    guard, _, server = _guard()
    guard.begin('trial', cohort.CLI_READ, 0)
    with pytest.raises(cohort.Refusal, match='request-sequence-refused'):
        _send(guard, server, cohort.CATALOG)
    with pytest.raises(cohort.Refusal, match='request-sequence-refused'):
        _send(guard, server, cohort.HANDSHAKE)  # in sequence, but after a refusal
    assert server.calls == [] and guard.events == []


def test_followed_redirect_history_is_refused():
    guard, _, server = _guard()
    server.history = [object()]
    guard.begin('trial', cohort.CLI_READ, 0)
    with pytest.raises(cohort.Refusal, match='redirect-refused'):
        _send(guard, server, cohort.HANDSHAKE)
    assert guard.events[0]['outcome'] == 'redirect-refused'


def test_invoke_for_another_repository_is_refused():
    guard, _, server = _guard()
    guard.begin('trial', [cohort.INVOKE], 0)
    body = json.loads(_invoke_body()); body['repo_id'] = 'other-repo'
    with pytest.raises(cohort.Refusal, match='invocation-refused'):
        asyncio.run(guard.send(FakeRequest('POST', '/api/invoke/v1', body=json.dumps(body).encode()), server))
    assert server.calls == []


def test_metadata_request_with_body_is_refused():
    guard, _, server = _guard()
    guard.begin('trial', cohort.CLI_READ, 0)
    with pytest.raises(cohort.Refusal, match='metadata-body-refused'):
        asyncio.run(guard.send(FakeRequest('GET', '/api/meta/v1/handshake', body=b'{}'), server))
    assert server.calls == []


def test_second_request_in_flight_is_refused():
    guard, _, server = _guard()
    server.delay = 0.05
    guard.begin('trial', cohort.CLI_READ, 0)
    async def both():
        return await asyncio.gather(guard.send(_request(cohort.HANDSHAKE), server),
                                    guard.send(_request(cohort.CATALOG), server), return_exceptions=True)
    first, second = asyncio.run(both())
    assert isinstance(second, cohort.Refusal) and str(second) == 'concurrency-limit'
    assert server.calls == [cohort.HANDSHAKE] and guard.max_in_flight == 1


def test_swallowed_refusal_is_reraised_at_trial_end():
    guard, _, server = _guard()
    server.raw['/api/meta/v1/handshake'] = json.dumps({'service_release': {'version': 'changed'}}).encode()
    guard.begin('trial', [cohort.HANDSHAKE], 0)
    try:  # a client that catches the error and returns normally
        _send(guard, server, cohort.HANDSHAKE)
    except cohort.Refusal:
        pass
    assert guard.position == len(guard.sequence)
    with pytest.raises(cohort.Refusal, match='service-release-mismatch'):
        guard.finish()


@pytest.mark.parametrize('raw,reason', [
    (b'[]', 'response-shape-refused'),
    (b'"text"', 'response-shape-refused'),
    (b'[' * 70 + b']' * 70, 'shape-depth-limit'),
    (b'[' * 200000 + b']' * 200000, 'shape-depth-limit'),  # RecursionError in the JSON decoder
])
def test_malformed_metadata_json_gets_a_bounded_outcome(raw, reason):
    guard, _, server = _guard()
    server.raw['/api/catalog/v1'] = raw
    guard.begin('trial', [cohort.CATALOG], 0)
    with pytest.raises(cohort.Refusal, match=reason):
        _send(guard, server, cohort.CATALOG)
    assert guard.events[0]['outcome'] == reason


def test_fake_run_guard_created_but_nothing_sent_is_refused(fake_run, monkeypatch):
    async def broken(self):
        raise RuntimeError('SECRET client failure')
    monkeypatch.setattr(fake_run.client, 'handshake', broken)
    report = fake_run.run()
    assert 'network_conditions' in report  # the guard existed
    assert report['status'] == 'refused' and report['reason'] == 'dependency-or-transport-refused'
    assert report['events'] == [] and 'SECRET' not in json.dumps(report)
    _assert_window_complete(report, 0)


def test_fake_run_interrupt_after_traffic_reports_incomplete(fake_run):
    fake_run.server.interrupt_at = 2 + 2 + 1  # first request of the second trial
    report = fake_run.run()
    assert report['status'] == 'incomplete' and report['reason'] == 'interrupted'
    assert len(report['samples']) == 1
    assert report['events'][-1]['outcome'] == 'interrupted'
    _assert_window_complete(report, 1)
    _assert_no_local_writes(fake_run)


def test_interrupted_report_exits_130(monkeypatch, capsys):
    monkeypatch.setattr(cohort, 'load_plan', lambda path, digest: {})
    monkeypatch.setattr(cohort, 'run', lambda *args: {'status': 'incomplete', 'reason': 'interrupted', 'samples': []})
    assert cohort.main(['--plan', 'p', '--plan-sha256', '0' * 64, '--mode', 'host-adapter-metadata',
                        '--profile', 'p', '--adapter-script', 'a']) == 130
    assert json.loads(capsys.readouterr().out)['status'] == 'incomplete'


def test_fake_run_sigint_cancellation_in_flight_is_interrupted(fake_run):
    # asyncio.run handles SIGINT by cancelling the task, then raises KeyboardInterrupt.
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    fake_run.server.sigint_at = 2 + 2 + 2  # second request of the second trial
    report = fake_run.run()
    assert report['status'] == 'incomplete' and report['reason'] == 'interrupted', report
    assert report['events'][-1]['outcome'] == 'interrupted'
    assert [event['outcome'] for event in report['events'][:-1]] == ['ok'] * 5
    _assert_window_complete(report, 1)
