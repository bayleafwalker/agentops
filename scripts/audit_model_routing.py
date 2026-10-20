#!/usr/bin/env python3
"""Audit model policy against observed native catalogues; never select or run models."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def observed_models(value: object) -> set[str]:
    if isinstance(value, dict) and isinstance(value.get("models"), list):
        rows = value["models"]
        if not rows or any(not isinstance(row, dict) or not isinstance(row.get("slug"), str) for row in rows):
            raise ValueError("catalogue has no usable model records")
        return {row["slug"] for row in rows if row.get("visibility") != "hide"}
    if isinstance(value, list) and value:
        models = set()
        for row in value:
            if not isinstance(row, dict) or not isinstance(row.get("success"), bool):
                raise ValueError("probe catalogue has malformed outcomes")
            if not row["success"]:
                raise ValueError("native model probe failed; availability is inconclusive")
            if row["success"]:
                observed = row.get("observed_models")
                if not isinstance(observed, list) or not observed or any(not isinstance(x, str) for x in observed):
                    raise ValueError("successful probe lacks observed model identity")
                models.update(observed)
        return models
    raise ValueError("unsupported or empty catalogue; could not check availability")


def audit(policy: dict, catalogues: dict[str, set[str]]) -> list[dict]:
    rows = []
    for alias, providers in sorted(policy["aliases"].items()):
        for provider, route in sorted(providers.items()):
            if provider not in catalogues:
                continue
            available = catalogues[provider]
            primary = route.get("model")
            fallback = route.get("fallback")
            issues = []
            if route.get("verified") is not True:
                issues.append("primary-unverified")
            if primary not in available:
                issues.append("primary-not-observed")
            if fallback and fallback not in available:
                issues.append("same-provider-fallback-not-observed")
            rows.append({"alias": alias, "provider": provider, "primary": primary,
                         "fallback": fallback, "issues": issues})
    missing = set(catalogues) - {row["provider"] for row in rows}
    if missing:
        raise ValueError("catalogue provider absent from policy: " + ", ".join(sorted(missing)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=ROOT / "model-routing.json")
    parser.add_argument("--catalogue", action="append", required=True, metavar="PROVIDER=FILE")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    catalogues = {}
    evidence = {}
    try:
        for specification in args.catalogue:
            provider, name = specification.split("=", 1)
            if provider in catalogues:
                raise ValueError("duplicate provider catalogue: " + provider)
            raw = Path(name).read_bytes()
            catalogues[provider] = observed_models(json.loads(raw))
            evidence[provider] = {"sha256": hashlib.sha256(raw).hexdigest(),
                                  "observed_models": sorted(catalogues[provider])}
        policy_bytes = args.policy.read_bytes()
        rows = audit(json.loads(policy_bytes), catalogues)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"could not check model routing: {error}\n")
    report = {"schema": "native-model-routing-audit/v1",
              "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
              "catalogues": evidence, "routes": rows,
              "passed": all(not row["issues"] for row in rows)}
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    for row in rows:
        print(f"{row['provider']}/{row['alias']}: " + (", ".join(row["issues"]) or "observed"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
