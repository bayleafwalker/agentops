# OpenCode v2 host-adapter compatibility

Status: implementation and qualification in progress; not a deployment or
permission to launch. Owner work item: `agentops#2874` (served sprintctl).

## Observed failure

On 2026-11-03, the live devbox inbox was running OpenCode 2.0.32. Its installed
host adapter was pinned to agentops `c2078f27b6d48fdc4a3c28a6a423ff4896ccb748`.
Using the adapter identity's existing service credential without disclosing it,
`GET /global/health` and `GET /session/status?directory=/tmp` returned HTTP 200
with `text/html`; the adapter expects JSON from the OpenCode 1.19 API. The v2
`GET /api/session/active` returned JSON and zero active sessions at inspection.

The adapter treats a non-JSON health response as unhealthy and defers launching.
It can still acknowledge, accept, and register an inbox run before reaching
that health gate. Active systemd units therefore establish process liveness,
not a functioning continuation route. The zero-active result is a point-in-time
observation, not a future quiescence guarantee.

An isolated, network-namespaced probe of the exact 2.0.32 binary used temporary
HOME/XDG directories, a synthetic credential and no inherited provider access.
The retained [sanitized API observations](../evidence/2026-11-03-opencode-v2/api-probe.json)
record request and response shapes. Source documentation and current public
schemas may describe later releases; qualification must target the installed
binary, not infer behavior from a newer schema.

## Required behavior

1. Preserve the legacy transport for already-qualified v1 installations. Detect
   supported API versions with read-only requests and strictly validated JSON;
   HTML, malformed results and unknown versions are unavailable, not healthy.
2. Map the full v2 lifecycle: exact-directory/title discovery with bounded
   pagination, creation with the registered model, effective ordered
   permissions, prompt admission, active status and paginated terminal messages,
   interruption and recovery. A prompt acknowledgement is not completion.
3. Preserve the successor's narrow authority. The v2 ordered
   `action/resource/effect` permission rules differ from v1's
   `permission/pattern/action` format. Verify the effective server rules and
   exercise actual allowed owner commands and denied shell, file, network and
   delegation actions in an isolated environment; equality of a stored JSON
   list alone is not containment evidence.
4. Preserve attempt and owner boundaries. A lost create response must not cause
   a second session. A lost prompt response must not cause duplicate work;
   reconcile the exact input identity and authoritative inbox/message state.
   A prompt may be durably admitted before inbox or message projections expose
   it; empty projections cannot by themselves authorize resubmission.
   A repeated prompt ID coalesced in one disposable 2.0.32 probe, but that is
   not proof of exactly-once execution under every failure or restart.
5. Distinguish never-started, queued, active, succeeded, failed, interrupted
   and unknown. Tie terminal evidence to the current admitted input, not a
   stale session outcome from an earlier turn. Absence from the active map,
   assistant intermediate messages and interrupt acknowledgements are not
   terminal outcome proof. Missing pages, ambiguous identities,
   mismatched model/directory/permissions, and unobserved cancellation must not
   settle an attempt as successful.
6. Retain v1 regression tests; add v2 tests for malformed or HTML responses,
   permission drift, pagination, duplicate and ambiguous sessions, prompt
   response loss, intermediate tool turns, cancellation races, and restart
   recovery. Force each new negative control to fail without its protection.
7. Exercise the exact pinned OpenCode binary with a disposable loopback fake
   provider, synthetic owner fixtures and no real credentials: create, bind,
   continue, deny forbidden tools, interrupt, recover and revoke. Then update
   the NixOS package pin and separately qualify the installed service and owner
   evidence. A source merge or native CLI marker is not installed-service proof.

The devbox native agent-home Flash model correction is independent: it repairs
an unavailable default, and does not qualify this adapter or broaden its work
scope. Keep admission controlled through the existing owner and host mechanisms
until the full adapter lifecycle is qualified. No new dispatcher, queue,
credential authority or automatic provider fallback is introduced here.
