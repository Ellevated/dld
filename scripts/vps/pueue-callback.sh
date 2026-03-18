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

# Night-reviewer has its own notification logic — skip generic callback
if [[ "$GROUP" == "night-reviewer" ]]; then
    echo "[callback] Skipping generic callback for night-reviewer group (id=${PUEUE_ID})"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] callback skipped: night-reviewer id=${PUEUE_ID}" >> "$CALLBACK_LOG"
    exit 0
fi

echo "[callback] pueue_id=${PUEUE_ID} project=${PROJECT_ID} task=${TASK_LABEL} result=${RESULT} status=${STATUS}"

# ---------------------------------------------------------------------------
# Resolve spec_id for QA dispatch (multi-layer)
# Layer 1: From TASK_LABEL regex (orchestrator sets label = spec_id)
# Layer 2: From agent output PREVIEW (spec_id appears in result text)
# Layer 3: From inbox done file (SpecID metadata written by Spark)
# ---------------------------------------------------------------------------
resolve_spec_id() {
    local task_label="$1" preview="$2" project_path="$3"

    # Layer 1: From TASK_LABEL (orchestrator sets label = spec_id)
    if [[ "$task_label" =~ (TECH|FTR|BUG|ARCH)-[0-9]+ ]]; then
        echo "${BASH_REMATCH[0]}"
        return 0
    fi

    # Layer 2: From agent output preview (spec_id appears in result text)
    if [[ -n "$preview" ]]; then
        local from_preview
        from_preview=$(echo "$preview" | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || true)
        if [[ -n "$from_preview" ]]; then
            echo "$from_preview"
            return 0
        fi
    fi

    # Layer 3: From inbox done file (SpecID metadata written by Spark)
    if [[ -n "$project_path" && "$task_label" =~ ^inbox- ]]; then
        local inbox_done_dir="${project_path}/ai/inbox/done"
        if [[ -d "$inbox_done_dir" ]]; then
            local spec_from_inbox
            spec_from_inbox=$(grep -rh '\*\*SpecID:\*\*' "$inbox_done_dir"/*.md 2>/dev/null | \
                tail -1 | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' || true)
            if [[ -n "$spec_from_inbox" ]]; then
                echo "$spec_from_inbox"
                return 0
            fi
        fi
    fi

    return 1  # No spec_id resolved
}

# ---------------------------------------------------------------------------
# Step 1-3: Release slot + finish task + update project phase via db.py
# All SQL is parameterized inside db.py — no injection risk here.
# This block MUST execute even if notify fails, so errors are logged but not fatal.
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" ]]; then
    # Try to resolve spec_id for QA — inbox tasks without resolvable spec skip QA
    QA_SPEC_ID_EARLY=$(resolve_spec_id "$TASK_LABEL" "" "" || true)
    if [[ -n "$QA_SPEC_ID_EARLY" || ! "$TASK_LABEL" =~ ^inbox- ]]; then
        NEW_PHASE="qa_pending"
    else
        # Inbox task with no spec_id resolvable yet (PREVIEW not available here)
        # Defer to Step 7 where PREVIEW is available for Layer 2 resolution
        NEW_PHASE="qa_pending"
    fi
else
    NEW_PHASE="failed"
fi

CALLBACK_TASK_ARG=()
if [[ "$NEW_PHASE" == "qa_pending" ]]; then
    CALLBACK_TASK_ARG=("${TASK_LABEL}")
else
    CALLBACK_TASK_ARG=("")
fi

python3 "${SCRIPT_DIR}/db.py" callback \
    "${PUEUE_ID}" "${STATUS}" "${EXIT_CODE}" "${PROJECT_ID}" "${NEW_PHASE}" "${CALLBACK_TASK_ARG[@]}" || {
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
            sed 's/"result_preview": *"//;s/"$//' | python3 -c "import sys; print(sys.stdin.read()[:300], end='')" || true)
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

# Clean preview: strip markdown, process noise, tables for Telegram
CLEAN_PREVIEW=""
if [[ -n "$PREVIEW" ]]; then
    CLEAN_PREVIEW=$(echo "$PREVIEW" | \
        sed 's/^##* //g' | \
        sed 's/\*\*//g' | \
        sed '/^|[-=]/d' | \
        sed '/^```/d' | \
        sed '/Definition of Done/d' | \
        sed '/чекбокс/Id' | \
        sed '/отмечен.*выполнен/Id' | \
        sed '/функциональн.*чек/Id' | \
        sed '/^[[:space:]]*$/d' | \
        python3 -c "import sys; print(sys.stdin.read()[:200], end='')")
    # Trim to last complete sentence/line, add ellipsis if truncated
    if [[ ${#PREVIEW} -gt 200 ]]; then
        CLEAN_PREVIEW="${CLEAN_PREVIEW}…"
    fi
fi

# Extract spec ID from task label for context (e.g. "qa-BUG-680" → "BUG-680")
CONTEXT_SPEC=""
if [[ "$TASK_LABEL" =~ (TECH|FTR|BUG|ARCH)-[0-9]+ ]]; then
    CONTEXT_SPEC="${BASH_REMATCH[0]}"
fi

if [[ "$STATUS" == "done" ]]; then
    if [[ -n "$CONTEXT_SPEC" ]]; then
        MSG="✅ *${PROJECT_ID}*: ${SKILL_LABEL} по ${CONTEXT_SPEC} — готово"
    else
        MSG="✅ *${PROJECT_ID}*: ${SKILL_LABEL} — готово"
    fi
else
    if [[ -n "$CONTEXT_SPEC" ]]; then
        MSG="❌ *${PROJECT_ID}*: ${SKILL_LABEL} по ${CONTEXT_SPEC} — ошибка"
    else
        MSG="❌ *${PROJECT_ID}*: ${SKILL_LABEL} — ошибка"
    fi
fi

if [[ -n "$CLEAN_PREVIEW" ]]; then
    # Escape Markdown special chars to prevent "Can't parse entities" Telegram error
    CLEAN_PREVIEW=$(echo "$CLEAN_PREVIEW" | sed 's/\*/\\*/g; s/_/\\_/g; s/\[/\\[/g; s/`/\\`/g')
    MSG="${MSG}
${CLEAN_PREVIEW}"
fi

# (surrogate cleanup moved after result-flag messaging)

# ---------------------------------------------------------------------------
# Pre-compute completion/result flags for messaging
# ---------------------------------------------------------------------------
NOTIFY_PY="${SCRIPT_DIR}/notify.py"
EMPTY_RESULT=false
if echo "$PREVIEW" | grep -qiE 'analyzed: 0|findings_written: 0|нечего обрабатывать|0 pending|0 ✗|0 fail|0 FAIL|все проверки пройдены|all tests passed|QA PASSED'; then
    EMPTY_RESULT=true
fi

# Append next-step hint to QA messages
if [[ "$STATUS" == "done" && "$SKILL" == "qa" ]]; then
    if [[ "$EMPTY_RESULT" == "true" ]]; then
        MSG="${MSG}
→ Проблем не найдено"
    else
        MSG="${MSG}
→ Отчёт сохранён в файлы. Дальше решение за OpenClaw."
    fi
fi

# Final surrogate cleanup — Telegram API rejects surrogates with UnicodeEncodeError
MSG=$(python3 -c "
import sys
text = sys.stdin.read()
print(text.encode('utf-8', errors='replace').decode('utf-8'), end='')
" <<< "$MSG" 2>/dev/null || echo "$MSG")

# ---------------------------------------------------------------------------
# Step 6: Send Telegram completion notification (fail-safe)
# Skip noise: empty reflect/qa results don't need user attention.
# notify.py handles topic routing by project_id.
# ---------------------------------------------------------------------------
SKIP_NOTIFY=false

# Don't notify about reflect at all — it's internal housekeeping, not user-facing
if [[ "$SKILL" == "reflect" ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: reflect is internal (not user-facing)"
fi

# Don't notify about secondary QA (from inbox, not from autopilot)
# Primary QA has label like "project:qa-SPEC-ID", secondary has "project:qa-inbox-..."
if [[ "$SKILL" == "qa" && "$TASK_LABEL" =~ ^qa-inbox- ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: secondary QA from inbox (noise)"
fi

# Don't notify about intermediate cycle steps (spark, autopilot, qa) on success.
# OpenClaw reads pending-events and reports results itself.
# Only suppress SUCCESS — failures must still notify for debugging.
if [[ "$STATUS" == "done" && ("$SKILL" == "spark" || "$SKILL" == "autopilot" || "$SKILL" == "qa") ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: ${SKILL} success (OpenClaw handles reporting)"
fi

# Don't notify about "Unknown skill" errors (skill not deployed yet)
if echo "$PREVIEW" | grep -qi 'Unknown skill'; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: unknown skill error"
fi

# Don't notify about failed tasks without skill — uninformative "❌ — ошибка"
if [[ "$STATUS" == "failed" && -z "$SKILL" ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: failed task with no skill (noise)"
fi

if [[ "$SKIP_NOTIFY" == "false" && -f "$NOTIFY_PY" ]]; then
    echo "[callback] Sending notification: project=${PROJECT_ID} msg_len=${#MSG}" >> "$CALLBACK_LOG"
    python3 "$NOTIFY_PY" "$PROJECT_ID" "$MSG" 2>>"$CALLBACK_LOG" || {
        echo "[callback] WARN: notify.py failed for project=${PROJECT_ID}" >&2
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: notify.py failed for project=${PROJECT_ID}" >> "$CALLBACK_LOG"
    }
elif [[ ! -f "$NOTIFY_PY" ]]; then
    echo "[callback] WARN: notify.py not found at ${NOTIFY_PY} — skipping Telegram notification" >&2
fi

# ---------------------------------------------------------------------------
# Step 6.5: No automatic feedback → inbox
# North star: only OpenClaw writes inbox items after reviewing artifacts.
# Skills may write their own durable files (QA reports, diaries, etc), but the
# callback must not enqueue new work automatically.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 6.8: Write durable OpenClaw wake event
# Hybrid model: callback writes event artifacts, OpenClaw wakes via cron fallback
# and reads these files idempotently.
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" || ( "$STATUS" == "failed" && "$SKILL" == "qa" ) ]]; then
    PROJECT_PATH_FOR_EVENT=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${PROJECT_ID}')
print(state['path'] if state else '')
" 2>/dev/null || true)

    if [[ -n "$PROJECT_PATH_FOR_EVENT" && ( "$SKILL" == "autopilot" || "$SKILL" == "qa" || "$SKILL" == "reflect" ) ]]; then
        EVENT_DIR="${PROJECT_PATH_FOR_EVENT}/ai/openclaw/pending-events"
        mkdir -p "$EVENT_DIR"
        EVENT_TS=$(date '+%Y%m%d-%H%M%S')
        EVENT_FILE="${EVENT_DIR}/${EVENT_TS}-${SKILL}.json"
        ARTIFACT_REL=""
        if [[ "$SKILL" == "qa" ]]; then
            ARTIFACT_REL=$(find "${PROJECT_PATH_FOR_EVENT}/ai/qa" -maxdepth 1 -type f -name "[0-9]*-*.md" | sort | tail -1 | sed "s#^${PROJECT_PATH_FOR_EVENT}/##" || true)
        elif [[ "$SKILL" == "reflect" ]]; then
            ARTIFACT_REL=$(find "${PROJECT_PATH_FOR_EVENT}/ai/reflect" -maxdepth 1 -type f -name "findings-*.md" | sort | tail -1 | sed "s#^${PROJECT_PATH_FOR_EVENT}/##" || true)
        fi
        cat > "$EVENT_FILE" <<EOF
{
  "project_id": "${PROJECT_ID}",
  "skill": "${SKILL}",
  "status": "${STATUS}",
  "task_label": "${TASK_LABEL}",
  "artifact_rel": "${ARTIFACT_REL}",
  "created_at": "${EVENT_TS}"
}
EOF

        # Wake OpenClaw immediately so it reports cycle completion without cron lag
        OPENCLAW_BIN="${HOME}/.npm-global/bin/openclaw"
        if [[ -x "$OPENCLAW_BIN" ]]; then
            timeout 5 "$OPENCLAW_BIN" system event --mode now 2>>"$CALLBACK_LOG" || true
            echo "[callback] OpenClaw wake sent for ${SKILL} event (project=${PROJECT_ID})" >> "$CALLBACK_LOG"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Step 7: Post-autopilot — dispatch QA + Reflect
# ONLY after autopilot completion. NOT after spark — spark doesn't change code,
# so QA/reflect after spark creates infinite QA→inbox→spark→QA loops.
# ---------------------------------------------------------------------------
if [[ "$STATUS" == "done" && "$SKILL" == "autopilot" ]]; then
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
    echo "[callback] Post-autopilot tail: TASK_LABEL=${TASK_LABEL} (used as QA spec_id)" >> "$CALLBACK_LOG"

    if [[ -n "$PROJECT_PATH" ]]; then
        REFLECT_LABEL="${PROJECT_ID}:reflect-${TASK_LABEL}"

        # Resolve spec_id using all available signals (PREVIEW available now)
        QA_SPEC_ID=$(resolve_spec_id "$TASK_LABEL" "$PREVIEW" "$PROJECT_PATH" || true)

        if [[ -z "$QA_SPEC_ID" ]]; then
            echo "[callback] Skipping QA: no spec_id resolved from task_label='${TASK_LABEL}' or agent output"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] QA skip: no spec_id task=${TASK_LABEL}" >> "$CALLBACK_LOG"
        else
            QA_LABEL="${PROJECT_ID}:qa-${QA_SPEC_ID}"
            echo "[callback] Resolved QA spec_id=${QA_SPEC_ID} (task_label=${TASK_LABEL})" >> "$CALLBACK_LOG"

            # Dispatch QA once per autopilot completion
            if pueue status --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for t in data.get('tasks', {}).values():
    label = t.get('label', '')
    status = t.get('status', {})
    if label == '${QA_LABEL}' and isinstance(status, dict) and ('Running' in status or 'Queued' in status):
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
                echo "[callback] Skipping duplicate QA dispatch for ${QA_LABEL}"
            else
                pueue add --group "$RUNNER_GROUP" --label "$QA_LABEL" \
                    -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" \
                    "/qa ${QA_SPEC_ID}" 2>/dev/null && {
                    echo "[callback] QA dispatched for ${PROJECT_ID}:${QA_SPEC_ID} (group=${RUNNER_GROUP})"
                } || {
                    echo "[callback] WARN: QA dispatch failed for ${PROJECT_ID}" >&2
                }
            fi
        fi

        # Dispatch Reflect after every autopilot completion (unconditional — agents own diary writes)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] reflect dispatch attempt: project=${PROJECT_ID} task=${TASK_LABEL}" >> "$CALLBACK_LOG"
        if pueue status --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for t in data.get('tasks', {}).values():
    label = t.get('label', '')
    status = t.get('status', {})
    if label == '${REFLECT_LABEL}' and isinstance(status, dict) and ('Running' in status or 'Queued' in status):
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
            echo "[callback] Skipping duplicate reflect dispatch for ${REFLECT_LABEL}"
        else
            pueue add --group "$RUNNER_GROUP" --label "$REFLECT_LABEL" \
                -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_PATH" "$PROJECT_PROVIDER" "reflect" \
                "/reflect" 2>/dev/null && {
                echo "[callback] Reflect dispatched for ${PROJECT_ID}:${TASK_LABEL} (group=${RUNNER_GROUP})"
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] reflect dispatched OK: project=${PROJECT_ID} task=${TASK_LABEL}" >> "$CALLBACK_LOG"
            } || {
                echo "[callback] WARN: Reflect dispatch failed for ${PROJECT_ID}" >&2
            }
        fi
    fi
fi

echo "[callback] done pueue_id=${PUEUE_ID} project=${PROJECT_ID} task=${TASK_LABEL} status=${STATUS}"

# Debug trace — log completion
echo "[$(date '+%Y-%m-%d %H:%M:%S')] callback done: id=${PUEUE_ID} project=${PROJECT_ID} skill=${SKILL} status=${STATUS} skip_notify=${SKIP_NOTIFY}" >> "$CALLBACK_LOG"
