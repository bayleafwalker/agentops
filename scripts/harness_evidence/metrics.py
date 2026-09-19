"""Build OTLP/JSON rate-limit gauge points from the headroom file format.

`payload` carries the identity attributes a gauge should also correlate by
(`session_id`, `runtime`, `harness`, `environment`, ...) plus one control key,
`windows`, shaped like the utilisation windows `.claude-headroom.json`
(#2372) records:

    {"windows": {"5h": {"used_percent": 42.5, "resets_at": "2026-09-14T18:00:00Z"},
                 "7d": {"used_percent": 10.0, "resets_at": "2026-09-20T00:00:00Z"}}}

Each window becomes one gauge data point carrying a `rate_limit` attribute
(`window`, `used_percent`, `resets_at` -- the same shape and allowlist entry
`spans.py` uses), filtered through the same
`schemas/harness-evidence-attributes.schema.json` allowlist as spans: an
unlisted key on `payload`, or an unlisted key nested under one window's
entry, is dropped and counted rather than emitted.
"""
from __future__ import annotations

from typing import Any

from . import attributes
from .otlp import kv_list

_METRIC_CONTROL_KEYS = frozenset({"windows"})
_METRIC_NAME = "claude_code.rate_limit.used_percent"


def build_rate_limit_gauges(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an OTLP/JSON resourceMetrics batch, one gauge point per window."""
    schema = attributes.load_schema()
    base_candidate = attributes.candidate_from_payload(payload, _METRIC_CONTROL_KEYS)
    base_result = attributes.filter_attributes(base_candidate, schema)

    dropped_keys = list(base_result.dropped_keys)
    data_points = []
    for window, values in (payload.get("windows") or {}).items():
        point_candidate = dict(base_result.attributes)
        # schema_version was only needed to make base_candidate independently
        # schema-legal; it is not itself a per-point attribute.
        point_candidate.pop("schema_version", None)
        point_candidate["rate_limit"] = {"window": window, **(values or {})}
        point_result = attributes.filter_attributes(point_candidate, schema)
        dropped_keys.extend(point_result.dropped_keys)

        used_percent = (values or {}).get("used_percent")
        data_points.append(
            {
                "attributes": kv_list(point_result.attributes),
                "asDouble": float(used_percent) if used_percent is not None else 0.0,
                "timeUnixNano": "0",
            }
        )

    resource_attrs = {
        key: base_result.attributes[key]
        for key in ("runtime", "harness", "environment")
        if key in base_result.attributes
    }

    return {
        "resourceMetrics": [
            {
                "resource": {"attributes": kv_list(resource_attrs)},
                "scopeMetrics": [
                    {
                        "scope": {"name": "agentops.harness_evidence", "version": "1"},
                        "metrics": [
                            {
                                "name": _METRIC_NAME,
                                "unit": "%",
                                "gauge": {"dataPoints": data_points},
                            }
                        ],
                    }
                ],
            }
        ],
        "dropped_attribute_count": len(dropped_keys),
        "dropped_attribute_keys": dropped_keys,
    }
