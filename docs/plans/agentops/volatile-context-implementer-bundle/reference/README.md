# Reference Implementation

This package demonstrates the contracts without assuming private sprintctl/Vuoro schemas.

It is intentionally:

- dependency-free on Python 3.11+;
- small enough to inspect;
- a hook adapter and projector reference, not a proposed new product;
- backed by a fake in-memory authority for tests and demos.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Run the fake service

```bash
python -m volatile_context.fake_service --listen 127.0.0.1 --port 8765
```

In another shell:

```bash
export VUORO_DISPATCH_ID=demo-dispatch
export VUORO_REPO_ID=demo-repo
export VUORO_CONTEXT_ENDPOINT=http://127.0.0.1:8765

printf '%s\n' '{"session_id":"s1","cwd":"/tmp/repo","hook_event_name":"SessionStart","source":"startup"}' \
  | python -m volatile_context.hook_adapter --harness codex
```

The real implementation should keep the adapter shape but move providers, binding resolution, cursors, and CAS into the existing served substrate.
