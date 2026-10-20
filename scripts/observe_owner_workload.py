#!/usr/bin/env python3
"""Collect a reviewed, bounded read cohort; never natural-usage or workflow acceptance.

Optional runtime dependencies are loaded only after the approved plan and source
bindings pass. Use --help without the released client installed. Live sampling
requires a separately reviewed plan digest, fixed mode, profile and source path.
Run the collector with `python -B`; run() also suppresses bytecode writes itself.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import sys
import time
from unittest.mock import patch
from urllib.parse import urlsplit

MODES = ('host-adapter-metadata', 'served-cli-inbox-read')
READ_OPERATION = 'work.message.read-v1'
READ_ARGUMENTS = {'after_seq': 0, 'limit': 1}
HANDSHAKE = ('GET', '/api/meta/v1/handshake')
CATALOG = ('GET', '/api/catalog/v1')
INVOKE = ('POST', '/api/invoke/v1')
METADATA = [HANDSHAKE, CATALOG]
# Sprintctl 0.21.0 (commit ca3aa1b, #2822) handshakes a fresh client before every
# authenticated invoke: served._invoke_operation runs handshake() then invoke(),
# and the released client's invoke() fetches the catalog first. 0.20.0 sent only
# catalog+invoke, so its sequence and request count are refused.
CLI_READ = [HANDSHAKE, CATALOG, INVOKE]
REQUIRED_SPRINTCTL = '0.21.0'
PREFLIGHT = METADATA
SEQUENCES = {MODES[0]: METADATA, MODES[1]: CLI_READ}
TRIALS = 5
# Budget = preflight + trials x per-trial sequence: 2 + 5x2 = 12, 2 + 5x3 = 17.
REQUEST_BUDGET = {mode: len(PREFLIGHT) + TRIALS * len(SEQUENCES[mode]) for mode in MODES}
BOUNDS = {'trials_per_mode': TRIALS, 'concurrent_requests': 1, 'inter_trial_seconds': 1,
          'max_wall_seconds_per_mode': 60, 'max_request_seconds': 5,
          'max_http_requests_per_mode': REQUEST_BUDGET, 'max_request_body_bytes': 4096,
          'max_response_body_bytes': 2097152, 'automatic_retries': 0,
          'warmup_samples_discarded': 0}
MODULES = ('sprintctl.cli', 'sprintctl.served', 'sprintctl.commands.inbox',
           'vuoro_client.client', 'vuoro_client.profile')
DEFAULT_PORTS = {'http': 80, 'https': 443}


class Refusal(Exception):
    """Bounded diagnostic reason, never a raw dependency/server exception."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def route(pair):
    return ' '.join(pair)


def budget_derivation(mode):
    return {'preflight_requests': len(PREFLIGHT), 'requests_per_trial': len(SEQUENCES[mode]),
            'trials': TRIALS, 'total': REQUEST_BUDGET[mode]}


def origin(url):
    parts = urlsplit(str(url))
    port = parts.port
    return parts.scheme, parts.hostname, None if port == DEFAULT_PORTS.get(parts.scheme) else port


def shape(value):
    """Only type/cardinality statistics: no keys, values, identifiers or body hashes."""
    result = {key: 0 for key in ('objects', 'arrays', 'strings', 'numbers', 'booleans', 'nulls',
                                'properties', 'string_utf8_bytes', 'max_depth', 'max_array_length')}
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise Refusal('shape-depth-limit')
        result['max_depth'] = max(result['max_depth'], depth)
        if isinstance(item, dict):
            result['objects'] += 1
            result['properties'] += len(item)
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            result['arrays'] += 1
            result['max_array_length'] = max(result['max_array_length'], len(item))
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            result['strings'] += 1
            result['string_utf8_bytes'] += len(item.encode('utf-8'))
        elif isinstance(item, bool):
            result['booleans'] += 1
        elif item is None:
            result['nulls'] += 1
        elif isinstance(item, (int, float)):
            result['numbers'] += 1
        else:
            raise Refusal('shape-invalid')
    return result


