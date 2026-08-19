from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from .authority import InMemoryRevisionedTaskStore, MissingPrecondition
from .cursor import InMemoryCursorStore
from .model import Binding, ProjectionRequest, ProviderSnapshot, RevisionConflict
from .projection import Projector


class BindingProvider:
    provider_id = "binding"
    priority = 100
    budget_bytes = 900

    def validate(self, binding: Binding) -> str:
        return f"binding:{binding.dispatch_id}:1"

    def render(self, binding: Binding, expected_revision: str) -> ProviderSnapshot:
        return ProviderSnapshot(
            provider_id=self.provider_id,
            revision=expected_revision,
            source_uri=f"vuoro://dispatch/{binding.dispatch_id}",
            data={
                "dispatch_id": binding.dispatch_id,
                "repo_id": binding.repo_id,
                "task_id": binding.task_id,
            },
        )


class TaskProvider:
    provider_id = "task"
    priority = 90
    budget_bytes = 4000

    def __init__(self, store: InMemoryRevisionedTaskStore) -> None:
        self.store = store

    def validate(self, binding: Binding) -> str:
        return self.store.revision()

    def render(self, binding: Binding, expected_revision: str) -> ProviderSnapshot:
        revision, data = self.store.snapshot()
        if revision != expected_revision:
            raise RevisionConflict(f"expected {expected_revision}, current {revision}")
        return ProviderSnapshot(
            provider_id=self.provider_id,
            revision=revision,
            source_uri=f"sprintctl://task/{binding.task_id or 'TASK-42'}",
            data=data,
        )


class WorkspaceProvider:
    provider_id = "workspace"
    priority = 70
    budget_bytes = 1400

    def validate(self, binding: Binding) -> str:
        return f"workspace:{binding.repo_id or 'unknown'}:1"

    def render(self, binding: Binding, expected_revision: str) -> ProviderSnapshot:
        return ProviderSnapshot(
            provider_id=self.provider_id,
            revision=expected_revision,
            source_uri=f"vuoro://repo/{binding.repo_id or 'unknown'}/workspace",
            data={"repo_id": binding.repo_id, "canonical_branch": "main"},
        )


class HostProvider:
    provider_id = "host"
    priority = 60
    budget_bytes = 900

    def validate(self, binding: Binding) -> str:
        return "host:demo:1"

    def render(self, binding: Binding, expected_revision: str) -> ProviderSnapshot:
        return ProviderSnapshot(
            provider_id=self.provider_id,
            revision=expected_revision,
            source_uri="vuoro://host/current",
            data={"host": "demo", "capabilities": ["git", "python"]},
        )


class FakeContextService:
    def __init__(self) -> None:
        self.store = InMemoryRevisionedTaskStore()
        self.cursors = InMemoryCursorStore()
        self.projector = Projector(
            [
                BindingProvider(),
                TaskProvider(self.store),
                WorkspaceProvider(),
                HostProvider(),
            ],
            self.cursors,
        )

    @staticmethod
    def _binding(payload: Mapping[str, Any]) -> Binding:
        dispatch_id = str(payload["dispatch_id"])
        repo_id = str(payload.get("repo_id") or "demo-repo")
        return Binding(
            dispatch_id=dispatch_id,
            repo_id=repo_id,
            task_id="TASK-42",
            host_id="demo",
        )

    def project(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = ProjectionRequest.from_mapping(payload)
        return self.projector.project(request, self._binding(payload)).as_dict()

    def validate_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        current = self.store.revision()
        expected = payload.get("expected_revision")
        allowed = expected is not None and str(expected) == current
        context = None
        reason = None
        if not allowed:
            reason = (
                f"Task revision changed: expected {expected}, current {current}"
                if expected is not None
                else f"Task mutation requires if_revision; current {current}"
            )
            request = {
                **payload,
                "event": "PreToolUse",
                "mode": "full",
                "cwd": str(payload.get("cwd", ".")),
                "provider_ids": ["task"],
            }
            context = self.project(request).get("context")
        return {
            "schema_version": "1",
            "allowed": allowed,
            "reason": reason,
            "current_revision": current,
            "context": context,
        }

    def observe_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = {
            **payload,
            "event": "PostToolUse",
            "mode": "full",
            "cwd": str(payload.get("cwd", ".")),
            "provider_ids": [str(payload.get("provider_id", "task"))],
        }
        return self.project(request)

    def invalidate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.cursors.invalidate(
            dispatch_id=str(payload["dispatch_id"]),
            harness=str(payload["harness"]),
            session_id=str(payload["session_id"]),
            agent_id=str(payload.get("agent_id") or "root"),
            provider_ids=set(str(p) for p in payload.get("provider_ids", ())) or None,
        )
        return {"schema_version": "1", "invalidated": True}

    def mutate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        result = self.store.mutate(
            expected_revision=(
                str(payload["if_revision"])
                if payload.get("if_revision") is not None
                else None
            ),
            patch=(payload.get("patch") if isinstance(payload.get("patch"), Mapping) else {}),
            actor=str(payload.get("actor") or ""),
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        return {"schema_version": "1", **result.as_dict()}


class Handler(BaseHTTPRequestHandler):
    service = FakeContextService()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> Mapping[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("request body must be an object")
        return value

    def _write(self, status: int, value: Mapping[str, Any]) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            payload = self._read_json()
            if self.path == "/v1/agent-context/project":
                result = self.service.project(payload)
            elif self.path == "/v1/agent-context/mutations/validate":
                result = self.service.validate_mutation(payload)
            elif self.path == "/v1/agent-context/mutations/observe":
                result = self.service.observe_mutation(payload)
            elif self.path == "/v1/agent-context/invalidate":
                result = self.service.invalidate(payload)
            elif self.path == "/demo/task/mutate":
                result = self.service.mutate(payload)
            else:
                self._write(404, {"error": "not found"})
                return
            self._write(200, result)
        except MissingPrecondition as exc:
            self._write(428, {"error": "precondition_required", "message": str(exc)})
        except RevisionConflict as exc:
            self._write(
                409,
                {
                    "error": "revision_conflict",
                    "message": str(exc),
                    "current_revision": self.service.store.revision(),
                },
            )
        except Exception as exc:
            self._write(400, {"error": str(exc)})


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fake volatile-context service")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    server = ThreadingHTTPServer((args.listen, args.port), Handler)
    print(f"fake volatile-context service listening on http://{args.listen}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
