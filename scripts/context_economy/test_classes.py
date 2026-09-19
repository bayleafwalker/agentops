"""Tests for the Bash command classifier (relocated from outctl@94840d7)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "classes.py"

_spec = importlib.util.spec_from_file_location("context_economy_classes", SCRIPT)
classes_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(classes_mod)


def test_file_read_commands_classify_as_file_read():
    for cmd in ["cat foo.py", "sed -n '1,20p' bar.txt", "head -50 baz.log", "tail -f x.log"]:
        assert classes_mod.cls(cmd) == "file-read"


def test_git_commands_classify_as_git():
    for cmd in ["git status", "gh pr list", "fj repo list"]:
        assert classes_mod.cls(cmd) == "git"


def test_infra_commands_classify_before_search():
    # kubectl matches k8s/flux/infra even though it could loosely resemble other classes
    assert classes_mod.cls("kubectl get pods") == "k8s/flux/infra"


def test_search_list_commands():
    for cmd in ["grep -rn foo .", "rg foo", "find . -name '*.py'", "ls -la"]:
        assert classes_mod.cls(cmd) == "search/list"


def test_unrecognized_command_is_other():
    assert classes_mod.cls("echo hello") == "other"


def test_first_matching_class_wins():
    # "git log" also could loosely match nothing else, but ensure git wins over search
    # for a command that contains both a git subcommand and a search-like word.
    assert classes_mod.cls("git grep foo") == "git"


def test_bound_regex_detects_pipes_and_flags():
    assert classes_mod.BOUND.search("find . -name '*.py' | head -20")
    assert classes_mod.BOUND.search("kubectl get pods -o wide --stat")
    assert not classes_mod.BOUND.search("cat huge_file.txt")
