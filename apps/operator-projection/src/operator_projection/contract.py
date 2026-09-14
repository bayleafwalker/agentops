"""Two renderers, one contract (§11.6): both must cover every document field, asserted at import."""

from . import render_html, render_text

FIELDS = frozenset(
    {"schema", "derived", "generated_at", "cadence_s", "stale_after_s", "registry", "sources"}
    | {f"panels.provenance.{k}" for k in ("authority", "catalog", "compatibility")}
    | {f"panels.pickup.{k}" for k in ("counts", "rows", "overflow")}
    | {f"panels.hazards.{k}" for k in ("open", "oldest_days", "rows")}
    | {f"panels.moves.{k}" for k in ("window", "counts", "attributed", "exercise_observable", "rows", "overflow", "zero", "recall")}
    | {f"panels.ground_tools.{k}" for k in ("installed", "authority", "adapters", "domains")}
    | {f"panels.may_do.{k}" for k in ("grants", "admitted_policy_revision", "policy")}
    | {f"panels.blind_spots.{k}" for k in ("scope", "coverage_s1", "not_seen")}
)

for _renderer in (render_html, render_text):
    assert _renderer.COVERS == FIELDS, f"{_renderer.__name__} coverage differs: {sorted(_renderer.COVERS ^ FIELDS)}"
