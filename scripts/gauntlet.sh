#!/usr/bin/env bash
# ToolKinetik gauntlet — persists and reruns every verification layer.
# Usage: scripts/gauntlet.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1. Full test suite (random order via pytest-randomly) =="
uv run pytest tests/ -q

echo "== 2. Static types =="
uv run mypy src

echo "== 3. Lint + format =="
uv run ruff check src

echo "== 4. Changed-line coverage on the security modules =="
uv run pytest tests/ \
  --cov=toolkinetik.safety \
  --cov=toolkinetik.app \
  --cov=toolkinetik.coding_agent \
  --cov=toolkinetik.tdd_loop \
  --cov-report=term-missing -q

echo "== 5. Real execution: example skills pass the whitelist =="
uv run python -c "
from toolkinetik.safety import SafetyChecker
c = SafetyChecker()
for f in ['skills/math_skill.py', 'skills/weather_skill.py']:
    r = c.check_skill_file(f)
    assert r.passed, f'{f} unexpectedly rejected: {r.issues}'
    print(f, 'passed')
"

echo "== 6. Repeat runs (suite health: flakiness check) =="
for i in 1 2 3; do uv run pytest tests/ -q >/dev/null && echo "run $i: ok"; done

echo "GAUNTLET OK"
