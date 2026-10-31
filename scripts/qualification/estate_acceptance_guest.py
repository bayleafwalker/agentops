#!/usr/bin/env python3
"""Trusted diskless acceptance guest supervisor; no network/host credentials."""
from __future__ import annotations

import hashlib
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

LIMIT = 4 * 1024 * 1024
SOURCE = "scripts/estate_status.py"
TEST = "scripts/tests/test_estate_maintenance.py"


def need(value):
    if not value: raise ValueError("acceptance-guest-refused")


def copy_file(source, target):
    info = source.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_size <= 4 * 1024 * 1024)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    target.chmod(0o555 if info.st_mode & 0o111 else 0o444)


def unprivileged():
    if ctypes.CDLL(None).prctl(38, 1, 0, 0, 0): os._exit(126)
    os.setgroups([]); os.setgid(1000); os.setuid(1000)
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def quiesce():
    for _ in range(50):
        found = []
        for path in Path("/proc").iterdir():
            if path.name.isdecimal():
                try:
                    if path.stat().st_uid == 1000: found.append(int(path.name))
                except FileNotFoundError: pass
        if not found: return
        for pid in found:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        while True:
            try:
                if os.waitpid(-1, os.WNOHANG)[0] == 0: break
            except ChildProcessError: break
        time.sleep(.02)
    raise ValueError("acceptance-child-not-quiescent")


def run(config, payload):
    need(os.geteuid() == 0)
    need(config["baseline_revision"] == "dcb137a42c5bd135415515c8d750ec8c5b1b1660")
    need(set(os.listdir("/sys/class/net")) == {"lo"} and not os.listdir("/sys/block"))
    need(not any(kind in Path("/proc/mounts").read_text() for kind in (" 9p ", " virtiofs ", " nfs ")))
    need(set(payload) == {"schema_version", "mode", "base", "candidate", "challenge", "files"}
         and payload["schema_version"] == "agentops-estate-acceptance-input/v1"
         and payload["mode"] in {"check", "review"} and set(payload["files"]) == {SOURCE, TEST})
    baseline = Path(config["baseline"]); root = Path("/work/repository")
    os.symlink(baseline, "/baseline")
    root.mkdir(parents=True)
    # Only pinned public baseline code/schema/fixtures are executable inputs.
    for name in ("bin/agentops", SOURCE, "scripts/estate_mcp.py", "scripts/schema_check.py",
                 "environment-record/estate-status-v1.schema.json"):
        copy_file(baseline/name, root/name)
    for source in sorted((baseline/"scripts/tests").glob("test_estate*.py")):
        copy_file(source, root/"scripts/tests"/source.name)
    fixture = "scripts/tests/fixtures/estate_status/live-2026-10-14"
    for source in sorted((baseline/fixture).rglob("*")):
        if source.is_file(): copy_file(source, root/source.relative_to(baseline))
    (root/SOURCE).chmod(0o644)
    (root/SOURCE).write_bytes(payload["files"][SOURCE].encode("utf-8")); (root/SOURCE).chmod(0o444)
    Path("/input/candidate-test.py").write_bytes(payload["files"][TEST].encode("utf-8"))
    Path("/input/candidate-test.py").chmod(0o444)
    if payload["mode"] == "review":
        for kind in ("candidate", "baseline"):
            target = Path("/work/regression-" + kind)
            copy_file(baseline/SOURCE, target/SOURCE)
            (target/TEST).parent.mkdir(parents=True)
            (target/TEST).write_bytes(payload["files"][TEST].encode("utf-8")); (target/TEST).chmod(0o444)
            if kind == "candidate":
                (target/SOURCE).chmod(0o644)
                (target/SOURCE).write_bytes(payload["files"][SOURCE].encode("utf-8")); (target/SOURCE).chmod(0o444)
    sentinel = Path("/run/agentops-acceptance-guest.json")
    sentinel.write_text(json.dumps({"schema_version": "agentops-estate-acceptance-guest/v1", "base": config["baseline_revision"]}))
    sentinel.chmod(0o444)
    marker = Path("/run/acceptance-parent-private")
    marker.write_text("synthetic-owner-db-and-storage-marker")
    marker.chmod(0o600)
    need(marker.read_text() == "synthetic-owner-db-and-storage-marker")
    home = Path("/tmp/home"); home.mkdir(); os.chown(home, 1000, 1000)
    # The executable cannot acquire host credentials or a guest root identity.
    process = subprocess.Popen([config["python"], "-I", "-B", config["oracle"], payload["mode"]],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=root, env={"PATH": config["path"], "HOME": str(home), "LANG": "C.UTF-8",
                       "PYTHONDONTWRITEBYTECODE": "1"}, preexec_fn=unprivileged, start_new_session=True)
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    selector = selectors.DefaultSelector()
    for stream in streams: selector.register(stream, selectors.EVENT_READ)
    try:
        deadline = time.monotonic() + 100
        while selector.get_map() and time.monotonic() < deadline:
            for key, _ in selector.select(.05):
                part = os.read(key.fd, 8192)
                if not part: selector.unregister(key.fileobj); continue
                streams[key.fileobj].extend(part)
                need(sum(map(len, streams.values())) <= 256 * 1024)
        if selector.get_map(): return "unknown", {}, "guest-outcome-unknown"
        process.wait(timeout=max(.001, deadline - time.monotonic()))
        stderr = bytes(streams[process.stderr]).strip()
        if process.returncode == 1 and stderr.startswith(b"estate-acceptance-refused:"):
            spec = importlib.util.spec_from_file_location("trusted_oracle_codes", config["oracle"])
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            reason = stderr[len(b"estate-acceptance-refused:"):].decode("ascii")
            need(reason in module.FAILURE_CODES)
            return "failed", {}, reason
        need(process.returncode == 0)
        result = json.loads(streams[process.stdout])
        need(result["schema_version"] == "agentops-estate-acceptance-oracle/v1"
             and result["mode"] == payload["mode"] and result["complete"] is True
             and result["boundary_probed"] is True)
        fields = {"cases", "baseline_tests"} if payload["mode"] == "check" else {"type_partitions", "added_regressions", "regression_tests", "baseline_failures"}
        metrics = {name: result[name] for name in fields}
        need(all(type(value) is int and 0 < value < 100000 for value in metrics.values()))
        return "passed", metrics, "none"
    finally:
        selector.close()
        if process.poll() is None: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
        quiesce()


def main():
    config = json.loads(Path(sys.argv[1]).read_bytes())
    raw = Path("/input/payload.json").read_bytes(); need(len(raw) <= LIMIT)
    payload = json.loads(raw)
    outcome, metrics, reason = "unknown", {}, "guest-outcome-unknown"
    try: outcome, metrics, reason = run(config, payload)
    except Exception: pass
    receipt = {"schema_version": "agentops-estate-acceptance-result/v1",
        **{key: payload[key] for key in ("mode", "base", "candidate", "challenge")},
        "input_sha256": hashlib.sha256(raw).hexdigest(), "outcome": outcome, "metrics": metrics,
        "guest_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "reason": reason}
    # Candidate stdout/stderr is never copied to the root-only serial channel.
    print("AGENTOPS-ACCEPTANCE " + json.dumps(receipt, sort_keys=True), flush=True)
    subprocess.run([config["poweroff"], "-f"], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)


if __name__ == "__main__":
    try: main()
    except Exception:
        raise SystemExit(124) from None
