#!/usr/bin/env bash
# scripts/vps/qa-loop.sh
# QA dispatch: run /qa skill after autopilot completion.
# Usage: qa-loop.sh <project_id> <project_dir> <spec_id>
#
# Phase transitions:
#   qa_pending → qa_running → idle       (PASS)
#   qa_pending → qa_running → qa_failed  (FAIL)
#
# On FAIL: writes bug report to {project_dir}/ai/inbox/ so the
# orchestrator cycle picks it up and repeats autopilot.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ID="${1:?Usage: qa-loop.sh <project_id> <project_dir> <spec_id>}"
PROJECT_DIR="${2:?Missing project_dir}"
SPEC_ID="${3:?Missing spec_id}"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

DB_EXEC="${SCRIPT_DIR}/db_exec.sh"
CLAUDE_BIN="${CLAUDE_PATH:-claude}"
QA_TIMEOUT="${QA_TIMEOUT:-600}"

# ---------------------------------------------------------------------------
# Update phase: qa_pending → qa_running
# ---------------------------------------------------------------------------

"$DB_EXEC" "UPDATE project_state SET phase = 'qa_running', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"

# ---------------------------------------------------------------------------
# Find spec file in ai/features/
# ---------------------------------------------------------------------------

SPEC_FILE=$(find "${PROJECT_DIR}/ai/features/" -name "${SPEC_ID}*" -type f 2>/dev/null | head -1 || echo "")

if [[ -z "$SPEC_FILE" ]]; then
    echo "[qa] Spec file not found: ${SPEC_ID}" >&2
    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "QA skipped: spec file not found for ${SPEC_ID}" 2>/dev/null || true
    "$DB_EXEC" "UPDATE project_state SET phase = 'idle', current_task = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
    exit 1
fi

# ---------------------------------------------------------------------------
# Run QA via Claude CLI
# ---------------------------------------------------------------------------

export CLAUDE_PROJECT_DIR="$PROJECT_DIR"
export PROJECT_DIR="$PROJECT_DIR"

CONFIG_DIR="${PROJECT_DIR}/.claude-config"
mkdir -p "$CONFIG_DIR"
export CLAUDE_CODE_CONFIG_DIR="$CONFIG_DIR"

echo "[qa] Running QA for ${SPEC_ID} in ${PROJECT_DIR}"

set +e
QA_OUTPUT=$(timeout "$QA_TIMEOUT" "$CLAUDE_BIN" \
    --print \
    --output-format json \
    --max-turns 15 \
    -p "/qa ${SPEC_ID}" \
    2>&1)
QA_EXIT=$?
set -e

# ---------------------------------------------------------------------------
# Evaluate result and transition phase
# ---------------------------------------------------------------------------

if (( QA_EXIT == 0 )); then
    # QA passed — reset phase to idle
    "$DB_EXEC" "UPDATE project_state SET phase = 'idle', current_task = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "QA PASSED for ${SPEC_ID}" 2>/dev/null || true
    echo "[qa] PASSED: ${SPEC_ID}"
else
    # QA failed — write bug to inbox so the cycle repeats
    "$DB_EXEC" "UPDATE project_state SET phase = 'qa_failed', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"

    TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
    INBOX_DIR="${PROJECT_DIR}/ai/inbox"
    mkdir -p "$INBOX_DIR"

    # Write QA failure as new inbox item (orchestrator will pick it up next cycle)
    cat > "${INBOX_DIR}/${TIMESTAMP}-qa-fail.md" << EOF
# Idea: ${TIMESTAMP}
**Source:** qa-dispatch
**Route:** spark_bug
**Status:** new
---
QA failed for ${SPEC_ID}. Exit code: ${QA_EXIT}.

Please investigate and fix the issues found during QA.
Spec: ${SPEC_FILE}
EOF

    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "QA FAILED for ${SPEC_ID}. Bugs written to inbox." 2>/dev/null || true
    echo "[qa] FAILED: ${SPEC_ID} (exit=${QA_EXIT})"
fi
