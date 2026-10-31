#!/usr/bin/env python3
"""Reproduce synthetic Work2873 KVM controls; never run or accept real Work.

Usage: verify_estate_acceptance.py INSTALLED_PACKAGE LOCAL_PUBLIC_REPO OUTPUT
The local repo must contain the pinned public baseline. All candidate edits and
commits are confined to temporary clones; no model, network or owner is called.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository_delivery import git

BASE = "dcb137a42c5bd135415515c8d750ec8c5b1b1660"
SOURCE = "scripts/estate_status.py"
TEST = "scripts/tests/test_estate_maintenance.py"
GUARD = "not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit <= 0"
ADDED = '''    def test_boolean_limits_are_unknown(self):
        for value in (True, False):
            data = report()
            data["jobs"]["talos-etcd-backup.service"]["max_age_hours"] = value
            self.assertEqual(estate.maintenance_fact(probe(data), "infra")["status"], "unknown")

'''


def need(value):
    if not value: raise ValueError("synthetic-acceptance-control-failed")


def fixture(parent, source, kind):
    root = parent / kind
    git(source, "clone", "--shared", "--no-checkout", "--", str(source), str(root))
    git(root, "checkout", "--detach", BASE)
    code = (root/SOURCE).read_text()
    need(code.count(GUARD) == 1)
    if kind != "unfixed": code = code.replace(GUARD, GUARD.replace("not isinstance(limit, (int, float))", "type(limit) not in (int, float)"))
    if kind == "unrelated": code += "\nUNRELATED_SYNTHETIC_CONTROL = True\n"
    if kind == "unfixed": code += "\n# Synthetic unchanged-defect control.\n"
    tests = (root/TEST).read_text().replace("class MaintenanceFacts(unittest.TestCase):\n", "class MaintenanceFacts(unittest.TestCase):\n" + ADDED)
    if kind == "vacuous":
        tests = tests.replace(ADDED, ADDED + "    def test_vacuous_control(self):\n        self.assertTrue(True)\n\n")
    (root/SOURCE).write_text(code); (root/TEST).write_text(tests)
    git(root, "add", "--", SOURCE, TEST)
    git(root, "-c", "user.name=SyntheticFixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "Synthetic acceptance control; not a real Work2873 run")
    return root, git(root, "rev-parse", "HEAD").decode().strip()


def command(package, mode, row):
    return [str(package/"bin"/("estate-maintenance-"+mode)), str(row[0]), BASE, row[1]]


def invoke(package, mode, row, expected):
    start = time.monotonic()
    result = subprocess.run(command(package, mode, row), capture_output=True, text=True, timeout=140)
    need(result.returncode == expected and not result.stderr)
    receipt = json.loads(result.stdout)
    need(receipt["outcome"] == ("passed" if expected == 0 else "failed"))
    if expected == 0:
        metrics = {"cases": 17, "baseline_tests": 109} if mode == "check" else {
            "type_partitions": 8, "added_regressions": 1,
            "regression_tests": 1, "baseline_failures": 1}
        need(receipt["metrics"] == metrics)
    return {"returncode": result.returncode, "elapsed_seconds": round(time.monotonic()-start, 2), "receipt": receipt}


def running(pid):
    try: return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError: return False


def interrupted(package, row, target):
    process = subprocess.Popen(command(package, "check", row), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True)
    qemu = None
    try:
        end = time.monotonic()+20
        while time.monotonic() < end and process.poll() is None:
            children = Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()
            for pid in children:
                try: raw = Path(f"/proc/{pid}/cmdline").read_bytes()
                except FileNotFoundError: continue
                if b"qemu-system-x86_64\0" in raw: qemu = int(pid); break
            if qemu is not None: break
            time.sleep(.02)
        need(qemu is not None)
        os.kill(process.pid if target == "parent" else qemu, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=8)
        end = time.monotonic()+5
        while running(qemu) and time.monotonic() < end: time.sleep(.02)
        need(not running(qemu))
        if target == "qemu":
            need(process.returncode == 124 and not stdout
                 and stderr.strip() == b"estate-acceptance-outcome-unknown")
        else: need(process.returncode == -signal.SIGKILL and not stdout)
        return {"target": target, "returncode": process.returncode, "qemu_stopped": True,
                "positive_receipt": False}
    finally:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=3)


def main():
    need(len(sys.argv) == 4)
    package, source, output = map(Path, sys.argv[1:])
    need(package.is_absolute() and str(package).startswith("/nix/store/") and source.is_absolute())
    pins = json.loads((package/"driver-pins.json").read_bytes())
    need(pins["qualified"] is False and pins["work_base"] == BASE)
    for mode in ("check", "review"):
        path = (package/"bin"/("estate-maintenance-"+mode)).resolve(strict=True)
        need(str(path) == pins["drivers"][mode]["path"]
             and hashlib.sha256(path.read_bytes()).hexdigest() == pins["drivers"][mode]["sha256"])
    with tempfile.TemporaryDirectory(prefix="estate-acceptance-controls-") as temporary:
        rows = {kind: fixture(Path(temporary), source, kind) for kind in ("positive", "unfixed", "unrelated", "vacuous")}
        results = {"positive-"+mode: invoke(package, mode, rows["positive"], 0) for mode in ("check", "review")}
        need(results["positive-check"]["receipt"]["guest_boot_id"] != results["positive-review"]["receipt"]["guest_boot_id"])
        for kind in ("unfixed", "unrelated"):
            for mode in ("check", "review"): results[kind+"-"+mode] = invoke(package, mode, rows[kind], 1)
        results["vacuous-review"] = invoke(package, "review", rows["vacuous"], 1)
        results["parent-death"] = interrupted(package, rows["positive"], "parent")
        results["qemu-death"] = interrupted(package, rows["positive"], "qemu")
    value = {"schema_version": "agentops-estate-acceptance-synthetic-proof/v1", "qualified": False,
        "scope": "local KVM synthetic controls only; no Work, owner, model, deployment or publication authority",
        "package": str(package), "pins": pins, "results": results}
    output.write_text(json.dumps(value, sort_keys=True, indent=2)+"\n")
    print(json.dumps({"controls": len(results), "passed": True, "qualified": False,
        "proof_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__": main()
