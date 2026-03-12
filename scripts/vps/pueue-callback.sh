#!/usr/bin/env bash
# scripts/vps/pueue-callback.sh
# Pueue completion callback: release compute slot + update DB + notify Telegram.
#
# Called by Pueue daemon via pueue.yml callback config:
#   callback: "/path/to/pueue-callback.sh {{ id }} '{{ group }}' '{{ result }}'"
#
# Pueue template variables (v4.0+):
#   {{ id }}     — numeric pueue task id
#   {{ group }}  — pueue group (claude-runner, codex-runner, gemini-runner)
#   {{ result }} — result string (Success, Failed, Killed, Errored(N), etc.)
#
# NOTE: {{ label }} is NOT available in Pueue v4.0.4 callback templates.
# Label is resolved at runtime via `pueue status --json`.
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
GROUP="${2:-unknown}"
RESULT="${3:-unknown}"

# Resolve label from pueue status (not available as callback template var in v4.0.4)
LABEL=$(pueue status --json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
task = data.get('tasks', {}).get('$PUEUE_ID', {})
print(task.get('label', 'unknown'))
" 2>/dev/null || echo "unknown")

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a
[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

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
# Step 4: Extract structured data from agent JSON output (claude-runner.py)
# ---------------------------------------------------------------------------
PREVIEW=""
SKILL=""
if command -v pueue &>/dev/null; then
    # claude-runner.py prints JSON with: skill, result_preview, exit_code, etc.
    # JSON is the last line of stdout; --lines 10 gives enough margin
    AGENT_JSON=$(pueue log "${PUEUE_ID}" --lines 10 2>/dev/null | \
        grep -E '^\{.*"skill"' | tail -1 || true)
    if [[ -n "$AGENT_JSON" ]]; then
        PREVIEW=$(echo "$AGENT_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('result_preview', '')[:500])
" 2>/dev/null || true)
        SKILL=$(echo "$AGENT_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('skill', ''))
" 2>/dev/null || true)
    fi
    # Fallback: grep for result_preview if JSON parse failed
    if [[ -z "$PREVIEW" ]]; then
        PREVIEW=$(pueue log "${PUEUE_ID}" --lines 3 2>/dev/null | \
            grep -o '"result_preview": *"[^"]*"' | head -1 | \
            sed 's/"result_preview": *"//;s/"$//' | head -c 300 || true)
    fi
fi

# ---------------------------------------------------------------------------
# Step 5: Build Telegram message
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" ]]; then
    MSG="✅ *${PROJECT_ID}*: ${TASK_LABEL} завершено"
else
    MSG="❌ *${PROJECT_ID}*: ${TASK_LABEL} — ошибка (${RESULT})"
fi

if [[ -n "$PREVIEW" ]]; then
    MSG="${MSG}
${PREVIEW}"
fi

# ---------------------------------------------------------------------------
# Step 5.5: Spark approval notification with result_preview
# When spark completes successfully, send approval buttons with the summary
# so the user sees WHAT spark plans to do, not dry spec headers.
# ---------------------------------------------------------------------------
NOTIFY_PY="${SCRIPT_DIR}/notify.py"
SENT_APPROVAL=false

if [[ "$STATUS" == "done" && "$SKILL" == "spark" && -f "$NOTIFY_PY" ]]; then
    # Resolve project path for spec file lookup
    SPARK_PROJECT_PATH=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${PROJECT_ID}')
print(state['path'] if state else '')
" 2>/dev/null || true)

    if [[ -n "$SPARK_PROJECT_PATH" ]]; then
        # Find newest draft spec in backlog
        BACKLOG="${SPARK_PROJECT_PATH}/ai/backlog.md"
        SPEC_ID=""
        SPEC_TITLE=""
        TASKS_COUNT=0

        if [[ -f "$BACKLOG" ]]; then
            # Get the last (newest) draft spec ID
            SPEC_ID=$(grep -E '^\|\s*(TECH|FTR|BUG|ARCH)-[0-9]+\s*\|.*\|\s*draft\s*\|' "$BACKLOG" 2>/dev/null | \
                      grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | tail -1 || true)
        fi

        if [[ -n "$SPEC_ID" ]]; then
            # Find spec file for title and task count
            SPEC_FILE=$(find "${SPARK_PROJECT_PATH}/ai/features/" -name "${SPEC_ID}*" -type f 2>/dev/null | head -1 || true)
            if [[ -n "$SPEC_FILE" ]]; then
                SPEC_TITLE=$(grep -m1 '^# ' "$SPEC_FILE" 2>/dev/null | sed 's/^# //' | head -c 100 || true)
                TASKS_COUNT=$(grep -c -E '^#{2,3} Task' "$SPEC_FILE" 2>/dev/null || true)
                TASKS_COUNT=$(( TASKS_COUNT + 0 ))
            fi
            SPEC_TITLE="${SPEC_TITLE:-$SPEC_ID}"

            # Use result_preview as the summary (what spark plans to do)
            SUMMARY="${PREVIEW:-—}"

            echo "[callback] Sending spark approval: project=${PROJECT_ID} spec=${SPEC_ID}"
            python3 "$NOTIFY_PY" --spec-approval \
                "$PROJECT_ID" "$SPEC_ID" "$SPEC_TITLE" "$SUMMARY" "$TASKS_COUNT" 2>/dev/null && {
                SENT_APPROVAL=true
                # Mark as notified so scan_drafts won't re-notify
                echo "$SPEC_ID" >> "${SCRIPT_DIR}/.notified-drafts-${PROJECT_ID}"
                echo "[callback] Spark approval sent: ${PROJECT_ID}:${SPEC_ID}"
            } || {
                echo "[callback] WARN: spark approval notification failed" >&2
            }
        else
            echo "[callback] WARN: no draft spec found in backlog for spark result" >&2
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Step 6: Send Telegram completion notification (fail-safe)
# Skip if we already sent approval notification (avoid double message).
# notify.py handles topic routing by project_id.
# ---------------------------------------------------------------------------
if [[ "$SENT_APPROVAL" == "false" && -f "$NOTIFY_PY" ]]; then
    python3 "$NOTIFY_PY" "$PROJECT_ID" "$MSG" 2>/dev/null || {
        echo "[callback] WARN: notify.py failed for project=${PROJECT_ID}" >&2
    }
elif [[ ! -f "$NOTIFY_PY" ]]; then
    echo "[callback] WARN: notify.py not found at ${NOTIFY_PY} — skipping Telegram notification" >&2
fi

# ---------------------------------------------------------------------------
# Step 6.5: Council/Architect → Inbox feedback loop
# When council or architect completes, write result_preview back to inbox
# with route=spark so the next orchestrator cycle creates a spec from it.
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" && ( "$SKILL" == "council" || "$SKILL" == "architect" ) && -n "$PREVIEW" ]]; then
    FEEDBACK_PROJECT_PATH=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${PROJECT_ID}')
print(state['path'] if state else '')
" 2>/dev/null || true)

    if [[ -n "$FEEDBACK_PROJECT_PATH" ]]; then
        INBOX_DIR="${FEEDBACK_PROJECT_PATH}/ai/inbox"
        mkdir -p "$INBOX_DIR"
        TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
        INBOX_FILE="${INBOX_DIR}/${TIMESTAMP}-${SKILL}-result.md"

        cat > "$INBOX_FILE" <<INBOX_EOF
# ${SKILL^} result: ${TASK_LABEL}
**Source:** ${SKILL}
**Route:** spark
**Context:** Результат ${SKILL} по запросу ${TASK_LABEL}
**Status:** new
---
${PREVIEW}
INBOX_EOF

        echo "[callback] ${SKILL} result written to inbox: ${INBOX_FILE}"

        # Notify user that council result is queued for spark
        if [[ -f "$NOTIFY_PY" ]]; then
            python3 "$NOTIFY_PY" "$PROJECT_ID" \
                "🧠 *${PROJECT_ID}*: ${SKILL} завершён. Результат отправлен в Spark." 2>/dev/null || true
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Step 7: Post-autopilot — dispatch QA + Reflect (FTR-149)
# Only after successful autopilot completion.
# Non-blocking: submitted to pueue, orchestrator tracks via phase.
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" && ( "$SKILL" == "autopilot" || "$SKILL" == "spark" || "$SKILL" == "spark_bug" ) ]]; then
    # Resolve project path + provider from DB
    read -r PROJECT_PATH PROJECT_PROVIDER <<< "$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${PROJECT_ID}')
if state:
    print(state['path'], state.get('provider', 'claude'))
else:
    print('', 'claude')
" 2>/dev/null || echo '' 'claude')"
    PROJECT_PROVIDER="${PROJECT_PROVIDER:-claude}"
    RUNNER_GROUP="${PROJECT_PROVIDER}-runner"

    if [[ -n "$PROJECT_PATH" ]]; then
        # Dispatch QA
        pueue add --group "$RUNNER_GROUP" --label "${PROJECT_ID}:qa-${TASK_LABEL}" \
            -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" \
            "/qa Проверь изменения после ${TASK_LABEL}" 2>/dev/null && {
            echo "[callback] QA dispatched for ${PROJECT_ID}:${TASK_LABEL} (group=${RUNNER_GROUP})"
        } || {
            echo "[callback] WARN: QA dispatch failed for ${PROJECT_ID}" >&2
        }

        # Dispatch Reflect
        pueue add --group "$RUNNER_GROUP" --label "${PROJECT_ID}:reflect-${TASK_LABEL}" \
            -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_PATH" "$PROJECT_PROVIDER" "reflect" \
            "/reflect" 2>/dev/null && {
            echo "[callback] Reflect dispatched for ${PROJECT_ID}:${TASK_LABEL} (group=${RUNNER_GROUP})"
        } || {
            echo "[callback] WARN: Reflect dispatch failed for ${PROJECT_ID}" >&2
        }
    fi
fi

echo "[callback] done pueue_id=${PUEUE_ID} project=${PROJECT_ID} task=${TASK_LABEL} status=${STATUS}"
