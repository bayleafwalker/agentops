#!/usr/bin/env python3
"""Read-only preflight for a preregistered outcome-measurement companion.

The companion remains authoring evidence beside the owners' ExperimentRecords;
this script does not import, accept, settle or write measurement data. Missing
cases and values stay unknown and prevent the affected comparison from passing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ARMS = ("baseline", "candidate")
COHORTS = {"software", "household", "creative"}
METRICS = {
    "independent_pass_rate", "useful_verified_rate",
    "maintenance_minutes_per_case", "reexplanation_minutes_per_case",
    "review_minutes_per_case", "failed_attempts_per_case",
    "escaped_defects_per_case", "direct_cost_per_case",
}
LOWER_IS_BETTER = {
    "maintenance_minutes_per_case", "reexplanation_minutes_per_case",
    "review_minutes_per_case", "failed_attempts_per_case",
    "escaped_defects_per_case", "direct_cost_per_case",
}
REQUIRED_CLAIM_METRICS = {
    "useful_verified_rate", "maintenance_minutes_per_case",
    "reexplanation_minutes_per_case", "review_minutes_per_case",
    "failed_attempts_per_case", "escaped_defects_per_case", "direct_cost_per_case",
}


class OutcomeMeasurementError(ValueError):
    """The companion has an invalid shape or contradictory identifiers."""


def _timestamp(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OutcomeMeasurementError(f"{field} must be an ISO-8601 timestamp or null")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise OutcomeMeasurementError(f"{field} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None:
        raise OutcomeMeasurementError(f"{field} must include a timezone")
    return result


def _number(value: Any, field: str, *, integer: bool = False) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutcomeMeasurementError(f"{field} must be a non-negative number or null")
    if not math.isfinite(value) or value < 0 or (integer and int(value) != value):
        raise OutcomeMeasurementError(f"{field} must be a non-negative {'integer' if integer else 'number'} or null")
    return int(value) if integer else float(value)


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise OutcomeMeasurementError(f"{field} must be an array of non-empty strings")
    return value


def _ref(value: Any, field: str) -> bool:
    if value is not None and (not isinstance(value, str) or not value):
        raise OutcomeMeasurementError(f"{field} must be a non-empty reference or null")
    return isinstance(value, str) and bool(value)


def _validate_case(case: Any, index: int) -> dict[str, Any]:
    where = f"cases[{index}]"
    if not isinstance(case, dict):
        raise OutcomeMeasurementError(f"{where} must be an object")
    case_id, arm = case.get("case_id"), case.get("arm_id")
    if not isinstance(case_id, str) or not case_id:
        raise OutcomeMeasurementError(f"{where}.case_id must be a non-empty string")
    if arm not in ARMS:
        raise OutcomeMeasurementError(f"{where}.arm_id must be baseline or candidate")
    _timestamp(case.get("observed_at"), f"{where}.observed_at")
    _ref(case.get("artifact_revision_ref"), f"{where}.artifact_revision_ref")
    if not isinstance(case.get("run_ids"), list):
        raise OutcomeMeasurementError(f"{where}.run_ids must be an array")
    _strings(case["run_ids"], f"{where}.run_ids")

    acceptance = case.get("internal_acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("disposition") not in {
        "accepted", "rejected", "pending", "unknown",
    }:
        raise OutcomeMeasurementError(f"{where}.internal_acceptance.disposition is invalid")
    _ref(acceptance.get("owner_decision_ref"), f"{where}.internal_acceptance.owner_decision_ref")
    _timestamp(acceptance.get("observed_at"), f"{where}.internal_acceptance.observed_at")

    check = case.get("independent_requirements")
    if not isinstance(check, dict) or check.get("status") not in {"pass", "fail", "unknown", "not-applicable"}:
        raise OutcomeMeasurementError(f"{where}.independent_requirements.status is invalid")
    for key in ("criterion_refs", "oracle_refs", "evidence_refs", "unknown_required_checks"):
        _strings(check.get(key), f"{where}.independent_requirements.{key}")
    for key in ("oracle_origin", "independence_basis", "evaluator_ref", "evaluated_revision_ref"):
        _ref(check.get(key), f"{where}.independent_requirements.{key}")

    use = case.get("actual_use")
    if not isinstance(use, dict) or use.get("status") not in {"observed", "not-observed", "unknown", "not-applicable"}:
        raise OutcomeMeasurementError(f"{where}.actual_use.status is invalid")
    _ref(use.get("consumer_ref"), f"{where}.actual_use.consumer_ref")
    use_start = _timestamp(use.get("window_start"), f"{where}.actual_use.window_start")
    use_end = _timestamp(use.get("window_end"), f"{where}.actual_use.window_end")
    if use_start and use_end and use_end < use_start:
        raise OutcomeMeasurementError(f"{where}.actual_use.window_end precedes window_start")
    _strings(use.get("evidence_refs"), f"{where}.actual_use.evidence_refs")

    defects = case.get("escaped_defects")
    if not isinstance(defects, dict):
        raise OutcomeMeasurementError(f"{where}.escaped_defects must be an object")
    _number(defects.get("observed_count"), f"{where}.escaped_defects.observed_count", integer=True)
    _ref(defects.get("detection_method_ref"), f"{where}.escaped_defects.detection_method_ref")
    defect_start = _timestamp(defects.get("window_start"), f"{where}.escaped_defects.window_start")
    defect_end = _timestamp(defects.get("window_end"), f"{where}.escaped_defects.window_end")
    if defect_start and defect_end and defect_end < defect_start:
        raise OutcomeMeasurementError(f"{where}.escaped_defects.window_end precedes window_start")
    _ref(defects.get("coverage_description"), f"{where}.escaped_defects.coverage_description")
    _strings(defects.get("evidence_refs"), f"{where}.escaped_defects.evidence_refs")

    burden = case.get("burden")
    if not isinstance(burden, dict):
        raise OutcomeMeasurementError(f"{where}.burden must be an object")
    for key in ("maintenance_minutes", "reexplanation_minutes", "review_minutes", "failed_attempts"):
        observation = burden.get(key)
        if not isinstance(observation, dict):
            raise OutcomeMeasurementError(f"{where}.burden.{key} must be an object")
        _number(observation.get("value"), f"{where}.burden.{key}.value", integer=key == "failed_attempts")
        _strings(observation.get("source_refs"), f"{where}.burden.{key}.source_refs")
    cost = burden.get("direct_cost")
    if not isinstance(cost, dict):
        raise OutcomeMeasurementError(f"{where}.burden.direct_cost must be an object")
    _number(cost.get("amount"), f"{where}.burden.direct_cost.amount")
    currency = cost.get("currency")
    if currency is not None and (not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha() or not currency.isupper()):
        raise OutcomeMeasurementError(f"{where}.burden.direct_cost.currency must be a three-letter uppercase code or null")
    _strings(cost.get("source_refs"), f"{where}.burden.direct_cost.source_refs")
    return case


def _metric_value(metric: str, cases: list[dict[str, Any]], expected: list[str], use_required: bool) -> tuple[float | None, int]:
    if not expected:
        return None, 0
    by_id = {case["case_id"]: case for case in cases}
    if metric in {"independent_pass_rate", "useful_verified_rate"}:
        if metric == "useful_verified_rate" and not use_required:
            return None, 0
        eligible = []
        for case_id in expected:
            case = by_id.get(case_id)
            if case is None:
                continue
            check = case["independent_requirements"]
            status = check["status"]
            use = case["actual_use"]
            use_status = use["status"]
            independently_observed = (
                status in {"pass", "fail"}
                and bool(check["criterion_refs"] and check["oracle_refs"] and check["oracle_origin"]
                         and check["independence_basis"] and check["evaluator_ref"]
                         and check["evaluated_revision_ref"] == case.get("artifact_revision_ref")
                         and check["evidence_refs"] and not check["unknown_required_checks"])
            )
            if not independently_observed:
                continue
            use_observed = (
                use_status in {"observed", "not-observed"} and use["consumer_ref"]
                and use["window_start"] and use["window_end"] and use["evidence_refs"]
            )
            if metric == "useful_verified_rate" and not use_observed:
                continue
            eligible.append(status == "pass" and (metric != "useful_verified_rate" or use_status == "observed"))
        return (sum(eligible) / len(expected), len(eligible)) if len(eligible) == len(expected) else (None, len(eligible))

    field_map = {
        "maintenance_minutes_per_case": ("maintenance_minutes", "value"),
        "reexplanation_minutes_per_case": ("reexplanation_minutes", "value"),
        "review_minutes_per_case": ("review_minutes", "value"),
        "failed_attempts_per_case": ("failed_attempts", "value"),
        "escaped_defects_per_case": ("escaped_defects", "observed_count"),
        "direct_cost_per_case": ("direct_cost", "amount"),
    }
    container, key = field_map[metric]
    values: list[float] = []
    currencies: set[str] = set()
    for case_id in expected:
        case = by_id.get(case_id)
        if case is None:
            continue
        observation = case["escaped_defects"] if container == "escaped_defects" else case["burden"][container]
        value = observation.get(key)
        if value is None:
            continue
        if not observation.get("evidence_refs", observation.get("source_refs")):
            continue
        if metric == "direct_cost_per_case":
            currency = observation.get("currency")
            if currency is None:
                continue
            currencies.add(currency)
        elif metric == "escaped_defects_per_case":
            if not (observation.get("detection_method_ref") and observation.get("window_start")
                    and observation.get("window_end") and observation.get("coverage_description")):
                continue
        values.append(float(value))
    if metric == "direct_cost_per_case" and len(currencies) != 1:
        return None, len(values)
    if len(values) != len(expected):
        return None, len(values)
    return sum(values) / len(expected), len(values)


def assess(document: Any) -> dict[str, Any]:
    """Validate and summarize a companion without mutating it."""
    if not isinstance(document, dict):
        raise OutcomeMeasurementError("artifact root must be an object")
    if document.get("artifact_kind") != "outcome-measurement-companion":
        raise OutcomeMeasurementError("artifact_kind must be outcome-measurement-companion")
    plan = document.get("comparison")
    if not isinstance(plan, dict):
        raise OutcomeMeasurementError("comparison must be an object")
    expected = _strings(document.get("expected_case_ids"), "expected_case_ids")
    if len(expected) != len(set(expected)):
        raise OutcomeMeasurementError("expected_case_ids must be unique")
    cases_raw = document.get("cases")
    if not isinstance(cases_raw, list):
        raise OutcomeMeasurementError("cases must be an array")
    cases = [_validate_case(case, index) for index, case in enumerate(cases_raw)]
    seen: set[tuple[str, str]] = set()
    for case in cases:
        key = (case["arm_id"], case["case_id"])
        if key in seen:
            raise OutcomeMeasurementError(f"duplicate case observation: {key[0]}/{key[1]}")
        if key[1] not in expected:
            raise OutcomeMeasurementError(f"unexpected case id for {key[0]} arm: {key[1]}")
        seen.add(key)

    cohort = plan.get("cohort_id")
    if cohort is not None and cohort not in COHORTS:
        raise OutcomeMeasurementError("comparison.cohort_id must be software, household or creative")
    use_required = plan.get("use_required")
    if use_required is not None and not isinstance(use_required, bool):
        raise OutcomeMeasurementError("comparison.use_required must be a boolean")
    registered_at = _timestamp(plan.get("registered_at"), "comparison.registered_at")
    population_registered_at = _timestamp(document.get("population_registered_at"), "population_registered_at")
    observation_window = document.get("observation_window")
    if not isinstance(observation_window, dict):
        raise OutcomeMeasurementError("observation_window must be an object")
    window_start = _timestamp(observation_window.get("start"), "observation_window.start")
    window_end = _timestamp(observation_window.get("end"), "observation_window.end")
    if window_start and window_end and window_end < window_start:
        raise OutcomeMeasurementError("observation_window.end precedes start")

    arms = plan.get("arms")
    if arms is not None and not isinstance(arms, dict):
        raise OutcomeMeasurementError("comparison.arms must be an object")
    arm_refs_ok = isinstance(arms, dict)
    if isinstance(arms, dict):
        for arm in ARMS:
            entry = arms.get(arm)
            if not isinstance(entry, dict):
                arm_refs_ok = False
                continue
            arm_refs_ok &= _ref(entry.get("experiment_record_ref"), f"comparison.arms.{arm}.experiment_record_ref")
            arm_refs_ok &= _ref(entry.get("revision_ref"), f"comparison.arms.{arm}.revision_ref")
    arm_revision_refs = {
        arm: (arms.get(arm, {}).get("revision_ref")
              if isinstance(arms, dict) and isinstance(arms.get(arm), dict) else None)
        for arm in ARMS
    }

    threshold_owner = _ref(plan.get("threshold_owner_ref"), "comparison.threshold_owner_ref")
    claim_rule = _ref(plan.get("claim_rule_ref"), "comparison.claim_rule_ref")
    thresholds_raw = plan.get("thresholds")
    if thresholds_raw is None:
        thresholds_raw = []
    if not isinstance(thresholds_raw, list):
        raise OutcomeMeasurementError("comparison.thresholds must be an array")
    thresholds: list[dict[str, Any]] = []
    threshold_metrics: set[str] = set()
    threshold_dates_ok = True
    for index, threshold in enumerate(thresholds_raw):
        where = f"comparison.thresholds[{index}]"
        if not isinstance(threshold, dict):
            raise OutcomeMeasurementError(f"{where} must be an object")
        metric = threshold.get("metric")
        if metric not in METRICS:
            raise OutcomeMeasurementError(f"{where}.metric is unsupported")
        if metric in threshold_metrics:
            raise OutcomeMeasurementError(f"duplicate threshold for metric {metric}")
        threshold_metrics.add(metric)
        direction = threshold.get("direction")
        allowed = {"decrease", "no_worse"} if metric in LOWER_IS_BETTER else {"increase", "no_worse"}
        if metric == "useful_verified_rate":
            allowed = {"increase"}
        if direction not in allowed:
            raise OutcomeMeasurementError(f"{where}.direction must be one of {', '.join(sorted(allowed))}")
        amount = _number(threshold.get("amount"), f"{where}.amount")
        if amount is None or (amount == 0 and direction != "no_worse"):
            raise OutcomeMeasurementError(f"{where}.amount must be positive, except no_worse may be zero")
        if metric in {"independent_pass_rate", "useful_verified_rate"} and amount > 1:
            raise OutcomeMeasurementError(f"{where}.amount for a rate must be between 0 and 1")
        owner_ok = _ref(threshold.get("owner_ref"), f"{where}.owner_ref")
        date = _timestamp(threshold.get("registered_at"), f"{where}.registered_at")
        threshold_dates_ok &= owner_ok and date is not None
        if registered_at is not None and date is not None and date > registered_at:
            raise OutcomeMeasurementError(f"{where}.registered_at follows comparison preregistration")
        thresholds.append({**threshold, "amount": float(amount), "_date_ok": owner_ok and date is not None})

    earliest_observation: datetime | None = None
    for index, case in enumerate(cases):
        observed = _timestamp(case.get("observed_at"), f"cases[{index}].observed_at")
        if observed is not None and (earliest_observation is None or observed < earliest_observation):
            earliest_observation = observed
    chronologically_preregistered = bool(registered_at and earliest_observation and registered_at <= earliest_observation)
    if any(t.get("_date_ok") for t in thresholds):
        chronologically_preregistered &= all(
            _timestamp(t.get("registered_at"), "comparison.thresholds.registered_at") <= earliest_observation
            for t in thresholds if t.get("_date_ok") and earliest_observation is not None
        )

    requirements_ref = _ref(document.get("requirements_ref"), "requirements_ref")
    population_ref = _ref(document.get("population_ref"), "population_ref")
    evaluation_ref = _ref(document.get("evaluation_policy_ref"), "evaluation_policy_ref")
    population_date_ok = population_registered_at is not None and window_start is not None
    if population_registered_at and window_start:
        population_date_ok &= population_registered_at <= window_start
    dated_case_pairs = {
        (case["arm_id"], case["case_id"]) for case in cases if case.get("observed_at") is not None
    }
    full_observation_dates = bool(expected) and len(dated_case_pairs) == len(expected) * len(ARMS)
    case_dates_in_window = all(
        case.get("observed_at") is None or (
            window_start is not None and window_end is not None
            and window_start <= _timestamp(case["observed_at"], "cases.observed_at") <= window_end
        )
        for case in cases
    )
    scope_ready = bool(
        cohort in COHORTS and population_ref and requirements_ref and evaluation_ref
        and population_date_ok and expected and window_start and window_end
        and use_required is True and arm_refs_ok and threshold_owner and claim_rule
        and REQUIRED_CLAIM_METRICS <= threshold_metrics
        and threshold_dates_ok and chronologically_preregistered
        and full_observation_dates and case_dates_in_window
    )

    arm_reports: dict[str, Any] = {}
    metric_values: dict[str, dict[str, tuple[float | None, int]]] = {}
    arm_cost_currencies: dict[str, str | None] = {}
    for arm in ARMS:
        arm_cases = [case for case in cases if case["arm_id"] == arm]
        found = {case["case_id"] for case in arm_cases}
        missing = [case_id for case_id in expected if case_id not in found]
        unbound_revision_ids = [
            case["case_id"] for case in arm_cases
            if not arm_revision_refs[arm] or case.get("artifact_revision_ref") != arm_revision_refs[arm]
        ]
        metrics: dict[str, Any] = {}
        for metric in sorted(METRICS):
            value, known = _metric_value(metric, arm_cases, expected, use_required is True)
            metrics[metric] = {"value": value, "known_cases": known, "denominator": len(expected)}
            metric_values.setdefault(metric, {})[arm] = (value, known)
        costs = [case["burden"]["direct_cost"] for case in arm_cases
                 if case["burden"]["direct_cost"].get("amount") is not None
                 and case["burden"]["direct_cost"].get("source_refs")]
        currencies = {cost.get("currency") for cost in costs}
        arm_cost_currencies[arm] = next(iter(currencies)) if len(currencies) == 1 else None
        acceptance_counts: dict[str, int] = {}
        unsubstantiated_acceptance_ids = []
        for case in arm_cases:
            disposition = case["internal_acceptance"]["disposition"]
            supported = disposition == "unknown" or (
                case["internal_acceptance"]["owner_decision_ref"]
                and case["internal_acceptance"]["observed_at"]
            )
            if not supported:
                unsubstantiated_acceptance_ids.append(case["case_id"])
                disposition = "unknown"
            acceptance_counts[disposition] = acceptance_counts.get(disposition, 0) + 1
        arm_reports[arm] = {
            "case_count": len(arm_cases), "expected_cases": len(expected),
            "missing_case_ids": missing, "unbound_revision_case_ids": unbound_revision_ids,
            "internal_acceptance_dispositions": acceptance_counts,
            "unsubstantiated_acceptance_case_ids": unsubstantiated_acceptance_ids,
            "direct_cost_currency": arm_cost_currencies[arm], "metrics": metrics,
        }

    threshold_reports = []
    thresholds_pass = True
    all_threshold_data_complete = bool(thresholds)
    for threshold in thresholds:
        metric = threshold["metric"]
        baseline, baseline_known = metric_values[metric]["baseline"]
        candidate, candidate_known = metric_values[metric]["candidate"]
        amount, direction = threshold["amount"], threshold["direction"]
        currencies_match = (
            metric != "direct_cost_per_case"
            or (arm_cost_currencies["baseline"] is not None
                and arm_cost_currencies["baseline"] == arm_cost_currencies["candidate"])
        )
        complete = baseline is not None and candidate is not None and currencies_match
        if not complete:
            passed = False
            status = "incomplete"
        elif direction == "increase":
            passed = candidate - baseline >= amount
            status = "passed" if passed else "threshold-not-met"
        elif direction == "decrease":
            passed = baseline - candidate >= amount
            status = "passed" if passed else "threshold-not-met"
        else:
            passed = candidate - baseline <= amount
            status = "passed" if passed else "guardrail-exceeded"
        thresholds_pass &= passed
        all_threshold_data_complete &= complete
        threshold_reports.append({
            "metric": metric, "direction": direction, "amount": amount,
            "baseline": baseline, "candidate": candidate,
            "currency": arm_cost_currencies["baseline"] if metric == "direct_cost_per_case" and currencies_match else None,
            "baseline_currency": arm_cost_currencies["baseline"] if metric == "direct_cost_per_case" else None,
            "candidate_currency": arm_cost_currencies["candidate"] if metric == "direct_cost_per_case" else None,
            "baseline_known_cases": baseline_known, "candidate_known_cases": candidate_known,
            "status": status,
        })

    all_arm_cases_present = bool(expected) and all(
        not arm_reports[arm]["missing_case_ids"] and not arm_reports[arm]["unbound_revision_case_ids"]
        for arm in ARMS
    )
    useful_threshold = next((row for row in threshold_reports if row["metric"] == "useful_verified_rate"), None)
    outcome_claim_allowed = bool(
        scope_ready and all_arm_cases_present and useful_threshold
        and useful_threshold["status"] == "passed"
    )
    benefit_claim_allowed = bool(
        outcome_claim_allowed and all_threshold_data_complete and thresholds_pass
    )
    if not scope_ready:
        state = "not-preregistered"
    elif not all_arm_cases_present or not all_threshold_data_complete:
        state = "incomplete"
    elif thresholds_pass:
        state = "thresholds-met"
    else:
        state = "thresholds-not-met"
    return {
        "artifact_kind": "outcome-measurement-preflight-report",
        "cohort_id": cohort,
        "state": state,
        "outcome_improvement_claim_allowed": outcome_claim_allowed,
        "benefit_claim_allowed": benefit_claim_allowed,
        "population_denominator": len(expected),
        "arms": arm_reports,
        "threshold_results": threshold_reports,
        "limitations": [
            "This report is a descriptive, read-only preflight; it does not establish causality or owner acceptance.",
            "Unknown effort, cost, use, defect and correctness observations are not converted to zero.",
            "Outcome improvement requires the useful-verified threshold to pass.",
            "A benefit claim also requires complete evidence and passing thresholds for burden, failed attempts, defects and cost.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("companion", type=Path, help="authored outcome-measurement companion JSON")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.companion.read_text())
        report = assess(document)
    except (OSError, json.JSONDecodeError, OutcomeMeasurementError) as exc:
        print(json.dumps({"state": "invalid", "error": str(exc)}), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{report['cohort_id'] or 'unassigned'}: {report['state']}; "
              f"outcome_improvement_claim_allowed={str(report['outcome_improvement_claim_allowed']).lower()}; "
              f"benefit_claim_allowed={str(report['benefit_claim_allowed']).lower()}")
        for threshold in report["threshold_results"]:
            print(f"{threshold['metric']}: {threshold['status']}")
    return 0 if report["state"] in {"thresholds-met", "thresholds-not-met"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