def load_plan(path, expected_digest):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise Refusal('plan-digest-mismatch')
    plan = json.loads(raw)
    if plan.get('schema_version') != 'agentops-controlled-read-plan/v1' or plan.get('bounds') != BOUNDS:
        raise Refusal('plan-bounds-mismatch')
    modes = plan.get('modes', {})
    if set(modes) != set(MODES):
        raise Refusal('plan-modes-mismatch')
    if (modes[MODES[0]].get('owner_operations') != [] or
            modes[MODES[1]].get('owner_operations') != [READ_OPERATION] or
            digest(modes[MODES[1]].get('arguments')) != digest(READ_ARGUMENTS)):
        raise Refusal('plan-operations-mismatch')
    if plan.get('preflight', {}).get('allowed_requests') != [route(x) for x in PREFLIGHT]:
        raise Refusal('plan-sequence-mismatch')
    for mode in MODES:
        if modes[mode].get('allowed_requests_per_trial') != [route(x) for x in SEQUENCES[mode]]:
            raise Refusal('plan-sequence-mismatch')
        if modes[mode].get('request_budget') != budget_derivation(mode):
            raise Refusal('plan-request-budget-mismatch')
    bindings = plan.get('bindings', {})
    if set(bindings) != {'versions', 'source_files', 'adapter_source_sha256', 'inventory_sha256',
                         'service_release_sha256', 'catalog_revision_sha256'}:
        raise Refusal('plan-bindings-invalid')
    if set(bindings['versions']) != {'sprintctl', 'vuoro-client', 'httpx'} or any(
            not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.+-]*', v) for v in bindings['versions'].values()):
        raise Refusal('plan-bindings-invalid')
    if bindings['versions']['sprintctl'] != REQUIRED_SPRINTCTL:
        raise Refusal('sprintctl-version-unsupported')
    if set(bindings['source_files']) != set(MODULES):
        raise Refusal('plan-bindings-invalid')
    hashes = [bindings[k] for k in bindings if k.endswith('_sha256')]
    for row in bindings['source_files'].values():
        if set(row) != {'sha256'}:
            raise Refusal('plan-bindings-invalid')
        hashes.append(row['sha256'])
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in hashes):
        raise Refusal('plan-bindings-invalid')
    return plan


