#!/usr/bin/env python3
"""Pre-fill the parts of a release-unit packet that are identical for every sub-release.

The pathway splits every release into sub-releases -- v5.0 implementation, v5.1
the big drop, v5.2 vuoro-shared, v5.3 client update, ... v5.9 the refactor pass
-- and each one is one orchestrator hand-off unit with its own gate set. The
dumb orchestrator must not have to reconstruct that gate set per sub-release:
this module pre-fills the parts that are identical for every sub-release, so
the only thing an orchestrator supplies is which release it is, which repo,
which sprint item, what may be written and why.

The module writes no file, parses no arguments and touches no git. Each call
returns a fresh object graph: mutating one result, or mutating an argument
after the call, must not reach any other packet.
"""
from __future__ import annotations

import copy
from typing import Any

#: The pathway §5 gate set, in §5's order. A release unit crosses a release
#: boundary by definition, so the stop condition must fire on it rather than
#: the driver running it unattended.
GATE_SET: list[dict[str, Any]] = [
    {"order": 1, "gate": "prepare_cold_worktree_at_pinned_commit"},
    {"order": 2, "gate": "repo_suite_with_falsifier_coverage"},
    {"order": 3, "gate": "round_checks_and_untracked_file_guard"},
    {"order": 4, "gate": "release_contract_digest_validation"},
    {"order": 5, "gate": "hybrid_dispatch_gate_then_receipt"},
    {"order": 6, "gate": "pr_opened_with_receipt_then_stop"},
]

#: The four encoded L-2 stop conditions, as stable identifiers.
STOP_CONDITIONS: list[str] = [
    "gate_red_twice_on_same_packet",
    "release_boundary_crossing",
    "command_outside_allowed_command_ids",
    "path_outside_writable_patch_paths",
]

#: The packet is a template: the orchestrator pins the actual commit at freeze
#: time. This placeholder satisfies the schema's 40-hex pattern without the
#: function touching git.
PENDING_STARTING_COMMIT: str = "0" * 40

#: The standard protected paths for a release-unit packet.
PROTECTED_PATHS: list[str] = [
    "templates/dispatch/hybrid/**",
    "templates/dispatch/scripts/hybrid_dispatch.py",
    "templates/dispatch/scripts/dispatch_release.py",
    "templates/dispatch/scripts/release_scorecard.py",
    "templates/dispatch/manifest.schema.json",
    "templates/dispatch/model-routing.json",
    "agentops.dispatch.json",
    "templates/dispatch/tests/**",
    "templates/dispatch/hooks/**",
    "docs/**",
    ".claude/**",
    "apps/web/**",
]

#: The standard limits for a release-unit packet.
LIMITS: dict[str, Any] = {
    "timeout_seconds": 1800,
    "max_cost_usd": 3.0,
    "soft_token_ceiling": 1200000,
    "hard_token_ceiling": 2000000,
}

#: The standard worktree for a release-unit packet. The orchestrator overrides
#: the branch per release before freeze.
WORKTREE: dict[str, Any] = {
    "root": "/tmp/agentops-hybrid/worktrees",
    "branch": "hybrid/release-unit",
    "cleanup": "retain-for-review",
}

#: The standard oracle for a release-unit packet. The release unit's own oracle
#: decides correctness; the coordinator authors it before freeze.
ORACLE: dict[str, Any] = {
    "ownership": "externally_defined",
    "worker_may_modify": False,
    "description": "The release unit's own oracle decides correctness; the coordinator authors it before freeze.",
    "starts_red": [],
    "reference_patch": "docs/evidence/packets/release-unit.reference.patch",
}

#: The standard readable context for a release-unit packet.
READABLE_CONTEXT_PATHS: list[str] = [
    "templates/dispatch/hybrid/task-packet.schema.json",
]

#: The standard required outcomes for a release-unit packet.
REQUIRED_OUTCOMES: list[str] = [
    "the release unit's required outcomes, authored by the coordinator before freeze",
]

#: The standard acceptance properties for a release-unit packet.
ACCEPTANCE_PROPERTIES: list[dict[str, str]] = [
    {
        "id": "REQ-001",
        "requirement": "the release unit's acceptance properties, authored by the coordinator before freeze",
        "command_id": "agentops.dispatch.tests.release_unit_packet",
        "fails_when": "the release unit's own oracle is red",
    },
]

#: The standard non-goals for a release-unit packet.
NON_GOALS: list[str] = [
    "the release unit's non-goals, authored by the coordinator before freeze",
]

#: The standard allowed commands for a release-unit packet.
ALLOWED_COMMAND_IDS: list[str] = [
    "agentops.dispatch.tests.release_unit_packet",
]

#: The standard context-churn limits for a release-unit packet.
CONTEXT_CHURN: dict[str, Any] = {
    "max_repeated_reads_per_path": 4,
    "max_reasoning_steps_without_mutation": 20,
    "max_identical_context_tokens": 250000,
    "handoff_when_candidate_ready": True,
}

#: The standard review block for a release-unit packet.
REVIEW: dict[str, Any] = {
    "coordinator_context": "independent",
    "challenger_enabled": False,
    "references": [
        "docs/plans/agentops/2026-08-23-handoff-loop-and-telemetry.md",
        "docs/dispatch/handover-2026-08-23-metanarrative-v5.md",
    ],
}


def release_unit_packet(
    release: str,
    repo_id: str,
    sprint_item: dict[str, Any],
    writable_patch_paths: list[str],
    purpose: str,
) -> dict[str, Any]:
    """Return a fresh release-unit packet for ``release``.

    The pre-filled parts -- the §5 gate set, the four L-2 stop conditions,
    ``release_boundary``, the schema version, route, limits, worktree and the
    rest -- are identical for every sub-release; only ``task_id`` derives from
    ``release``. The caller's ``repo_id``, ``sprint_item``,
    ``writable_patch_paths`` and ``purpose`` appear unchanged. Every call
    returns a fresh object graph: mutating one result, or mutating an argument
    after the call, must not reach any other packet.
    """
    return {
        "schema_version": "agentops-task/v2",
        "task_id": f"{release}-release-unit",
        "repo_id": repo_id,
        "sprint_item": copy.deepcopy(sprint_item),
        "route": "mechanical_bulk",
        "task_class": "mechanical_implementation",
        "risk": "low",
        "oracle": copy.deepcopy(ORACLE),
        "attempt": 1,
        "starting_commit": PENDING_STARTING_COMMIT,
        "purpose": purpose,
        "readable_context_paths": copy.deepcopy(READABLE_CONTEXT_PATHS),
        "writable_patch_paths": copy.deepcopy(writable_patch_paths),
        "protected_paths": copy.deepcopy(PROTECTED_PATHS),
        "required_outcomes": copy.deepcopy(REQUIRED_OUTCOMES),
        "acceptance_properties": copy.deepcopy(ACCEPTANCE_PROPERTIES),
        "non_goals": copy.deepcopy(NON_GOALS),
        "allowed_command_ids": copy.deepcopy(ALLOWED_COMMAND_IDS),
        "limits": copy.deepcopy(LIMITS),
        "context_churn": copy.deepcopy(CONTEXT_CHURN),
        "network_policy": "disabled",
        "worktree": copy.deepcopy(WORKTREE),
        "review": copy.deepcopy(REVIEW),
        "release_boundary": True,
        "gate_set": copy.deepcopy(GATE_SET),
        "stop_conditions": copy.deepcopy(STOP_CONDITIONS),
    }