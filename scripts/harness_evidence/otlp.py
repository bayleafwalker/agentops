"""Minimal OTLP/JSON key-value encoding shared by `spans` and `metrics`.

Only the shapes this library actually produces are handled: strings, bools,
ints, floats, flat lists of one of those (`cost_usd_list`), and one level of
nested dict (`durations`, `rate_limit`), which OTLP/JSON represents as a
`kvlistValue`. Nothing here reaches further than that because
`attributes.filter_attributes` never keeps anything deeper.
"""
from __future__ import annotations

from typing import Any


def any_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [any_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"kvlistValue": {"values": kv_list(value)}}
    # Never reached by anything filter_attributes keeps, but fail loudly
    # rather than silently drop a value type nobody accounted for.
    raise TypeError(f"unsupported OTLP attribute value type: {type(value)!r}")


def kv_list(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": key, "value": any_value(value)} for key, value in attributes.items()]
