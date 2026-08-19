#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '==> Compiling reference package\n'
python3 -m compileall -q "$ROOT/reference/volatile_context" "$ROOT/reference/tests"

printf '==> Running reference tests\n'
(
  cd "$ROOT/reference"
  python3 -m unittest discover -s tests -v
)

printf '==> Parsing JSON artifacts and checking budgets\n'
python3 - "$ROOT" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
for path in sorted(root.rglob("*.json")):
    json.loads(path.read_text(encoding="utf-8"))

projection = (root / "examples/projection.json").read_text(encoding="utf-8").strip()
if len(projection.encode("utf-8")) > 7500:
    raise SystemExit("example projection exceeds 7500-byte hard budget")
print(f"parsed {len(list(root.rglob('*.json')))} JSON files")
PY

printf '==> Checking for obvious credential material\n'
if grep -RInE --exclude='validate-bundle.sh' \
  '(AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,})' \
  "$ROOT"; then
  echo 'credential-like material found' >&2
  exit 1
fi

printf '==> Bundle validation passed\n'
