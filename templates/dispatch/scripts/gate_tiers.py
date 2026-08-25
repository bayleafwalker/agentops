"""Stratify a packet's registered gates without shrinking what must pass.

A packet may declare ``gate_tiers`` to reorder its granted gates into
``fast``, ``focused``, and ``full`` tiers. Stratification is strictly about
order: a plan may stop early, but a candidate may only be minted once every
granted gate has run green. A packet that declares no tiers is not an error --
every granted id lands in ``full``, which is exactly what every packet frozen
before this row already meant.

The seam is deliberately shaped so the cheap answer is wrong: a plan that runs
the fast tier and stops is a legal plan, and a candidate minted from it is not.
"""

from __future__ import annotations

from typing import Any, Iterable

TIER_ORDER = ("fast", "focused", "full")


def stratify(packet: dict[str, Any]) -> dict[str, list[str]]:
    """Validate the packet's ``gate_tiers`` against its grant.

    Returns every tier key, empty lists included, with ids in the order the
    packet declared them. A packet that declares no ``gate_tiers`` is not an
    error: every granted id lands in ``full``.

    Raises ValueError when the declaration and the grant disagree: an unknown
    tier name, an id not granted by ``allowed_command_ids``, an id in more than
    one tier, a granted id in no tier, or an empty ``full`` tier.
    """
    granted = list(packet.get("allowed_command_ids", []))
    declared = packet.get("gate_tiers")

    if declared is None:
        return {"fast": [], "focused": [], "full": granted}

    if not isinstance(declared, dict):
        raise ValueError("gate_tiers must be a mapping of tier name to command ids")

    unknown = [tier for tier in declared if tier not in TIER_ORDER]
    if unknown:
        raise ValueError(f"unknown gate tier(s): {', '.join(sorted(unknown))}")

    granted_set = set(granted)
    seen: set[str] = set()
    tiers: dict[str, list[str]] = {tier: [] for tier in TIER_ORDER}
    for tier in TIER_ORDER:
        for command_id in declared.get(tier, []):
            if command_id not in granted_set:
                raise ValueError(
                    f"gate tier {tier!r} names {command_id!r}, which "
                    "allowed_command_ids does not grant"
                )
            if command_id in seen:
                raise ValueError(
                    f"gate {command_id!r} appears more than once across the tiers"
                )
            seen.add(command_id)
            tiers[tier].append(command_id)

    missing = [command_id for command_id in granted if command_id not in seen]
    if missing:
        raise ValueError(
            f"granted gate(s) in no tier: {', '.join(sorted(missing))}"
        )

    if not tiers["full"]:
        raise ValueError(
            "the 'full' tier must not be empty: there is always a final "
            "required repository gate"
        )

    return tiers


def plan(packet: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """The run order: tiers in TIER_ORDER, empty tiers omitted, full last."""
    tiers = stratify(packet)
    return [(tier, tiers[tier]) for tier in TIER_ORDER if tiers[tier]]


def unmet_for_candidate(
    packet: dict[str, Any], results: Iterable[dict[str, Any]]
) -> list[str]:
    """The granted ids that have not yet run green, in run order.

    ``results`` is any iterable of {"command_id", "exit_code"} and is drained
    once. A result for an id the packet was not granted is ignored, a red
    result does not count as having run, and a duplicate green result does not
    satisfy a second gate.
    """
    green: set[str] = set()
    for result in results:
        if result.get("exit_code") == 0:
            green.add(result["command_id"])
    tiers = stratify(packet)
    return [
        command_id
        for tier in TIER_ORDER
        for command_id in tiers[tier]
        if command_id not in green
    ]


def candidate_ready(
    packet: dict[str, Any], results: Iterable[dict[str, Any]]
) -> bool:
    """True exactly when every granted gate has run green, whatever the tiers."""
    return not unmet_for_candidate(packet, results)