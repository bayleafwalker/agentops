"""checks/handoff_non_perturbation.py over a fake authority with synthetic events. Never run against the live authority here."""

import importlib.util
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
    result = module.check(auth, 11)
    assert result["unchanged"] and result["events_before"] == result["events_after"] == 3
    assert [op for op, _ in client.invoked] == ["work.read.events", "work.read.handoff", "work.read.events"]
    assert result["catalog_revision"] == "synthetic-catalog-0001"


def test_an_appended_event_fails_and_is_printed():
    _, auth = authority(perturbing=True)
    result = module.check(auth, 11)
    assert not result["unchanged"] and result["appended"] == [{"id": 3, "type": "handoff-read"}]


def test_the_generator_allowlist_alone_refuses_the_events_read():
    client, auth = authority(perturbing=False, allow=module.READ_OPS)
    with pytest.raises(ReadRefused):
        module.check(auth, 11)
    assert client.invoked == []


def test_without_the_identity_the_check_is_not_runnable(tmp_path, capsys):
    pytest.importorskip("vuoro_client")
    profile = tmp_path / "profile.yaml"
    profile.write_text(f"authority_url: https://authority.invalid\nrequired_authorities: [work:read]\ncredential_ref: file:{tmp_path / 'absent'}\n")
    assert module.main(["--sprint-id", "11", "--profile", str(profile)]) == 2
    assert "credential is absent" in capsys.readouterr().err
