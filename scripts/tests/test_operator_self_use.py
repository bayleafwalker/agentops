import datetime
import json
import unittest
from pathlib import Path

from scripts.estate_status import evaluate_operator_self_use


def valid_record():
    return {
        "scope": {"workspaces": ["kotona"], "operator_owned": True, "host_owner": "operator"},
        "reviewed_on": "2026-11-08",
        "pat": {"id": "01M6XKNE9ZJRSYM7F5DXDGXVXT", "expires_on": "2026-11-28",
                "workspace": "kotona", "authorities": ["work:read"]},
        "evidence_refs": {"cutover_plan": "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md",
                          "composition_qualification": {"ref": "receipt.json", "pinned_pair": {"tenant_runtime_pin": "runtime", "sprintctl_version": "0.18.0"}}},
        "cutover_open_rows": [], "profile_valid": True,
        "latest_restored_observation": {"status": "restored", "date": "2026-11-07"},
        "rehearsal_on": "2026-11-06", "vuoro_shared_fallback": True,
        "fallback_environment": "vuoro-shared",
    }


class OperatorSelfUseTests(unittest.TestCase):
    def eval_record(self, record, ready=False, day="2026-11-08"):
        return evaluate_operator_self_use(record,
            desired_release_ready={"status": "known", "value": ready}, today=datetime.date.fromisoformat(day),
            pinned_pair={"tenant_runtime_pin": "runtime", "sprintctl_version": "0.18.0"})

    def test_met(self):
        result = self.eval_record(valid_record())
        self.assertEqual(result["status"], "met")
        self.assertTrue(result["not_release_ready"])

    def test_each_not_met_check(self):
        cases = [
            ("profile_valid", False),
            ("cutover_open_rows", ["open"]),
            ("evidence_refs", {}),
            ("latest_restored_observation", None),
            ("pat", {"id": "01M6XKNE9ZJRSYM7F5DXDGXVXT", "expires_on": "2027-01-01",
                     "workspace": "kotona", "authorities": ["work:read"]}),
            ("vuoro_shared_fallback", None),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                r = valid_record(); r[field] = value
                self.assertEqual(self.eval_record(r)["status"], "not_met")
        r = valid_record(); r["evidence_refs"]["composition_qualification"] = None
        b3 = self.eval_record(r)
        self.assertEqual(b3["status"], "not_met")
        self.assertTrue(b3["first_failing_check"].startswith("B3 "))
        b7 = evaluate_operator_self_use(valid_record(), desired_release_ready=None,
            today=datetime.date(2026, 11, 8), pinned_pair={"tenant_runtime_pin": "runtime", "sprintctl_version": "0.18.0"})
        self.assertEqual(b7["status"], "not_met")
        self.assertTrue(b7["first_failing_check"].startswith("B7 "))
        self.assertEqual(self.eval_record(valid_record(), ready=True)["status"], "void")

    def test_each_void_condition(self):
        cases = [
            ("revoked", True), ("pat_reissued", True),
            ("pat", {"id": "replacement", "expires_on": "2026-11-28", "workspace": "kotona", "authorities": ["work:write"]}),
            ("tenant_runtime_pin_changed_after_composition", True),
            ("vuoro_shared_fallback", False),
            ("scope", {"workspaces": ["kotona", "other"], "operator_owned": True}),
            ("reviewed_on", "2026-01-01"),
            ("rehearsal_on", "2026-11-08"),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                r = valid_record(); r[field] = value
                self.assertEqual(self.eval_record(r)["status"], "void")
        r = valid_record(); self.assertEqual(self.eval_record(r, day="2026-12-09")["status"], "void")
        r = valid_record(); r["evidence_refs"]["composition_qualification"]["pinned_pair"]["sprintctl_version"] = "0.20.0"
        self.assertEqual(self.eval_record(r)["status"], "void")
        r = valid_record(); r["latest_restored_observation"] = None
        r["no_restored_observation_since"] = "2026-10-01"
        self.assertEqual(self.eval_record(r)["status"], "void")
        r = valid_record(); r["latest_restored_observation"]["date"] = "2026-10-01"
        self.assertEqual(self.eval_record(r, day="2026-11-08")["status"], "void")


if __name__ == "__main__":
    unittest.main()
