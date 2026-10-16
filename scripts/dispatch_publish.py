#!/usr/bin/env python3
"""Check and publish a dispatch tip in one native process (#2597).

Agent-relayed JSON never authorizes a Git or PR effect. This process reads Git,
enforces the publication rules, performs the effect and checks the remote.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from dispatch_publish_check import confirm, git, is_ancestor, preflight, remote_ref, resolve


def github_identity(url: str) -> str | None:
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?", url)
    return match.group(1).lower() if match else None


def publish(repo: str, tip: str, run_branch: str, expected: list[str], item_ids: list[str],
            target: dict | None = None) -> dict:
    """Publish a verified tip.

    Ungated (target None): push to main when no protected path is touched, else a
    dispatch/publish-<tip> PR. Gated (target = the attempt target execution_authority
    allowed): never main -- push exactly target["branch"], and open the PR only when
    the attempt authorized open_pull_request.
    """
    report = {"published": False, "action": "publish-refused"}
    if not re.fullmatch(r"dispatch/run-[A-Za-z0-9]{6,}", run_branch):
        raise ValueError("invalid run branch")
    if git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() != run_branch:
        raise ValueError("publication must use the named run branch")
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        location = git(repo, "rev-parse", "--git-path", marker).stdout.strip()
        if (Path(repo) / location).exists():
            raise ValueError("Git operation in progress")
    full = resolve(repo, tip)
    if not full or not is_ancestor(repo, full, "HEAD"):
        raise ValueError("TIP must be an ancestor of the run branch HEAD")
    fetch_url = git(repo, "remote", "get-url", "origin").stdout.strip()
    push_urls = git(repo, "remote", "get-url", "--push", "--all", "origin").stdout.splitlines()
    if len(push_urls) != 1:
        raise ValueError("publication requires exactly one push destination")
    push_url = push_urls[0]
    for url in (fetch_url, push_url):
        if re.search(r"(?:/|:)appservice(?:\.git)?/?$", url, re.I):
            raise ValueError("origin is appservice: pushing its main deploys it")
    identity = github_identity(fetch_url)
    if fetch_url != push_url and (not identity or github_identity(push_url) != identity):
        raise ValueError("fetch and push remotes identify different repositories")
    facts = preflight(repo, full, expected)
    main_sha, error = remote_ref(repo, "refs/heads/main")
    if error or not main_sha or git(repo, "rev-parse", "origin/main").stdout.strip() != main_sha:
        raise ValueError(error or "remote main missing or changed after fetch")
    if facts["unexpected"] or facts["missing_expected"]:
        raise ValueError("unaccounted or missing commits: " + json.dumps({k: facts[k] for k in ("unexpected", "missing_expected")}))
    for line in git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/dispatch/verified/").stdout.splitlines():
        name, _, value = line.partition(" ")
        if name not in facts["invalid_refs"] and is_ancestor(repo, value, "origin/main"):
            # Compare the old value so a concurrent writer's new evidence is preserved.
            git(repo, "update-ref", "-d", name, value)
    report.update(head_sha=full, origin_url=fetch_url)
    if not facts["range"]:
        return {**report, "published": True, "action": "already-on-origin"}
    if facts["net_zero"] and not facts["expected"]:
        return {**report, "action": "net-zero", "error": "no expected commit outside origin/main; no publication needed"}
    protected = facts["protected_hits"]
    if target is not None and target.get("commit_sha") != full:
        raise ValueError("tip differs from the attempt's authorized target commit")
    if not protected and target is None:
        pushed = git(repo, "push", "origin", f"{full}:refs/heads/main", check=False)
        if pushed.returncode == 0:
            checked = confirm(repo, full, "pushed")
            if not checked["confirmed"]:
                raise ValueError(checked.get("error", "push not confirmed on origin"))
            return {**report, "published": True, "action": "pushed"}
        refusal = pushed.stderr + pushed.stdout
        if not re.search(r"GH006|GH013|protected branch|rejected|fetch first|non-fast-forward", refusal, re.I):
            raise ValueError("main push failed: " + refusal.strip())
    branch_only = target is not None and target.get("operation") == "push_branch"
    if not identity and not branch_only:
        raise ValueError("PR hand-back requires a GitHub origin")
    branch = target["branch"] if target is not None else facts["publish_branch"]
    base = (target.get("base_branch") or "main") if target is not None else "main"
    old_sha, error = remote_ref(repo, f"refs/heads/{branch}")
    if error or (old_sha and old_sha != full):
        raise ValueError(error or "publication branch already has another tip")
    if not old_sha:
        git(repo, "push", "origin", f"{full}:refs/heads/{branch}")
    if target is not None and target.get("operation") == "push_branch":
        checked = confirm(repo, full, "branch-pushed", branch=branch)
        if not checked["confirmed"]:
            raise ValueError(checked.get("error", "branch not confirmed"))
        return {**report, "published": True, "action": "branch-pushed", "branch": branch}

    def gh(*args: str) -> str:
        return subprocess.run(["gh", *args, "--repo", identity], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    opened = json.loads(gh("pr", "list", "--state", "open", "--base", base, "--json", "headRefName,headRefOid,url"))
    contained = [p["url"] for p in opened if p["headRefName"].startswith("dispatch/publish-")
                 and p["headRefName"] != branch and resolve(repo, p["headRefOid"])
                 and is_ancestor(repo, p["headRefOid"], full)]
    urls = [p["url"] for p in opened if p["headRefName"] == branch and p["headRefOid"] == full]
    if urls:
        url = urls[0]
    else:
        body = "Expected commits:\n" + "\n".join(expected) + "\n\nItems: " + ", ".join(item_ids)
        body += "\n\nContained earlier PRs:\n" + "\n".join(contained)
        body += "\n\nMerge with a merge commit to preserve the verified SHAs."
        if protected:
            body += "\n\nIndependent hand-pass review required for protected paths:\n" + "\n".join(protected)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as output:
            output.write(body)
            output.flush()
            url = gh("pr", "create", "--base", base, "--head", branch, "--title", f"Dispatch verified batch {full[:12]}", "--body-file", output.name)
    if not re.fullmatch(r"https://github\.com/" + re.escape(identity) + r"/pull/[0-9]+", url, re.I):
        raise ValueError("PR URL does not match origin")
    action = "needs-hand-pass-pr" if protected else "pr-opened"
    checked = confirm(repo, full, action, branch=branch if target is not None else None)
    if not checked["confirmed"]:
        raise ValueError(checked.get("error", "PR branch not confirmed"))
    return {**report, "action": action, "pr_url": url, "error": ", ".join(protected)}


def authority_gate(args: argparse.Namespace) -> tuple[dict | None, dict | None]:
    """Run the effect-boundary check: (refusal report, None) or (None, the allowed attempt target)."""
    import execution_authority as authority  # noqa: PLC0415 - only needed when gated
    from validate_vuoro_profiles import ProfileError, validate_environment  # noqa: PLC0415

    try:
        record = validate_environment(args.authority_environment)
        operation = record["authority"]["scoped_execution"]["publication_operation"]
    except (ProfileError, KeyError, TypeError) as error:
        return {"published": False, "action": "publish-refused", "error": f"authority: environment-invalid: {error}"}, None
    decision = authority.authorize(args.authority_environment, authority.ExecutionRequest(
        operation=operation, repo_id=args.authority_repo, run_id=args.run_id, grant_id=args.grant_id,
        attempt_id=args.attempt_id, commit_sha=resolve(args.repo, args.tip)), args.profile)
    if decision.allowed and decision.target:
        return None, decision.target
    if decision.allowed:  # defensive: an allowed publication always carries its target
        decision = authority.Decision(False, "internal-error", "allowed publication without a target", decision.tier)
    return {"published": False, "action": "publish-refused", "authority": decision.as_dict(),
            "error": f"authority: {decision.code}: {decision.reason}"}, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tip", required=True)
    parser.add_argument("--run-branch", required=True)
    parser.add_argument("--expected", action="append", default=[])
    parser.add_argument("--item-id", action="append", default=[])
    gate = parser.add_argument_group(
        "effect-boundary authority (docs/architecture/bounded-execution-environment.md)",
        "With --authority-environment, execution_authority.decide() must allow the record's "
        "publication operation for this exact commit before any effect.")
    gate.add_argument("--authority-environment", type=Path)
    gate.add_argument("--authority-repo", default="agentops")
    gate.add_argument("--run-id")
    gate.add_argument("--grant-id")
    gate.add_argument("--attempt-id")
    gate.add_argument("--profile", type=Path, help="vuoro client profile for the served owner reads")
    args = parser.parse_args()
    try:
        target = None
        if args.authority_environment:
            refusal, target = authority_gate(args)
            if refusal:
                print(json.dumps(refusal))
                return 1
        report = publish(args.repo, args.tip, args.run_branch, args.expected, args.item_id, target)
    except (ValueError, OSError, subprocess.CalledProcessError, SystemExit) as error:
        report = {"published": False, "action": "publish-refused", "error": str(error)}
    print(json.dumps(report))
    return 0 if report["action"] != "publish-refused" else 1


if __name__ == "__main__":
    raise SystemExit(main())
