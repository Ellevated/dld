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
# Debug trace — every callback invocation is logged
# ---------------------------------------------------------------------------
CALLBACK_LOG="${SCRIPT_DIR}/callback-debug.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] callback invoked: args=[$*]" >> "$CALLBACK_LOG"

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
text = data.get('result_preview', '')[:500]
# Strip surrogates that break Telegram API (UnicodeEncodeError)
text = text.encode('utf-8', errors='replace').decode('utf-8')
print(text)
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
# Step 5: Build Telegram message (human-readable)
# ---------------------------------------------------------------------------
# Skill labels for human-readable notifications
declare -A SKILL_LABELS=(
    [spark]="Спека"
    [autopilot]="Автопилот"
    [council]="Консилиум"
    [architect]="Архитектор"
    [reflect]="Рефлексия"
    [qa]="QA проверка"
    [bughunt]="Охота на баги"
    [scout]="Разведка"
)
SKILL_LABEL="${SKILL_LABELS[$SKILL]:-$SKILL}"

# Clean preview: strip markdown headers, bold markers, tables for Telegram
CLEAN_PREVIEW=""
if [[ -n "$PREVIEW" ]]; then
    CLEAN_PREVIEW=$(echo "$PREVIEW" | \
        sed 's/^##* //g' | \
        sed 's/\*\*//g' | \
        sed '/^|[-=]/d' | \
        sed '/^```/d' | \
        head -c 300)
fi

if [[ "$STATUS" == "done" ]]; then
    MSG="✅ *${PROJECT_ID}*: ${SKILL_LABEL} завершена"
else
    MSG="❌ *${PROJECT_ID}*: ${SKILL_LABEL} — ошибка"
fi

if [[ -n "$CLEAN_PREVIEW" ]]; then
    MSG="${MSG}
${CLEAN_PREVIEW}"
fi

