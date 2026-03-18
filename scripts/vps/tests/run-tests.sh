#!/usr/bin/env bash
# scripts/vps/tests/run-tests.sh
# Run all orchestrator tests (Python only — bash scripts replaced by Python in ARCH-161).
# Usage: bash scripts/vps/tests/run-tests.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=== Orchestrator Test Suite ==="
echo ""

# --- Python tests ---
echo "--- pytest: db.py, orchestrator.py, callback.py, event_writer.py ---"
cd "$PROJECT_ROOT"
python -m pytest scripts/vps/tests/ -v --tb=short "$@"

echo ""
echo "=== All tests complete ==="
