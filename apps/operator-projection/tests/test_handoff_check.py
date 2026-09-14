"""checks/handoff_non_perturbation.py over a fake authority with synthetic events. Never run against the live authority here."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fakes import FakeAuthorityClient
from operator_projection.sources import Authority, ReadRefused

CHECK = Path(__file__).resolve().parents[1] / "checks" / "handoff_non_perturbation.py"
spec = importlib.util.spec_from_file_location("handoff_non_perturbation", CHECK)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def ledger(perturbing: bool):
    stored = [{"id": n, "type": "synthetic"} for n in range(3)]

    def handoff(args):
        if perturbing:
            stored.append({"id": len(stored), "type": "handoff-read"})
        return {"last_checkpoint": None}

    return {"work.read.events": lambda args: {"repo_id": "repo-alpha", "events": stored[args["after_offset"]:][: args["limit"]]},
            "work.read.handoff": handoff}


def authority(perturbing: bool, allow=module.ALLOW):
    client = FakeAuthorityClient(results=ledger(perturbing))
    return client, Authority(client, lambda: True, allow=allow)


def test_an_unperturbed_ledger_passes_using_only_read_operations():
    client, auth = authority(perturbing=False)
    result = module.check(auth, 11, "repo-alpha")
    assert result["unchanged"] and result["events_before"] == result["events_after"] == 3
    assert [op for op, _ in client.invoked] == ["work.read.events", "work.read.handoff", "work.read.events"]
    assert result["catalog_revision"] == "synthetic-catalog-0001" and result["repo_id"] == "repo-alpha"
    assert client.repo_ids == ["repo-alpha"] * 3


def test_an_appended_event_fails_and_is_printed():
    _, auth = authority(perturbing=True)
    result = module.check(auth, 11, "repo-alpha")
    assert not result["unchanged"] and result["appended"] == [{"id": 3, "type": "handoff-read"}]


def test_the_generator_allowlist_alone_refuses_the_events_read():
    client, auth = authority(perturbing=False, allow=module.READ_OPS)
    with pytest.raises(ReadRefused):
        module.check(auth, 11, "repo-alpha")
    assert client.invoked == []


def test_without_the_identity_the_check_is_not_runnable(tmp_path, capsys):
    pytest.importorskip("vuoro_client")
    profile = tmp_path / "profile.yaml"
    profile.write_text(f"authority_url: https://authority.invalid\nrequired_authorities: [work:read]\ncredential_ref: file:{tmp_path / 'absent'}\n")
    assert module.main(["--sprint-id", "11", "--repo-id", "repo-alpha", "--profile", str(profile)]) == 2
    assert "credential is absent" in capsys.readouterr().err


def test_repo_id_is_required(capsys):
    with pytest.raises(SystemExit) as exited:
        module.main(["--sprint-id", "11"])
    assert exited.value.code == 2 and "--repo-id" in capsys.readouterr().err


def test_runs_when_piped_over_stdin_with_file_set(tmp_path):
    """The pod runs it as python3 -c "...exec(compile(stdin, '/app/checks/handoff_non_perturbation.py', 'exec'))"."""
    runner = "import sys; __file__ = sys.argv.pop(1); exec(compile(sys.stdin.read(), __file__, 'exec'))"
    env = {k: v for k, v in os.environ.items() if k != "OPERATOR_PROJECTION_PROFILE"}
    done = subprocess.run([sys.executable, "-c", runner, str(CHECK), "--sprint-id", "11", "--repo-id", "repo-alpha", "--profile", str(tmp_path / "absent.yaml")],
                          input=CHECK.read_text(), capture_output=True, text=True, cwd=tmp_path, env=env, timeout=60)
    assert done.returncode == 2 and "not runnable: set OPERATOR_PROJECTION_PROFILE" in done.stderr, done.stderr