def load_adapter(adapter_path):
    spec = importlib.util.spec_from_file_location('cohort_host_adapter', adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = adapter
    spec.loader.exec_module(adapter)
    return adapter


def check_bindings(plan, adapter_path, mode):
    bindings = plan['bindings']
    if hashlib.sha256(Path(adapter_path).read_bytes()).hexdigest() != bindings['adapter_source_sha256']:
        raise Refusal('adapter-source-mismatch')
    versions = bindings['versions']
    # A pre-handshake Sprintctl would send a different sequence; refuse it by name.
    if mode == MODES[1] and importlib.metadata.version('sprintctl') != REQUIRED_SPRINTCTL:
        raise Refusal('sprintctl-version-unsupported')
    for name in ('vuoro-client', 'httpx') + (('sprintctl',) if mode == MODES[1] else ()):
        if importlib.metadata.version(name) != versions[name]:
            raise Refusal('package-version-mismatch')
    for name in MODULES:
        if name.startswith('sprintctl.') and mode != MODES[1]:
            continue
        source = Path(importlib.util.find_spec(name).origin)
        if hashlib.sha256(source.read_bytes()).hexdigest() != bindings['source_files'][name]['sha256']:
            raise Refusal('client-source-mismatch')
    adapter = load_adapter(adapter_path)
    expected, basis = adapter._owner_inventory(adapter._declared_owner_operations())
    if basis['inventory_sha256'] != bindings['inventory_sha256']:
        raise Refusal('inventory-mismatch')
    return adapter, expected


class RequestGuard:
    """Admit only the declared sequence, within the per-mode request and wall budget.

    Every admitted request is recorded as an event at admission, so the event list
    is the complete record of what reached the transport, including failures.
    """

    def __init__(self, endpoint, repo_id, plan, mode, *, clock=time.monotonic):
        self.origin = origin(endpoint)
        self.repo_id, self.plan, self.clock = repo_id, plan, clock
        self.budget = REQUEST_BUDGET[mode]
        self.started = clock()
        self.deadline = self.started + BOUNDS['max_wall_seconds_per_mode']
        self.events, self.sequence = [], []
        self.position, self.in_flight, self.max_in_flight = 0, 0, 0
        self.reason = None
        self.phase, self.trial = 'preflight', None

    def offset(self):
        return self.clock() - self.started

    def refuse(self, reason):
        self.reason = self.reason or reason
        raise Refusal(reason)

    def check_wall(self):
        if self.clock() >= self.deadline:
            self.refuse('wall-time-limit')

    def begin(self, phase, sequence, trial=None):
        if self.position != len(self.sequence):
            self.refuse('incomplete-request-sequence')
        self.check_wall()
        self.phase, self.trial, self.sequence, self.position = phase, trial, sequence, 0

    def finish(self):
        if self.reason:
            raise Refusal(self.reason)
        if self.position != len(self.sequence):
            self.refuse('incomplete-request-sequence')

    def admit(self, request):
        if self.reason:  # refusals are final: nothing more is sent after one
            raise Refusal(self.reason)
        self.check_wall()
        if len(self.events) >= self.budget:
            self.refuse('request-count-limit')
        if self.in_flight:
            self.refuse('concurrency-limit')
        url = urlsplit(str(request.url))
        if origin(request.url) != self.origin or url.query or url.fragment:
            self.refuse('endpoint-mismatch')
        if self.position >= len(self.sequence) or (request.method, url.path) != self.sequence[self.position]:
            self.refuse('request-sequence-refused')
        body = request.content
        if len(body) > BOUNDS['max_request_body_bytes']:
            self.refuse('request-size-limit')
        if request.method == 'POST':
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeError):
                self.refuse('invocation-invalid')
            allowed = {'schema_version', 'request_id', 'operation', 'arguments', 'catalog_revision',
                       'basis_revision', 'idempotency_key', 'repo_id'}
            if (not isinstance(payload, dict) or set(payload) != allowed or
                    payload.get('schema_version') != 'invocation/v1' or
                    payload.get('operation') != READ_OPERATION or digest(payload.get('arguments')) != digest(READ_ARGUMENTS) or
                    payload.get('repo_id') != self.repo_id or payload.get('basis_revision') is not None or
                    payload.get('idempotency_key') is not None or
                    digest(payload.get('catalog_revision')) != self.plan['bindings']['catalog_revision_sha256']):
                self.refuse('invocation-refused')
        elif body:
            self.refuse('metadata-body-refused')
        self.position += 1
        return body, url.path

    async def send(self, request, transport):
        """Bound one admitted request; ``transport`` is the released client's own send."""
        body, path = self.admit(request)
        remaining = min(BOUNDS['max_request_seconds'], self.deadline - self.clock())
        request.extensions['timeout'] = dict.fromkeys(('connect', 'read', 'write', 'pool'), remaining)
        # This is a declared controlled condition, not a claim about
        # production compression ratios or total encrypted wire bytes.
        request.headers['Accept-Encoding'] = 'identity'
        start = self.clock()
        event = {'phase': self.phase, 'trial': self.trial, 'method': request.method, 'route': path,
                 'started_offset_seconds': start - self.started, 'request_body_bytes': len(body)}
        if body:
            event['canonical_arguments_bytes'] = len(json.dumps(READ_ARGUMENTS, sort_keys=True, separators=(',', ':')).encode())
        self.events.append(event)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        response, outcome = None, None
        try:
            async def read_bounded():
                nonlocal response
                response = await transport(request)
                # Defense in depth: the transport is called with follow_redirects=False;
                # a followed redirect would be an unadmitted second request.
                if getattr(response, 'history', None):
                    self.refuse('redirect-refused')
                if response.headers.get('content-encoding', 'identity').lower() not in ('identity', ''):
                    self.refuse('encoded-response-not-in-cohort')
                content = bytearray()
                async for chunk in response.aiter_raw():
                    if len(content) + len(chunk) > BOUNDS['max_response_body_bytes']:
                        self.refuse('response-size-limit')
                    content.extend(chunk)
                return type(response)(response.status_code, headers=response.headers, content=bytes(content),
                                      request=request, extensions=response.extensions)
            try:
                result = await asyncio.wait_for(read_bounded(), timeout=remaining)
            except asyncio.TimeoutError:
                self.refuse('request-timeout')
            version = result.http_version
            event.update({'status_code': result.status_code, 'response_body_bytes': len(result.content),
                          'http_version': version if version in ('HTTP/1.0', 'HTTP/1.1', 'HTTP/2') else 'unknown',
                          'encoding': 'identity'})
            stream = result.extensions.get('network_stream')
            tls = stream.get_extra_info('ssl_object') if stream and hasattr(stream, 'get_extra_info') else None
            tls_version = tls.version() if tls is not None else None
            event['tls_version'] = tls_version if tls_version in ('TLSv1.2', 'TLSv1.3') else 'unknown'
            if not result.is_success:  # includes every 3xx: redirects are never followed
                self.refuse('http-refused')
            try:
                response_json = result.json()
            except RecursionError:
                self.refuse('shape-depth-limit')
            except (ValueError, UnicodeError):
                self.refuse('response-json-invalid')
            try:
                event['response_shape'] = shape(response_json)
            except Refusal as exc:
                self.refuse(str(exc))
            if (request.method, path) in (CATALOG, HANDSHAKE) and not isinstance(response_json, dict):
                self.refuse('response-shape-refused')
            if (request.method, path) == CATALOG:
                if digest(response_json.get('revision')) != self.plan['bindings']['catalog_revision_sha256']:
                    self.refuse('catalog-revision-mismatch')
            if (request.method, path) == HANDSHAKE:
                if digest(response_json.get('service_release')) != self.plan['bindings']['service_release_sha256']:
                    self.refuse('service-release-mismatch')
            outcome = 'ok'
            return result
        except KeyboardInterrupt:
            outcome = 'interrupted'
            raise
        finally:
            event['outcome'] = outcome or self.reason or 'transport-error'
            event['duration_seconds'] = self.clock() - start
            if response is not None:
                await response.aclose()
            self.in_flight -= 1

    def client_type(self, base):
        guard = self
        class GuardedClient(base):
            async def send(self, request, **kwargs):
                return await guard.send(request, lambda req: super(GuardedClient, self).send(
                    req, stream=True, follow_redirects=False))
        return GuardedClient


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def run(plan, plan_digest, mode, profile_path, adapter_path, *, clock=time.monotonic, sleep=None):
    """Return a report whose status is complete, refused (nothing admitted) or incomplete."""
    sleep = sleep or time.sleep
    # Importing the adapter and released modules must not leave bytecode beside
    # them; the collector writes nothing locally and only prints its report.
    previous_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    started, started_at = clock(), utc_now()
    report = {'schema_version': 'agentops-controlled-read-observation/v1', 'plan_sha256': plan_digest,
              'mode': mode, 'status': 'refused', 'reason': 'local-preflight-unavailable', 'samples': [],
              'traffic_kind': 'controlled qualification; not natural usage', 'workflow_acceptance': 'unknown',
              'population_representativeness': 'unknown', 'estate_completeness': 'unknown', 'events': []}
    guard = None
    try:
        adapter, expected = check_bindings(plan, adapter_path, mode)
        from vuoro_client import AsyncVuoroClient
        from vuoro_client.profile import load_profile
        import httpx
        profile = load_profile(profile_path)
        profile_stamp = hashlib.sha256(Path(profile_path).read_bytes()).digest()
        # CLI must use its existing repository marker; no markerless override.
        repo_id = 'agentops'
        if mode == MODES[1]:
            marker = json.loads(Path('.sprintctl/backend.json').read_text())
            if marker.get('backend') != 'served' or marker.get('repo_id') != repo_id:
                raise Refusal('repository-binding-mismatch')
        guard = RequestGuard(profile.endpoint, repo_id, plan, mode, clock=clock)
        report['bindings'] = plan['bindings']
        report['network_conditions'] = {'proxy_configuration_present': any(os.environ.get(k) for k in
            ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')),
            'tls_proxy_setup': 'released client defaults preserved', 'accept_encoding': 'identity',
            'concurrency': 'controlled sequential; not observed estate traffic'}
        async def preflight():
            async with AsyncVuoroClient(profile, adapter._file_credential) as client:
                await client.handshake()
                catalog = await client.catalog(force_refresh=True)
                rows = adapter._owner_catalog_rows({READ_OPERATION: expected[READ_OPERATION]}, catalog, client.supported_schema_features)
                if rows[0]['status'] != 'exact-match':
                    raise Refusal('read-contract-mismatch')
        with patch('httpx.AsyncClient', guard.client_type(httpx.AsyncClient)):
            guard.begin('preflight', PREFLIGHT)
            asyncio.run(preflight())
            guard.finish()
            for trial in range(TRIALS):
                if trial:
                    sleep(BOUNDS['inter_trial_seconds'])
                if hashlib.sha256(Path(profile_path).read_bytes()).digest() != profile_stamp:
                    raise Refusal('profile-changed')
                guard.begin('trial', SEQUENCES[mode], trial)
                trial_started, first_event = clock(), len(guard.events)
                if mode == MODES[0]:
                    observed = adapter.inspect_owner(profile_path)
                    if observed['status'] != 'exact-match':
                        raise Refusal('adapter-inspection-refused')
                    result_count = len(observed['operations'])
                    result_kind = 'contract-operations'
                else:
                    from sprintctl.cli import cli
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with patch.dict(os.environ, {'SPRINTCTL_BACKEND': 'served', 'SPRINTCTL_VUORO_PROFILE': str(profile_path)}), \
                            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = cli.main(args=['message', 'read', '--after-seq', '0', '--limit', '1'], standalone_mode=False)
                    if code not in (None, 0):
                        raise Refusal('cli-exit-nonzero')
                    rendered = stdout.getvalue()
                    if len(rendered.encode()) > BOUNDS['max_response_body_bytes']:
                        raise Refusal('cli-output-size-limit')
                    result = json.loads(rendered)
                    result_count = len(result['messages'])
                    if result_count > 1:
                        raise Refusal('read-count-limit')
                    result_kind = 'messages'
                guard.finish()
                report['samples'].append({'trial': trial, 'started_offset_seconds': trial_started - guard.started,
                                          'duration_seconds': clock() - trial_started,
                                          'requests': len(guard.events) - first_event,
                                          'result_kind': result_kind, 'result_count': result_count,
                                          'empty': result_count == 0})
            if len(guard.events) != REQUEST_BUDGET[mode]:
                guard.refuse('request-budget-mismatch')
        report['status'] = 'complete'
        report.pop('reason')
    except BaseException as exc:
        if not isinstance(exc, (Exception, SystemExit, KeyboardInterrupt)):
            raise
        # An operator interrupt still yields the report for what was already sent;
        # main() then exits 130.
        report['reason'] = ('interrupted' if isinstance(exc, KeyboardInterrupt) else
                            guard.reason if guard and guard.reason else
                            str(exc) if isinstance(exc, Refusal) else 'dependency-or-transport-refused')
        # Once anything reached the transport the run is a partial cohort, kept
        # with its completed samples; refused means nothing was admitted.
        report['status'] = 'incomplete' if guard and guard.events else 'refused'
    finally:
        sys.dont_write_bytecode = previous_bytecode
        if guard:
            report['events'] = guard.events
            report['max_observed_in_flight'] = guard.max_in_flight
        report['window'] = {'started_at_utc': started_at, 'ended_at_utc': utc_now(),
                            'elapsed_seconds': clock() - started,
                            'max_wall_seconds': BOUNDS['max_wall_seconds_per_mode'],
                            'request_budget': REQUEST_BUDGET[mode],
                            'request_budget_derivation': budget_derivation(mode),
                            'requests_sent': len(report['events']),
                            'trials_planned': TRIALS, 'trials_completed': len(report['samples'])}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--mode', choices=MODES, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--adapter-script', required=True)
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan, args.plan_sha256)
        report = run(plan, args.plan_sha256, args.mode, args.profile, args.adapter_script)
    except Exception as exc:
        report = {'status': 'refused', 'reason': str(exc) if isinstance(exc, Refusal) else 'plan-unavailable', 'samples': []}
    print(json.dumps(report, sort_keys=True, indent=2))
    if report['status'] == 'complete':
        return 0
    return 130 if report.get('reason') == 'interrupted' else 2


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
