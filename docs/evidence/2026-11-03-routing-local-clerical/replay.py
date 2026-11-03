#!/usr/bin/env python3
"""Replay the recorded synthetic prompts against the local worker-fast lane."""
import json
import sys
import urllib.request
from pathlib import Path

record = json.loads(Path(__file__).with_name("results.json").read_text())
for case in record["cases"]:
    body = {"model": "worker-fast", "messages": [{"role": "user", "content": case["prompt"]}],
            "temperature": 0, "max_tokens": 512}
    request = urllib.request.Request("http://127.0.0.1:8020/v1/chat/completions",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            content = json.load(response)["choices"][0]["message"].get("content") or ""
        try:
            passed = json.loads(content) == case["expected"]
        except (TypeError, ValueError):
            passed = False
        print(json.dumps({"case": case["case"], "pass": passed, "content": content}))
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"case": case["case"], "error_type": type(error).__name__}), file=sys.stderr)
