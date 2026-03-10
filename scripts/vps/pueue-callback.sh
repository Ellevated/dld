#!/usr/bin/env bash
# scripts/vps/pueue-callback.sh
# Pueue completion callback: release compute slot + update DB + notify Telegram.
#
# Called by Pueue daemon via pueue.yml callback config:
#   callback: "/path/to/pueue-callback.sh {{ id }} '{{ label }}' '{{ group }}' '{{ result }}'"
#
# Pueue template variables (v4.0+):
#   {{ id }}     — numeric pueue task id
#   {{ label }}  — task label set at submission (format: "project_id:SPEC-ID")
#   {{ group }}  — pueue group (claude-runner or codex-runner)
#   {{ result }} — result string (Success, Failed, Killed, Errored(N), etc.)
#
# Design notes:
#   DA-8 / SA-2: slot is ALWAYS released, regardless of exit code or any error.
#   Script is fail-safe: every risky operation is wrapped with || true so
#   a DB error or missing notify.py never causes this callback to exit non-zero
#   (which would prevent Pueue from marking the task complete).
#   SQL injection fixed: all DB operations delegate to db.py (parameterized queries).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
PUEUE_ID="${1:?Missing pueue task id}"
LABEL="${2:-unknown}"
GROUP="${3:-unknown}"
RESULT="${4:-unknown}"

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

# ---------------------------------------------------------------------------
# Parse label: "project_id:SPEC-ID"
# ---------------------------------------------------------------------------
PROJECT_ID="${LABEL%%:*}"
TASK_LABEL="${LABEL#*:}"

# Guard: if label has no colon, both vars will equal LABEL (unknown split).
if [[ "$PROJECT_ID" == "$LABEL" ]]; then
    echo "[callback] WARN: label '${LABEL}' has no colon separator — project_id may be wrong" >&2
fi

# ---------------------------------------------------------------------------
# Map Pueue result to internal status + exit code
# ---------------------------------------------------------------------------
# Pueue result strings: "Success", "Failed(N)", "Killed", "Errored(N)", etc.
case "$RESULT" in
    *Success*) STATUS="done";   EXIT_CODE=0 ;;
    *)         STATUS="failed"; EXIT_CODE=1 ;;
esac

echo "[callback] pueue_id=${PUEUE_ID} project=${PROJECT_ID} task=${TASK_LABEL} result=${RESULT} status=${STATUS}"

# ---------------------------------------------------------------------------
# Step 1-3: Release slot + finish task + update project phase via db.py
# All SQL is parameterized inside db.py — no injection risk here.
# This block MUST execute even if notify fails, so errors are logged but not fatal.
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" ]]; then
    NEW_PHASE="qa_pending"
else
    NEW_PHASE="failed"
fi

python3 "${SCRIPT_DIR}/db.py" callback \
    "${PUEUE_ID}" "${STATUS}" "${EXIT_CODE}" "${PROJECT_ID}" "${NEW_PHASE}" || {
    echo "[callback] WARN: db.py callback failed for pueue_id=${PUEUE_ID}" >&2
}

echo "[callback] db updated pueue_id=${PUEUE_ID} phase=${NEW_PHASE}"

# ---------------------------------------------------------------------------
# Step 4: Collect a brief log summary to include in Telegram message
# ---------------------------------------------------------------------------
SUMMARY=""
if command -v pueue &>/dev/null; then
    SUMMARY=$(pueue log "${PUEUE_ID}" --lines 5 2>/dev/null | tail -5 || true)
fi

# ---------------------------------------------------------------------------
# Step 5: Build Telegram message
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" ]]; then
    MSG="Task ${TASK_LABEL} completed successfully for ${PROJECT_ID} (pueue#${PUEUE_ID})."
else
    MSG="Task ${TASK_LABEL} FAILED for ${PROJECT_ID} (pueue#${PUEUE_ID}). Result: ${RESULT}. Check: pueue log ${PUEUE_ID}"
fi

if [[ -n "$SUMMARY" ]]; then
    MSG="${MSG}

Last output:
${SUMMARY}"
fi

# ---------------------------------------------------------------------------
# Step 6: Send Telegram notification via notify.py (fail-safe)
# notify.py handles topic routing by project_id.
# We suppress all errors — a broken notifier must never prevent slot release.
# ---------------------------------------------------------------------------
NOTIFY_PY="${SCRIPT_DIR}/notify.py"
if [[ -f "$NOTIFY_PY" ]]; then
    python3 "$NOTIFY_PY" "$PROJECT_ID" "$MSG" 2>/dev/null || {
        echo "[callback] WARN: notify.py failed for project=${PROJECT_ID}" >&2
    }
else
    echo "[callback] WARN: notify.py not found at ${NOTIFY_PY} — skipping Telegram notification" >&2
fi

echo "[callback] done pueue_id=${PUEUE_ID} project=${PROJECT_ID} task=${TASK_LABEL} status=${STATUS}"
