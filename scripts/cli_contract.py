#!/usr/bin/env python3
"""Operator interface conformance: `agentops cli-contract [options] -- <command...>`.

Probes one command-line tool against docs/contracts/operator-interface.md and
reports PASS/FAIL/SKIP per check with the evidence it saw. It runs only
`--help`, `--version`, a bare invocation, a misspelled subcommand, an unknown
option and (with --status) the tool's read-only status command, so it is safe
to run against any tool that keeps those read-only.

Examples:
  agentops cli-contract -- lanectl
  agentops cli-contract --command status --status status -- sprintctl
  agentops cli-contract --json --command list -- direnv exec /projects/dev/auditctl auditctl

Exit status: 0 when no check fails, 1 when one does, 2 for usage errors.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

SCHEMA = "agentops.cli-contract/v1"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
VERSIONISH = re.compile(r"\b(v?\d+\.\d+(\.\d+)?|[0-9a-f]{7,40})\b")
TRUNCATED = re.compile(r"\w(\.\.\.|…)\s*$")
TRACEBACK = "Traceback (most recent call last)"


@dataclass
class Check:
    id: str
    result: str  # pass | fail | skip
    detail: str


@dataclass
class Run:
    code: int
    out: str
    err: str
    seconds: float


def run(argv: list[str], env: dict[str, str], timeout: float) -> Run:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Run(124, "", f"timed out after {timeout:g}s", time.monotonic() - start)
    except OSError as exc:
        return Run(127, "", str(exc), time.monotonic() - start)
    return Run(proc.returncode, proc.stdout, proc.stderr, time.monotonic() - start)


def excerpt(text: str, limit: int = 100) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= limit else line[: limit - 1] + "…"


def typo_of(name: str) -> str:
    if len(name) < 3:
        return name + "x"
    i = len(name) // 2
    swapped = name[: i - 1] + name[i] + name[i - 1] + name[i + 1 :]
    # A swap of two equal letters ("commit") would run the real command.
    return swapped if swapped != name else name + "x"


def evaluate(cmd: list[str], args: argparse.Namespace) -> list[Check]:
    env = {k: v for k, v in os.environ.items() if k not in {"FORCE_COLOR", "CLICOLOR_FORCE"}}
    env.update({"NO_COLOR": "1", "COLUMNS": "80", "TERM": "dumb"})
    checks: list[Check] = []

    def add(cid: str, ok: bool | None, detail: str) -> None:
        checks.append(Check(cid, "skip" if ok is None else "pass" if ok else "fail", detail))

    help_run = run(cmd + ["--help"], env, args.timeout)
    add("help.exit_zero", help_run.code == 0 and bool(help_run.out.strip()),
        f"exit {help_run.code}; stdout {len(help_run.out)} bytes; {excerpt(help_run.err or help_run.out)}")
    add("help.speed", help_run.seconds <= args.help_budget,
        f"{help_run.seconds:.2f}s (budget {args.help_budget:g}s)")
    help_text = help_run.out
    has_examples = bool(re.search(r"(?im)^\s*examples?:", help_text))
    add("help.examples", has_examples,
        "has an Examples: section" if has_examples else "no 'Examples:' section in --help")
    cut = [ln.strip() for ln in help_text.splitlines() if TRUNCATED.search(ln)]
    add("help.no_truncation", not cut, f"{len(cut)} truncated line(s)" + (f": {cut[0][:80]}" if cut else ""))
    wide = [ln for ln in help_text.splitlines() if len(ln) > args.max_width]
    add("help.width", not wide,
        f"{len(wide)} line(s) wider than {args.max_width} at COLUMNS=80"
        + (f" (widest {max(map(len, wide))})" if wide else ""))
    add("help.no_color", not ANSI.search(help_run.out + help_run.err), "NO_COLOR=1 respected"
        if not ANSI.search(help_run.out + help_run.err) else "ANSI escapes despite NO_COLOR=1")

    ver = run(cmd + ["--version"], env, args.timeout)
    add("version", ver.code == 0 and bool(VERSIONISH.search(ver.out + ver.err)),
        f"exit {ver.code}; {excerpt(ver.out or ver.err)}")

    bare = run(cmd, env, args.timeout)
    add("bare.helpful", bare.code == 0 and bool(bare.out.strip()),
        f"exit {bare.code}; stdout {len(bare.out)} bytes; {excerpt(bare.out or bare.err)}")

    if args.command:
        sub_help = run(cmd + [args.command, "--help"], env, args.timeout)
        # The command's own help: not a crash, and not the root map reprinted.
        word = re.compile(rf"(?<![\w-]){re.escape(args.command)}(?![\w-])")
        first = next((ln for ln in sub_help.out.splitlines() if ln.strip()), "")
        usage = [ln for ln in sub_help.out.splitlines() if re.match(r"(?i)\s*usage:", ln)]
        own = (sub_help.out.strip() != help_text.strip()
               and any(word.search(ln) for ln in usage + [first]))
        add("help.subcommand", sub_help.code == 0 and own
            and TRACEBACK not in sub_help.out + sub_help.err,
            f"`{args.command} --help` -> exit {sub_help.code}; "
            + ("same text as root --help; " if sub_help.out.strip() == help_text.strip() else "")
            + excerpt(sub_help.err or sub_help.out))
        bad = typo_of(args.command)
        assert bad != args.command
        typo = run(cmd + [bad], env, args.timeout)
        said = (typo.out + typo.err).lower()
        add("typo.suggests", typo.code == 2 and "did you mean" in said and args.command in said,
            f"`{bad}` -> exit {typo.code}; {excerpt(typo.err or typo.out)}")
    else:
        add("help.subcommand", None, "pass --command <real subcommand> to check")
        add("typo.suggests", None, "pass --command <real subcommand> to check")

    unknown = run(cmd + ["--definitely-not-an-option"], env, args.timeout)
    add("errors.usage_exit", unknown.code == 2, f"unknown option -> exit {unknown.code}")
    add("errors.no_traceback", TRACEBACK not in unknown.out + unknown.err,
        "no traceback" if TRACEBACK not in unknown.out + unknown.err else "Python traceback on unknown option")

    if args.status:
        status = run(cmd + args.status.split(), env, args.timeout)
        lines = status.out.splitlines()
        add("status.runs", status.code == 0 and bool(status.out.strip()),
            f"exit {status.code}; {len(lines)} lines; {status.seconds:.2f}s; {excerpt(status.err or status.out)}")
        add("status.speed", status.seconds <= args.status_budget,
            f"{status.seconds:.2f}s (budget {args.status_budget:g}s)")
        raw = [ln for ln in lines if ln.lstrip().startswith(("{", "[", '"'))]
        add("status.human_text", status.code == 0 and not raw and len(lines) <= args.status_lines,
            f"{len(lines)} lines (max {args.status_lines}); {len(raw)} raw-JSON line(s)")
        has_next = bool(re.search(r"(?im)^\s*(next:|→|->)", status.out))
        add("status.next_step", has_next, "names a next command" if has_next else "no 'next:' line")
        add("status.no_color", not ANSI.search(status.out), "no ANSI in non-TTY status"
            if not ANSI.search(status.out) else "ANSI escapes in non-TTY status")
        sj = run(cmd + args.status.split() + ["--json"], env, args.timeout)
        try:
            doc = json.loads(sj.out)
            ok = sj.code == 0 and isinstance(doc, dict) and isinstance(doc.get("schema"), str)
            detail = f"schema={doc.get('schema')!r}" if isinstance(doc, dict) else f"top level is {type(doc).__name__}"
        except ValueError:
            ok, detail = False, f"exit {sj.code}; not JSON: {excerpt(sj.err or sj.out)}"
        add("status.json", ok, detail)
    else:
        for cid in ("status.runs", "status.speed", "status.human_text", "status.next_step",
                    "status.no_color", "status.json"):
            add(cid, None, "pass --status <subcommand> to check")
    return checks


def render(cmd: list[str], checks: list[Check]) -> str:
    mark = {"pass": "●", "fail": "✗", "skip": "○"}
    counts = {r: sum(c.result == r for c in checks) for r in ("pass", "fail", "skip")}
    out = [f"cli-contract  {' '.join(cmd)}",
           f"{counts['pass']} pass · {counts['fail']} fail · {counts['skip']} skip", ""]
    width = max(len(c.id) for c in checks)
    out += [f"  {mark[c.result]} {c.result:<4}  {c.id:<{width}}  {c.detail}" for c in checks]
    failed = [c.id for c in checks if c.result == "fail"]
    out += ["", "next: fix " + ", ".join(failed[:3]) + (" …" if len(failed) > 3 else "")
            + "  (contract: agentops/docs/contracts/operator-interface.md)" if failed
            else "next: nothing to fix"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="agentops cli-contract",
        description="Check one CLI against the operator interface contract.",
        epilog="Examples:" + __doc__.split("Examples:", 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--command", help="a real subcommand; its misspelling must get 'did you mean'")
    p.add_argument("--status", help="read-only status subcommand to check, e.g. 'status' or 'usage --context'")
    p.add_argument("--json", action="store_true", help=f"emit {SCHEMA} JSON")
    p.add_argument("--help-budget", type=float, default=0.5, help="seconds allowed for --help (default 0.5)")
    p.add_argument("--status-budget", type=float, default=1.0, help="seconds allowed for status (default 1)")
    p.add_argument("--status-lines", type=int, default=24, help="max status lines (default 24)")
    p.add_argument("--max-width", type=int, default=100, help="max help line width at COLUMNS=80 (default 100)")
    p.add_argument("--timeout", type=float, default=30.0, help="per-invocation timeout seconds (default 30)")
    p.add_argument("cmd", nargs=argparse.REMAINDER, help="the tool to probe, after --")
    args = p.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        p.error("name the tool to probe after --, e.g. agentops cli-contract -- lanectl")
    checks = evaluate(cmd, args)
    if args.json:
        print(json.dumps({"schema": SCHEMA, "command": cmd,
                          "failed": sum(c.result == "fail" for c in checks),
                          "checks": [asdict(c) for c in checks]}, indent=2))
    else:
        print(render(cmd, checks))
    return 1 if any(c.result == "fail" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
