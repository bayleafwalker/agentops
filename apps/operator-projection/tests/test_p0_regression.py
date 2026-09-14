"""Test 10: the packaged Replay reproduces P0 run 2 exactly (scores and move list)."""

import importlib.util
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parents[1] / "p0"
DEV = Path(os.environ.get("OPERATOR_PROJECTION_P0_DEV", "/projects/dev"))
REPOS = {name: DEV / name for name in ("appservice", "vuoro", "auditctl")}

pytestmark = pytest.mark.skipif(
    not all((path / ".git").exists() for path in REPOS.values()), reason="P0 regression needs local appservice/vuoro/auditctl clones"
)


def load_p0():
    spec = importlib.util.spec_from_file_location("p0_replay", HERE / "replay.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0_run_2_is_reproduced_exactly():
    p0 = load_p0()
    truth = yaml.safe_load((HERE / "ground-truth.yaml").read_text())
    recorded = json.loads((HERE / "out" / "moves.json").read_text())
    tags = p0.ImageTags(json.loads((HERE / "out" / "image-tags.json").read_text()))
    replay = p0.Replay(yaml.safe_load((HERE / "registry.yaml").read_text()), p0.LocalGit(REPOS), tags)
    result = replay.run(datetime.fromisoformat(truth["window"]["start"]), datetime.fromisoformat(truth["window"]["end"]))
    scored = json.loads(json.dumps(p0.score(truth, result["moves"]), default=list))
    assert [asdict(m) for m in result["moves"]] == recorded["moves"]
    assert scored == recorded["score"]
    assert (round(scored["recall"], 3), scored["precision"]) == (0.986, 1.0)
    assert scored["misses"] == [["credbroker.binding", "8feff32e", "REGRESSED"], ["credbroker.binding", "d2dbccac", "GAINED"]]
