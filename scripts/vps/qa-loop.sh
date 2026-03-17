#!/usr/bin/env bash
# scripts/vps/qa-loop.sh
# QA dispatch: run /qa skill after autopilot completion.
# Usage: qa-loop.sh <project_id> <project_dir> <spec_id>
#
# Phase transitions:
#   qa_pending → qa_running → idle       (PASS)
#   qa_pending → qa_running → qa_failed  (FAIL)
#
# QA always writes file reports. OpenClaw reviews those reports and,
# if needed, writes follow-up inbox items itself.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ID="${1:?Usage: qa-loop.sh <project_id> <project_dir> <spec_id>}"
PROJECT_DIR="${2:?Missing project_dir}"
SPEC_ID="${3:?Missing spec_id}"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a
[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

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
# Persist QA report and transition phase
# ---------------------------------------------------------------------------

TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
QA_DIR="${PROJECT_DIR}/ai/qa"
mkdir -p "$QA_DIR"
SPEC_REL="${SPEC_FILE#${PROJECT_DIR}/}"
REPORT_FILE="${QA_DIR}/${TIMESTAMP}-${SPEC_ID}.md"

STATUS_LABEL="passed"
NOTIFY_TEXT="QA PASSED for ${SPEC_ID}"
if (( QA_EXIT != 0 )); then
    STATUS_LABEL="failed"
    NOTIFY_TEXT="QA FAILED for ${SPEC_ID}. Report saved to ai/qa/."
fi

cat > "$REPORT_FILE" << EOF
# QA Report: ${SPEC_ID}

**Status:** ${STATUS_LABEL}
**Project:** ${PROJECT_ID}
**Spec:** ${SPEC_ID}
**SpecPath:** ${SPEC_REL}
**ExitCode:** ${QA_EXIT}
**Timestamp:** ${TIMESTAMP}

---

auto-generated from qa-loop.sh

## Raw Output

${QA_OUTPUT}
EOF

if (( QA_EXIT == 0 )); then
    "$DB_EXEC" "UPDATE project_state SET phase = 'idle', current_task = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "$NOTIFY_TEXT" 2>/dev/null || true
    echo "[qa] PASSED: ${SPEC_ID} report=${REPORT_FILE}"
else
    "$DB_EXEC" "UPDATE project_state SET phase = 'qa_failed', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "$NOTIFY_TEXT" 2>/dev/null || true
    echo "[qa] FAILED: ${SPEC_ID} (exit=${QA_EXIT}) report=${REPORT_FILE}"
fi
