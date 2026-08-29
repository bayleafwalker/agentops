#!/usr/bin/env python3
"""One entry point for the metanarrative model: claims, observations, alignment.

The point of this file is that the model is *cheap to use*. A record format nobody
writes is worse than no record format, so every operation here is one command, and
each one publishes to the stores that already exist rather than to a new one:

* records live as JSON under ``<artifacts-root>/<scope>/model/``;
* every mutation emits an auditctl event, so the evidence spine sees it;
* ``publish`` hands a claim to kctl as a knowledge entry -- kctl is the claims
  store, this is only the shape;
* ``status`` reports what acceptance-lab and the telemetry projection say, so the
  regular workflow surfaces them instead of requiring a separate ritual.

Nothing here has an approval step. `actor_type` is provenance.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_model_records as model  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _artifacts_root() -> Path:
    root = os.environ.get("AUDITCTL_ARTIFACTS_ROOT")
    if not root:
        default = Path(__file__).resolve().parents[1] / "artifacts-root.default"
        root = default.read_text().splitlines()[0] if default.is_file() else "."
    return Path(root)


def _store(scope: str) -> Path:
    path = _artifacts_root() / scope / "model"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load(scope: str, kind: str | None = None) -> list[dict[str, Any]]:
    records = []
    for file in sorted(_store(scope).glob("*.json")):
        try:
            record = json.loads(file.read_text())
        except json.JSONDecodeError:
            continue
        if kind is None or record.get("schema_version") == kind:
            records.append(record)
    return records


def _write(scope: str, record: dict[str, Any], name: str) -> Path:
    path = _store(scope) / f"{name}.json"
    model.validate_record(record, path)
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path


def _auditctl(event_type: str, summary: str, metadata: dict[str, Any]) -> bool:
    """Emit to auditctl. Never fatal: a missing publisher must not lose the record."""

    binary = shutil.which("auditctl") or str(Path.home() / ".local/bin/auditctl")
    if not Path(binary).exists():
        return False
    env = dict(os.environ)
    env.setdefault("AUDITCTL_ARTIFACTS_ROOT", str(_artifacts_root()))
    result = subprocess.run(
        [binary, "add", "--type", event_type, "--source", "metanarrative",
         "--actor", env.get("USER", "unknown"), "--summary", summary,
         "--metadata", json.dumps(metadata)],
        capture_output=True, env=env,
    )
    return result.returncode == 0


def cmd_claim(args: argparse.Namespace) -> int:
    claim: dict[str, Any] = {
        "schema_version": "claim/v1",
        "id": args.id,
        "kind": args.kind,
        "scope": args.scope,
        "statement": args.statement,
        "state": args.state,
    }
    if args.state != "draft":
        claim["established_by"] = {
            "actor": args.actor,
            "actor_type": args.actor_type,
            "at": _now(),
            "authority_basis": args.authority_basis,
        }
        claim["validity"] = {"effective_from": _now()}
    if args.supersedes:
        claim["supersedes"] = args.supersedes
    if args.basis_for:
        claim["basis_for"] = args.basis_for
    if args.kind == "tenet":
        claim["enforcement_mode"] = args.enforcement_mode

    path = _write(args.scope, claim, f"claim-{args.id}")

    # Superseding is an event, not an edit: the prior claim closes its interval and
    # stays on disk. That is what makes current practice a projection.
    if args.supersedes:
        for record in _load(args.scope, "claim/v1"):
            if record["id"] == args.supersedes and record.get("state") == "current":
                record["state"] = "superseded"
                record.setdefault("validity", {})["effective_to"] = _now()
                _write(args.scope, record, f"claim-{record['id']}")

    published = _auditctl("model.claim", f"{args.kind} {args.id} is {args.state}",
                          {"claim": args.id, "kind": args.kind, "scope": args.scope,
                           "state": args.state, "supersedes": args.supersedes})
    print(f"wrote {path}" + ("" if published else "  (auditctl unavailable)"))
    return 0


def cmd_observe(args: argparse.Namespace) -> int:
    observation = {
        "schema_version": "observation/v1",
        "id": args.id,
        "subject": args.subject,
        "stance": args.stance,
        "observed_at": _now(),
        "evidence_ref": args.evidence_ref,
    }
    if args.note:
        observation["note"] = args.note
    path = _write(args.scope, observation, f"observation-{args.id}")
    _auditctl("model.observation", f"{args.stance} {args.subject}",
              {"observation": args.id, "subject": args.subject, "stance": args.stance})
    print(f"wrote {path}")

    # A contradiction against a current claim is the reconciliation signal. It does
    # not change the claim -- it makes the discrepancy visible.
    claims = {c["id"]: c for c in _load(args.scope, "claim/v1")}
    subject = claims.get(args.subject)
    if args.stance == "contradicts" and subject and subject.get("state") == "current":
        print(f"note: {args.subject} remains current and is now contradicted -- "
              f"reconciliation work, not a state change")
    return 0


def cmd_align(args: argparse.Namespace) -> int:
    """Classify work against a tenet, opening a session only on divergence."""

    claims = {c["id"]: c for c in _load(args.scope, "claim/v1")}
    tenet = claims.get(args.tenet)
    if tenet is None:
        print(f"no such claim: {args.tenet}", file=sys.stderr)
        return 1
    if tenet.get("enforcement_mode") == "block":
        print(f"{args.tenet} is an invariant (enforcement_mode: block). "
              f"A violation stops the work; it does not open a session.")
        return 1 if args.alignment == "divergent" else 0
    if args.alignment != "divergent":
        _auditctl("model.alignment", f"{args.work_ref} is {args.alignment} to {args.tenet}",
                  {"tenet": args.tenet, "work_ref": args.work_ref, "alignment": args.alignment})
        print(f"{args.work_ref}: {args.alignment} -- recorded, no session needed")
        return 0

    session = {
        "schema_version": "realignment-session/v1",
        "id": args.session_id,
        "tenet": args.tenet,
        "work_ref": args.work_ref,
        "alignment": "divergent",
        "state": "open",
        "resolution_options": ["realign-work", "supersede-tenet"],
    }
    path = _write(args.scope, session, f"session-{args.session_id}")
    _auditctl("model.realignment", f"divergence: {args.work_ref} vs {args.tenet}",
              {"session": args.session_id, "tenet": args.tenet, "work_ref": args.work_ref})
    print(f"opened {path}")
    print("resolve with: realign-work | supersede-tenet")
    print(f"blast radius: {', '.join(tenet.get('basis_for', [])) or '(no declared dependents)'}")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    sessions = {s["id"]: s for s in _load(args.scope, "realignment-session/v1")}
    session = sessions.get(args.session_id)
    if session is None:
        print(f"no such session: {args.session_id}", file=sys.stderr)
        return 1
    if args.attention:
        # Escalation is routing. The session stays open; nothing is closed by asking.
        session["attention_request"] = {"reason": args.attention, "raised_at": _now()}
        if args.detail:
            session["attention_request"]["detail"] = args.detail
        session.pop("resolution", None)
        session["state"] = "open"
    else:
        session["state"] = "resolved"
        session["resolution"] = args.resolution
        session.pop("attention_request", None)
    path = _write(args.scope, session, f"session-{args.session_id}")
    _auditctl("model.realignment", f"session {args.session_id} {session['state']}",
              {"session": args.session_id, "state": session["state"],
               "resolution": session.get("resolution"),
               "attention": (session.get("attention_request") or {}).get("reason")})
    print(f"wrote {path}: {session['state']}")
    if session["state"] == "open":
        print("attention requested; the session stays open until it is resolved")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Hand a current claim to kctl. kctl is the claims store; this is the shape."""

    claims = {c["id"]: c for c in _load(args.scope, "claim/v1")}
    claim = claims.get(args.id)
    if claim is None:
        print(f"no such claim: {args.id}", file=sys.stderr)
        return 1
    binary = shutil.which("kctl")
    if binary is None:
        print("kctl is not on PATH; claim not published", file=sys.stderr)
        return 1
    # kctl gained `tenet` and `direction` as categories (kctl migration 8), so a
    # published claim keeps its kind. `practice` has no category of its own and
    # publishes as `decision`: a practice is a decision the workspace is living by.
    category = claim["kind"] if claim["kind"] in {"tenet", "direction", "decision"} else "decision"
    body = f"{claim['statement']}\n\nkind: {claim['kind']}\nscope: {claim['scope']}"
    result = subprocess.run(
        [binary, "publish", "--title", claim["id"], "--body", body, "--category", category],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "kctl publish failed", file=sys.stderr)
        return 1
    print(f"published {args.id} to kctl")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """The one command a regular session runs. Cheap, and safe when nothing exists."""

    claims = _load(args.scope, "claim/v1")
    observations = _load(args.scope, "observation/v1")
    sessions = _load(args.scope, "realignment-session/v1")
    current = model.current_claims(claims)

    contradicted = [
        c for c in current
        if model.observational_status(c["id"], observations) == "contradicted"
    ]
    open_sessions = [s for s in sessions if s.get("state") == "open"]
    attention = [s for s in open_sessions if "attention_request" in s]

    print(f"claims: {len(current)} current of {len(claims)}")
    for claim in current:
        status = model.observational_status(claim["id"], observations)
        marker = "  [contradicted]" if status == "contradicted" else ""
        basis = f"  basis_for: {', '.join(claim['basis_for'])}" if claim.get("basis_for") else ""
        print(f"  {claim['kind']:9} {claim['id']}{marker}{basis}")
    if contradicted:
        print(f"\nreconciliation work: {len(contradicted)} current claim(s) contradicted "
              f"by observation")
    if open_sessions:
        print(f"\nopen realignment sessions: {len(open_sessions)}")
        for session in open_sessions:
            reason = (session.get("attention_request") or {}).get("reason")
            suffix = f"  attention: {reason}" if reason else ""
            print(f"  {session['id']}  {session['work_ref']} vs {session['tenet']}{suffix}")
    if attention:
        print(f"\n{len(attention)} session(s) need authority this workspace does not have")
    if not claims and not sessions:
        print("(no model records yet)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="metanarrative", description=__doc__.splitlines()[0])
    parser.add_argument("--scope", default="agentops", help="record store scope (default: agentops)")
    sub = parser.add_subparsers(dest="command", required=True)

    claim = sub.add_parser("claim", help="state a tenet, direction, practice or decision")
    claim.add_argument("id")
    claim.add_argument("--kind", required=True, choices=sorted(model.CLAIM_KINDS))
    claim.add_argument("--statement", required=True)
    claim.add_argument("--state", default="current", choices=sorted(model.STATES))
    claim.add_argument("--actor", default=os.environ.get("USER", "unknown"))
    claim.add_argument("--actor-type", default="agent", choices=sorted(model.ACTOR_TYPES),
                       help="provenance only; no value of this gates anything")
    claim.add_argument("--authority-basis", default="delegated",
                       choices=sorted(model.AUTHORITY_BASES))
    claim.add_argument("--enforcement-mode", default="review",
                       choices=sorted(model.ENFORCEMENT_MODES),
                       help="tenet: review opens a session, block stops the work")
    claim.add_argument("--supersedes")
    claim.add_argument("--basis-for", nargs="*", default=[],
                       help="what this claim is the basis for; presence makes it canonical")
    claim.set_defaults(func=cmd_claim)

    observe = sub.add_parser("observe", help="record evidence bearing on a claim")
    observe.add_argument("id")
    observe.add_argument("--subject", required=True)
    observe.add_argument("--stance", required=True, choices=sorted(model.STANCES))
    observe.add_argument("--evidence-ref", required=True)
    observe.add_argument("--note")
    observe.set_defaults(func=cmd_observe)

    align = sub.add_parser("align", help="classify work against a tenet")
    align.add_argument("work_ref")
    align.add_argument("--tenet", required=True)
    align.add_argument("--alignment", required=True, choices=sorted(model.ALIGNMENTS))
    align.add_argument("--session-id", default=f"rs-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}")
    align.set_defaults(func=cmd_align)

    resolve = sub.add_parser("resolve", help="resolve a session, or request attention")
    resolve.add_argument("session_id")
    resolve.add_argument("--resolution", choices=sorted(model.RESOLUTIONS))
    resolve.add_argument("--attention", choices=sorted(model.ATTENTION_REASONS),
                         help="routing, not a resolution: the session stays open")
    resolve.add_argument("--detail")
    resolve.set_defaults(func=cmd_resolve)

    publish = sub.add_parser("publish", help="hand a claim to kctl")
    publish.add_argument("id")
    publish.set_defaults(func=cmd_publish)

    status = sub.add_parser("status", help="what is current, contradicted, and open")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "resolve" and not args.resolution and not args.attention:
        print("resolve requires --resolution or --attention", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
