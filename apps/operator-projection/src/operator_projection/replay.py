"""Replay of the registry's git-readable vocabularies over appservice history (§6.3)."""

from __future__ import annotations

import json
import re
from datetime import datetime

import yaml

from .evaluators import DIGEST, Move, Row, broker_rows, classify, durability_rows, lock_rows, record_classes, service_rows
from .sources import GitSource, ImageTags

UNDETERMINED = object()
APPSERVICE, BRANCH = "appservice", "main"
RELEASE_LABEL = re.compile(r"release:\s*(vuoro-service-v[0-9.]+)")
VOCABULARIES = [
    "authority.service_release",
    "composition.release_lock",
    "audit.record_class",
    "credbroker.capability_rule",
    "credbroker.repository",
    "credbroker.binding",
    "durability.store",
]


def read_policy(config: str | None):
    """The deployed policy is the ConfigMap's production.json, and nothing else."""
    if config is None:
        return None
    try:
        return json.loads(yaml.safe_load(config)["data"]["production.json"])
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return UNDETERMINED


def recall(result: dict) -> dict:
    """Nightly recall invariant (§6.4 board falsifier 2): every boundary maps to a move or quiet, or is a miss."""
    return {"boundary_commits": len(result["boundaries"]), "mapped": len(result["boundaries"]) - len(result["misses"]),
            "misses": result["misses"]}


class Replay:
    def __init__(self, registry: dict, git: GitSource, tags: ImageTags):
        self.sources = registry["sources"]
        self.pins, self.validation = registry["external"]["pins"], registry["external"]["record_classes"]
        self.git, self.tags = git, tags
        self.declared_classes = record_classes(git.show(self.validation["repo"], BRANCH, self.validation["path"]) or "")
        self.undetermined: list[tuple[str, str]] = []
        # (capability, provider-wide audience value) -> forgejo repositories when that value first appeared
        self._audience_scopes: dict[tuple[str, str], frozenset[str]] = {}

    def read(self, commit: str, key: str) -> str | None:
        return self.git.show(APPSERVICE, commit, self.sources[key])

    def snapshot(self, commit: str, previous: dict) -> dict:
        deployment, policy = self.read(commit, "shared_deployment"), read_policy(self.read(commit, "broker_config"))
        locks = self.locks(deployment)
        state = {
            "authority.service_release": service_rows(deployment, self.read(commit, "shared_ks")),
            "composition.release_lock": locks,
            "audit.record_class": self._record_classes(locks, deployment),
        }
        if policy is UNDETERMINED:
            state |= {v: UNDETERMINED for v in VOCABULARIES if v.startswith("credbroker.")}
            state["durability.store"] = UNDETERMINED
        else:
            state |= broker_rows(policy, self._wide_scope(policy))
            state["durability.store"] = durability_rows(
                self.read(commit, "cockpit_pvc") is not None, policy, self.read(commit, "broker_pvc") is not None
            )
        for vocabulary in VOCABULARIES:
            if state[vocabulary] is UNDETERMINED:
                self.undetermined.append((commit, vocabulary))
                state[vocabulary] = previous.get(vocabulary, {})
        return state

    def locks(self, deployment: str | None):
        if deployment is None:
            return {}
        digest = DIGEST.search(deployment)
        source = digest and self.tags.source_commit(digest.group(1))
        pins = source and self.git.show(self.pins["repo"], source, self.pins["path"])
        return lock_rows(json.loads(pins)) if pins else UNDETERMINED

    def _record_classes(self, locks, deployment: str | None):
        if locks is UNDETERMINED:
            return UNDETERMINED
        reachable: set[str] = set()
        audit = locks.get("audit-adapter")
        if deployment is not None and audit:
            validation = self.git.show(self.validation["repo"], audit.value, self.validation["path"])
            if validation is None:
                return UNDETERMINED
            reachable = record_classes(validation)
        return {c: Row(c in reachable) for c in sorted(self.declared_classes)}

    def _wide_scope(self, policy: dict | None) -> dict[str, frozenset[str]] | None:
        audiences = ((policy or {}).get("providers", {}).get("forgejo") or {}).get("audiences")
        if not audiences:
            return None
        forgejo = frozenset(r["repository_id"] for r in policy.get("repositories", []) if r.get("provider") == "forgejo")
        return {
            capability: self._audience_scopes.setdefault((capability, value), forgejo)
            for capability, value in audiences.items()
            if isinstance(value, str)
        }

    def boundaries(self, start: datetime, end: datetime) -> list[tuple[str, datetime]]:
        commits = self.git.log(APPSERVICE, BRANCH, list(self.sources.values()), start, end)
        return [(sha, when) for sha, when in reversed(commits) if start <= when < end]

    def run(self, start: datetime, end: datetime) -> dict:
        base = self.git.resolve(APPSERVICE, BRANCH, before=start) or ""
        state = self.snapshot(base, {}) if base else {v: {} for v in VOCABULARIES}
        moves: list[Move] = []
        quiet: list[str] = []
        misses: list[str] = []
        diverged: list[dict] = []
        boundaries = self.boundaries(start, end)
        for sha, when in boundaries:
            pending = len(self.undetermined)
            after = self.snapshot(sha, state)
            found = [
                Move(v, member, cls, sha, when.isoformat(), self._detail(v, after.get(v, {}).get(member)))
                for v in VOCABULARIES
                for member, cls in classify(v, state.get(v, {}), after.get(v, {}))
            ]
            moves += found
            # An undetermined evaluation can hide a move, so its boundary is a recall miss, never quiet.
            if len(self.undetermined) > pending:
                misses.append(sha)
            elif not found:
                quiet.append(sha)
            deployment = self.read(sha, "shared_deployment") or ""
            label, digest = RELEASE_LABEL.search(deployment), DIGEST.search(deployment)
            served = self.tags.release(digest.group(1) if digest else None)
            if label and served and label.group(1) != served:
                diverged.append({"boundary": sha[:8], "label": label.group(1), "digest_release": served})
            state = after
        return {"base": base, "moves": moves, "quiet": quiet, "misses": misses, "boundaries": [sha for sha, _ in boundaries],
                "diverged": diverged, "final": state}

    def _detail(self, vocabulary: str, row: Row | None) -> str | None:
        if row is None:
            return None
        if vocabulary == "authority.service_release":
            return self.tags.release(row.value)
        return row.detail or (row.value if vocabulary == "durability.store" else None)
