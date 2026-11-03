#!/usr/bin/env python3
"""Cross-check the recorded routing comparison against its JSON evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
readme = (ROOT / "README.md").read_text()
base = json.loads((ROOT / "results.json").read_text())
go = json.loads((ROOT / "opencode-go-results.json").read_text())
assert len(base["tasks"]) == 6
assert len(go["tasks"]) == 6

terra_pass = local_pass = 0
for task in base["tasks"]:
    oracle = task["oracle"]
    terra = task["arms"]["codex_terra_chatgpt"]
    local = task["arms"]["local_worker_fast"]
    assert terra["correct"] == (terra["result"] == oracle), task["id"]
    assert local["correct"] == (local["result"] == oracle), task["id"]
    terra_pass += terra["correct"]
    local_pass += local["correct"]
    row = next(line for line in readme.splitlines() if line.startswith(f"| {task['id']} "))
    assert f"`{oracle}`" in row, (task["id"], "oracle mismatch")
    assert f"`{terra['result']}`" in row, (task["id"], "Terra mismatch")
    if local["result"].startswith("[truncated"):
        assert "no final answer within cap" in row, (task["id"], "worker-fast truncation mismatch")
    else:
        assert f"`{local["result"]}`" in row, (task["id"], "worker-fast mismatch")

assert terra_pass == 6 and local_pass == 0
assert "Codex requested Terra route 6/6; worker-fast 0/6" in readme
assert "corrected exact-answer counts remain Terra 6/6 and worker-fast 0/6" in readme
assert base["source_audit_correction"]["task_id"] == "T1"

by_id = {task["id"]: task for task in base["tasks"]}
go_exact = 0
go_semantic = 0
for task in go["tasks"]:
    source = by_id[task["id"]]
    assert task["oracle"] == source["oracle"]
    assert task["exact_answer_match"] == (task["assistant_text"] == task["oracle"])
    assert task["format_compliant"] == task["exact_answer_match"]
    assert task["semantic_oracle_present"] == (task["oracle"] in task["assistant_text"])
    assert task["exit_code"] == 0
    assert not task["tool_events"]
    assert task["session_id"]
    go_exact += task["exact_answer_match"]
    go_semantic += task["semantic_oracle_present"]
assert go_exact == 5 and go_semantic == 6
assert go["scoring"]["exact_answer_match_count"] == go_exact
assert go["scoring"]["semantic_oracle_present_count"] == go_semantic
assert go["scoring"]["format_compliant_count"] == go_exact
assert "5/6 exact-answer/format matches and 6/6" in readme
for task in go["tasks"]:
    assert f"| {task['id']} |" in readme
assert go["provider_billing_status"].startswith("unknown")
assert "billing/account allocation was **not independently verified**" in readme
print(json.dumps({"valid": True, "terra_exact": terra_pass, "worker_fast_exact": local_pass,
                  "opencode_go_exact_format": go_exact, "opencode_go_oracle_present": go_semantic}, indent=2))