# Final surrogate cleanup — Telegram API rejects surrogates with UnicodeEncodeError
MSG=$(python3 -c "
import sys
text = sys.stdin.read()
print(text.encode('utf-8', errors='replace').decode('utf-8'), end='')
" <<< "$MSG" 2>/dev/null || echo "$MSG")

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

            # Use result_preview as the summary; fallback to spec Problem/Why section
            SUMMARY="$PREVIEW"
            if [[ -z "$SUMMARY" && -n "$SPEC_FILE" ]]; then
                SUMMARY=$(grep -A2 -E '^## (Why|Symptom|Problem|Root Cause|Что делаем)' "$SPEC_FILE" 2>/dev/null | \
                    grep -v '^##' | head -3 | tr '\n' ' ' | head -c 300 || true)
            fi
            SUMMARY="${SUMMARY:-—}"
            # Strip surrogates from summary
            SUMMARY=$(python3 -c "import sys; print(sys.stdin.read().encode('utf-8',errors='replace').decode('utf-8'),end='')" <<< "$SUMMARY" 2>/dev/null || echo "$SUMMARY")

            # Mark as notified BEFORE sending — prevents scan_drafts race condition
            echo "$SPEC_ID" >> "${SCRIPT_DIR}/.notified-drafts-${PROJECT_ID}"

            echo "[callback] Sending spark approval: project=${PROJECT_ID} spec=${SPEC_ID}"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] spark approval: project=${PROJECT_ID} spec=${SPEC_ID} title=${SPEC_TITLE}" >> "$CALLBACK_LOG"
            python3 "$NOTIFY_PY" --spec-approval \
                "$PROJECT_ID" "$SPEC_ID" "$SPEC_TITLE" "$SUMMARY" "$TASKS_COUNT" 2>>"$CALLBACK_LOG" && {
                SENT_APPROVAL=true
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
# Skip noise: empty reflect/qa results don't need user attention.
# notify.py handles topic routing by project_id.
# ---------------------------------------------------------------------------
SKIP_NOTIFY=false

# Don't notify about empty reflect results (0 findings = nothing to report)
if [[ "$SKILL" == "reflect" && "$STATUS" == "done" ]]; then
    if echo "$PREVIEW" | grep -qiE 'analyzed: 0|inbox_files_created: 0|нечего обрабатывать|nothing to|0 pending'; then
        SKIP_NOTIFY=true
        echo "[callback] Skipping notification: reflect found 0 findings"
    fi
fi

# Don't notify about "Unknown skill" errors (skill not deployed yet)
if echo "$PREVIEW" | grep -qi 'Unknown skill'; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: unknown skill error"
fi

if [[ "$SENT_APPROVAL" == "false" && "$SKIP_NOTIFY" == "false" && -f "$NOTIFY_PY" ]]; then
    echo "[callback] Sending notification: project=${PROJECT_ID} msg_len=${#MSG}" >> "$CALLBACK_LOG"
    python3 "$NOTIFY_PY" "$PROJECT_ID" "$MSG" 2>>"$CALLBACK_LOG" || {
        echo "[callback] WARN: notify.py failed for project=${PROJECT_ID}" >&2
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: notify.py failed for project=${PROJECT_ID}" >> "$CALLBACK_LOG"
    }
elif [[ ! -f "$NOTIFY_PY" ]]; then
    echo "[callback] WARN: notify.py not found at ${NOTIFY_PY} — skipping Telegram notification" >&2
fi

# ---------------------------------------------------------------------------
# Step 6.5: Council/Architect/Reflect → Inbox feedback loop
# When council, architect, or reflect completes, write result_preview back to inbox
# with route=spark so the next orchestrator cycle creates a spec from it.
# This is a FALLBACK — skills should write inbox files themselves (FTR-149 Tasks 5/6c),
# but this ensures results aren't lost if the skill didn't write to inbox.
# ---------------------------------------------------------------------------
# Skip empty results (reflect with 0 findings shouldn't create inbox files)
EMPTY_RESULT=false
if echo "$PREVIEW" | grep -qiE 'analyzed: 0|inbox_files_created: 0|нечего обрабатывать|0 pending'; then
    EMPTY_RESULT=true
fi

if [[ "$STATUS" == "done" && "$EMPTY_RESULT" == "false" && ( "$SKILL" == "council" || "$SKILL" == "architect" || "$SKILL" == "reflect" ) && -n "$PREVIEW" ]]; then
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

        # Check if skill already wrote inbox files (FTR-149: skills write their own)
        # If recent inbox files from this skill exist, skip fallback to avoid duplicates
        EXISTING_INBOX=$(find "$INBOX_DIR" -name "*-${SKILL}-*" -newer "$INBOX_DIR/.." -mmin -10 2>/dev/null | head -1 || true)
        if [[ -n "$EXISTING_INBOX" ]]; then
            echo "[callback] ${SKILL} already wrote inbox files — skipping fallback"
        else
            TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
            INBOX_FILE="${INBOX_DIR}/${TIMESTAMP}-${SKILL}-result.md"

            cat > "$INBOX_FILE" <<INBOX_EOF
# ${SKILL^} result: ${TASK_LABEL}
**Source:** ${SKILL}
**Route:** spark
**Status:** new
**Context:** ai/diary/index.md
---
${PREVIEW}
INBOX_EOF

            echo "[callback] ${SKILL} result written to inbox: ${INBOX_FILE}"
        fi

        # Notify user that skill result is queued for spark
        if [[ -f "$NOTIFY_PY" ]]; then
            python3 "$NOTIFY_PY" "$PROJECT_ID" \
                "🧠 *${PROJECT_ID}*: ${SKILL_LABEL} завершена. Результат отправлен в Spark." 2>>"$CALLBACK_LOG" || true
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

# Debug trace — log completion
echo "[$(date '+%Y-%m-%d %H:%M:%S')] callback done: id=${PUEUE_ID} project=${PROJECT_ID} skill=${SKILL} status=${STATUS} sent_approval=${SENT_APPROVAL} skip_notify=${SKIP_NOTIFY}" >> "$CALLBACK_LOG"
