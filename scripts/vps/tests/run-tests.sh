#!/usr/bin/env bash
# scripts/vps/tests/run-tests.sh
# Run all orchestrator tests: pytest (Python) + bats (bash).
# Usage: bash scripts/vps/tests/run-tests.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=== Orchestrator Test Suite ==="
echo ""

# --- Python tests ---
echo "--- pytest: db.py + notify.py + approve_handler.py ---"
cd "$PROJECT_ROOT"
python -m pytest scripts/vps/tests/ -v --tb=short "$@"
echo ""

# --- Bash tests ---
if command -v bats &>/dev/null || command -v npx &>/dev/null; then
    echo "--- bats: inbox-processor.sh ---"
    if command -v bats &>/dev/null; then
        bats scripts/vps/tests/bash/
    else
        npx bats scripts/vps/tests/bash/
    fi
else
    echo "WARN: bats-core not installed, skipping bash tests"
    echo "Install: npm install -g bats"
fi

echo ""
echo "=== All tests complete ==="
