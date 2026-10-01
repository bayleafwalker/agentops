#!/usr/bin/env python3
"""Check active workstation hook commands; repair canonical agentops aliases only."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import tomllib


def configs(workspace, home):
    bases = [workspace, home]
    bases += sorted(p for p in workspace.iterdir()
                    if p.is_dir() and not p.name.startswith((".", "_")))
    for base in bases:
        for relative in (".codex/hooks.json", ".codex/config.toml",
                         ".claude/settings.json", ".claude/settings.local.json"):
            path = base / relative
            if path.is_file():
                yield path


def check(workspace, home, canonical, apply=False):
    errors, repairs, count = [], [], 0
    for config in configs(workspace, home):
        try:
            raw = config.read_text()
            data = tomllib.loads(raw) if config.suffix == ".toml" else json.loads(raw)
            hooks = data.get("hooks", {})
            for event, groups in hooks.items():
                if event == "state":  # Codex trust records are not registrations.
                    continue
                for group in groups:
                    for hook in group.get("hooks", []):
                        if hook.get("type") != "command":
                            continue
                        count += 1
                        args = shlex.split(hook["command"])
                        executable = os.path.expanduser(args[0])
                        if "/" not in executable:
                            if not shutil.which(executable):
                                errors.append(f"{config}: {event}: missing executable {executable}")
                            continue
                        target = Path(executable)
                        if not target.is_absolute():
                            errors.append(f"{config}: {event}: relative command needs runtime cwd: {target}")
                            continue
                        source = canonical / target.name
                        # Repair only a shared hook alias under a discovered config's hooks/
                        # directory. Never alter config commands or custom hook bodies.
                        alias = target.parent == config.parent / "hooks" and source.is_file()
                        if not target.exists() and apply and alias:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            if target.is_symlink():
                                target.unlink()
                            target.symlink_to(source)
                            repairs.append(str(target))
                        if not target.is_file():
                            errors.append(f"{config}: {event}: missing hook {target}")
                            continue
                        if not os.access(target, os.X_OK):
                            errors.append(f"{config}: {event}: hook is not executable: {target}")
                        # Several guard hooks source this relative to the invoked alias.
                        if alias and target.read_bytes() == source.read_bytes() and "lib/emit-decision.sh" in source.read_text():
                            library = target.parent / "lib"
                            if apply and not library.exists() and (canonical / "lib").is_dir():
                                if library.is_symlink():
                                    library.unlink()
                                library.symlink_to(canonical / "lib", target_is_directory=True)
                                repairs.append(str(library))
                            if not (library / "emit-decision.sh").is_file():
                                errors.append(f"{config}: {event}: missing decision library: {library}")
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            errors.append(f"{config}: cannot inspect hook configuration: {exc}")
    return count, errors, repairs


def duplicate_cost_hooks(workspace, home, canonical, apply=False):
    """Remove only redundant project Stop snapshots already registered globally."""
    errors, repairs = [], []
    source = canonical / "log-session-cost.sh"
    if not source.is_file():
        return errors, repairs

    def is_cost(hook):
        if hook.get("type") != "command":
            return False
        args = shlex.split(hook.get("command", ""))
        return len(args) == 1 and Path(os.path.expanduser(args[0])).resolve() == source.resolve()

    for harness, filename in ((".codex", "hooks.json"), (".claude", "settings.json")):
        global_config = home / harness / filename
        if not global_config.is_file():
            continue
        global_hooks = json.loads(global_config.read_text()).get("hooks", {}).get("Stop", [])
        if not any(not group.get("matcher") and any(is_cost(h) for h in group.get("hooks", []))
                   for group in global_hooks):
            continue
        for config in configs(workspace, home):
            if config == global_config or config.parent.name != harness or config.suffix != ".json":
                continue
            data = json.loads(config.read_text())
            groups = data.get("hooks", {}).get("Stop", [])
            kept, removed = [], False
            for group in groups:
                if group.get("matcher"):
                    kept.append(group)
                    continue
                hooks = [h for h in group.get("hooks", []) if not is_cost(h)]
                removed |= len(hooks) != len(group.get("hooks", []))
                if hooks:
                    kept.append({**group, "hooks": hooks})
            if not removed:
                continue
            if apply:
                if kept:
                    data["hooks"]["Stop"] = kept
                else:
                    del data["hooks"]["Stop"]
                config.write_text(json.dumps(data, indent=2) + "\n")
                repairs.append(f"duplicate Stop registration in {config}")
            else:
                errors.append(f"{config}: duplicate global Stop cost hook")
    return errors, repairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/projects/dev"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--canonical", type=Path, default=Path(__file__).resolve().parents[1] / "hooks")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    count, errors, repairs = check(args.workspace, args.home, args.canonical, args.apply)
    if not errors:
        duplicate_errors, duplicate_repairs = duplicate_cost_hooks(
            args.workspace, args.home, args.canonical, args.apply)
        errors += duplicate_errors
        repairs += duplicate_repairs
    for path in repairs:
        print(f"RESTORED {path}")
    for error in errors:
        print(f"FAIL {error}")
    print(f"Checked {count} command registrations; {len(errors)} failures; {len(repairs)} repairs")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
