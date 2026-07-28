from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs" / "dispatch" / "vuoro-blind-agent-served-parity.md"


def test_matrix_covers_every_blind_agent_guidance_command() -> None:
    """Keep the P0 inventory from silently losing a prescribed command.

    This is intentionally a dependency-free documentation contract. Command
    behavior belongs to the owning Sprintctl/Kctl repositories; this test only
    asserts that canonical Agentops guidance has a current parity decision.
    """
    text = MATRIX.read_text(encoding="utf-8")

    required = (
        "sprintctl doctor --json",
        "sprintctl sprint list --active --json",
        "sprintctl sprint list --include-backlog --json",
        "sprintctl claim list-sprint --sprint-id <sprint-id> --json",
        "sprintctl next-work --sprint-id <sprint-id> --json --explain",
        "sprintctl item show --id <item-id> --json",
        "sprintctl item edit --id <item-id> --description <text>",
        "sprintctl item ref list --id <item-id> --json",
        "sprintctl item dep list --id <item-id> --json",
        "sprintctl claim start --item-id <item-id>",
        "sprintctl sprint show --json",
        "sprintctl item list --sprint-id <id> --json",
        "sprintctl claim list --item-id <item-id> --json",
        "sprintctl claim resume --instance-id <id>",
        "sprintctl claim heartbeat --claim-id",
        "sprintctl agent-protocol --json",
        "sprintctl event add --sprint-id <id> --item-id <item-id>",
        "sprintctl claim handoff --claim-id",
        "sprintctl handoff --sprint-id <id> --output <path>",
        "sprintctl item done-from-claim --id <id>",
        "sprintctl claim release --claim-id",
        "kctl preflight --sprint-id <id>",
        "sprintctl maintain check --sprint-id <id>",
        "kctl extract --sprint-id <id> --basis-git-revision <full-commit>",
        "kctl publish",
        "kctl render",
    )

    for command in required:
        assert command in text, command


def test_matrix_preserves_source_deployment_boundary_and_remaining_gaps() -> None:
    text = MATRIX.read_text(encoding="utf-8")

    for source_ready in (
        "Atomic `work.read.context` landed in `3ac6cac`",
        "`work.read.items` landed in `934ceb6`",
        "`work.read.claims` route landed in Sprintctl `934ceb6`/`c199961`",
        "`work.read.next-work-explain` landed in `8b585a6`",
        "Server-side `work.read.sprint-detail` landed in `4cc02c0`",
        "`89b22b8`",
        "`7b9da6a`",
    ):
        assert source_ready in text, source_ready

    assert "P0" in text and "source/deployment split" in text
    assert "not a claim of deployed parity" in text
    assert "Deployed failure" in text
    assert "project-wide orientation" in text
    assert "kctl preflight" in text
    assert "explicit immutable CLI" in text
    assert "derive it from a mutable checkout" in text
    assert "local SQLite candidates or extraction" in text
    assert "knowledge.candidate.intake" in text
    assert "2026-07-26-vuoro-blind-agent-parity-next-devbox.md" in text
