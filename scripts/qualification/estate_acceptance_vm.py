#!/usr/bin/env python3
"""One fixed diskless KVM check/review; no network, model or Work authority.

An immutable Nix launcher supplies configuration and mode. The three consumer
arguments are a clean checkout, exact Work base and candidate. Candidate bytes
enter a fixed root-owned initramfs path, never a host command or guest image.
"""
from __future__ import annotations

import ctypes
import gzip
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository_delivery import git, git_ancestor

ALLOWED = ("scripts/estate_status.py", "scripts/tests/test_estate_maintenance.py")
SHA = re.compile(r"[0-9a-f]{40}\Z")
LIMIT = 4 * 1024 * 1024


def need(value, code="acceptance-input-refused"):
    if not value: raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def cpio(payload):
    """Only two fixed newc members, no archive names supplied by a candidate."""
    def entry(name, data, mode, inode):
        name = name.encode() + b"\0"
        fields = [inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0]
        header = b"070701" + b"".join(f"{number:08x}".encode() for number in fields)
        value = header + name
        value += b"\0" * (-len(value) % 4)
        value += data + b"\0" * (-len(data) % 4)
        return value
    need(len(payload) <= LIMIT)
    archive = entry("input", b"", stat.S_IFDIR | 0o755, 1)
    archive += entry("input/payload.json", payload, stat.S_IFREG | 0o444, 2)
    archive += entry("TRAILER!!!", b"", 0, 3)
    return gzip.compress(archive, mtime=0)


def candidate(repo, base, tip, baseline):
    need(SHA.fullmatch(base) and SHA.fullmatch(tip) and base != tip)
    need(git(repo, "rev-parse", "HEAD").decode().strip() == tip)
    need(not git(repo, "status", "--porcelain", "--untracked-files=all"))
    need(git_ancestor(repo, base, tip))
    records = git(repo, "diff", "--name-status", "--no-renames", "-z", base, tip).split(b"\0")
    need(records[-1:] == [b""] and len(records) == 5)
    changed = {records[i+1].decode(): records[i].decode() for i in (0, 2)}
    need(changed == {name: "M" for name in ALLOWED})
    rows = git(repo, "ls-tree", tip, "--", *ALLOWED).decode().splitlines()
    need(len(rows) == 2 and all(row.startswith("100644 blob ") for row in rows))
    files = {}
    for name in ALLOWED:
        need(git(repo, "show", base + ":" + name) == (Path(baseline)/name).read_bytes(), "baseline-file-changed")
        raw = git(repo, "show", tip + ":" + name)
        need(len(raw) <= 2 * 1024 * 1024)
        files[name] = raw.decode("utf-8")
    return files


def parent_death(expected_parent):
    # QEMU remains in the delivery driver's process group. Killing that group
    # stops it, and killing only its parent also cannot leave it running.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0): os._exit(126)
    if os.getppid() != expected_parent: os._exit(126)


def execute(config, mode, repo, base, tip):
    fields = {"schema_version", "work_base", "baseline", "kernel", "initrd", "qemu"}
    need(set(config) == fields and config["schema_version"] == "agentops-estate-acceptance-vm/v1")
    need(base == config["work_base"] and mode in {"check", "review"})
    for key in ("baseline", "kernel", "initrd", "qemu"):
        path = Path(config[key]); need(str(path).startswith("/nix/store/"))
        info = path.stat(); need(info.st_uid == 0 and not info.st_mode & 0o022)
    files = candidate(repo, base, tip, config["baseline"])
    payload = {"schema_version": "agentops-estate-acceptance-input/v1", "mode": mode,
               "base": base, "candidate": tip, "challenge": os.urandom(32).hex(), "files": files}
    raw = canonical(payload); need(len(raw) <= LIMIT)
    digest = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix="agentops-acceptance-") as temporary:
        root = Path(temporary); initrd = root/"input-initrd"
        with Path(config["initrd"]).open("rb") as source, initrd.open("xb") as output:
            while part := source.read(1024 * 1024): output.write(part)
            output.write(cpio(raw))
        command = [config["qemu"], "-no-user-config", "-nodefaults", "-display", "none",
            "-machine", "microvm", "-accel", "kvm", "-cpu", "host,-vmx,-svm",
            "-m", "1536", "-smp", "1", "-nic", "none", "-monitor", "none",
            "-parallel", "none", "-serial", "stdio", "-no-reboot",
            "-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
            "-kernel", config["kernel"], "-initrd", str(initrd),
            "-append", "console=ttyS0 quiet loglevel=0 panic=-1 rdinit=/init"]
        with (root/"serial").open("w+b") as serial:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=serial,
                stderr=subprocess.DEVNULL, env={"LANG": "C", "HOME": "/nonexistent"},
                preexec_fn=functools.partial(parent_death, os.getpid()))
            try:
                end = time.monotonic() + 120
                while process.poll() is None and time.monotonic() < end:
                    need(serial.tell() <= 65536, "acceptance-serial-overflow")
                    time.sleep(.05)
                if process.poll() is None: raise TimeoutError("acceptance-outcome-unknown")
                serial.seek(0); output = serial.read(65537)
                need(len(output) <= 65536)
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=3)
        records = [line[len(b"AGENTOPS-ACCEPTANCE "):] for line in output.replace(b"\r\n", b"\n").splitlines()
                   if line.startswith(b"AGENTOPS-ACCEPTANCE ")]
        need(len(records) == 1, "acceptance-outcome-unknown")
        receipt = json.loads(records[0])
        need(set(receipt) == {"schema_version", "mode", "base", "candidate", "challenge", "input_sha256", "outcome", "metrics", "guest_boot_id", "reason"})
        spec = importlib.util.spec_from_file_location("trusted_oracle_codes", Path(__file__).with_name("estate_maintenance_oracle.py"))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        need(receipt["reason"] in module.FAILURE_CODES | {"none", "guest-outcome-unknown"})
        need(type(receipt["metrics"]) is dict and all(type(value) is int and 0 < value < 100000 for value in receipt["metrics"].values()))
        need(type(receipt["guest_boot_id"]) is str and re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", receipt["guest_boot_id"]))
        metrics = {"cases", "baseline_tests"} if mode == "check" else {"type_partitions", "added_regressions", "regression_tests", "baseline_failures"}
        need(receipt["outcome"] != "passed" or set(receipt["metrics"]) == metrics)
        need(receipt == {"schema_version": "agentops-estate-acceptance-result/v1", "mode": mode,
            "base": base, "candidate": tip, "challenge": payload["challenge"], "input_sha256": digest,
            "outcome": receipt["outcome"], "metrics": receipt["metrics"],
            "guest_boot_id": receipt["guest_boot_id"], "reason": receipt["reason"]} and receipt["outcome"] in {"passed", "failed", "unknown"})
        print(json.dumps(receipt, sort_keys=True))
        return {"passed": 0, "failed": 1, "unknown": 124}[receipt["outcome"]]


def main():
    need(len(sys.argv) == 6)
    path = Path(sys.argv[1]); need(str(path).startswith("/nix/store/"))
    config = json.loads(path.read_bytes())
    return execute(config, sys.argv[2], Path(sys.argv[3]), sys.argv[4], sys.argv[5])


if __name__ == "__main__":
    def expired(_signum, _frame): raise TimeoutError("acceptance-outcome-unknown")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 125)
    try: raise SystemExit(main())
    except Exception:
        print("estate-acceptance-outcome-unknown", file=sys.stderr)
        raise SystemExit(124) from None
