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
        "kctl extract",
        "kctl publish",
        "kctl render",
    )

    for command in required:
        assert command in text, command


def test_matrix_preserves_p0_gaps_and_evidence_boundary() -> None:
    text = MATRIX.read_text(encoding="utf-8")

    for gap in (
        "usage --context",
        "item list",
        "item ref list",
        "item dep list",
        "claim list-sprint",
        "claim resume",
        "item done-from-claim",
        "tracker `handoff`",
    ):
        assert gap in text, gap

    assert "P0" in text and "inventory" in text
    assert "not a claim that" in text
    assert "unsupported operations already fail cleanly" in text
    assert "2026-07-26-vuoro-blind-agent-parity-next-devbox.md" in text
