#!/usr/bin/env bash
# scripts/vps/inbox-processor.sh
# Process inbox files: read route metadata, dispatch to skill via Pueue.
# Usage: inbox-processor.sh <project_id> <project_dir> <inbox_file>
#
# Called by orchestrator.sh for each new *.md file found in ai/inbox/.
# Reads **Route:** metadata, maps to skill command, submits to Pueue via
# run-agent.sh, logs in SQLite, notifies Telegram topic.
#
# Env vars passed to the agent subprocess:
#   CLAUDE_PROJECT_DIR        — absolute path to the project
#   CLAUDE_CURRENT_SPEC_PATH  — absolute path to the inbox file (in done/)
#
# Exit codes:
#   0  — submitted (or already processed)
#   1  — file not found or fatal error
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
PROJECT_ID="${1:?Usage: inbox-processor.sh <project_id> <project_dir> <inbox_file>}"
PROJECT_DIR="${2:?Missing project_dir argument}"
INBOX_FILE="${3:?Missing inbox_file argument}"

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a
[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
if [[ ! -f "$INBOX_FILE" ]]; then
    echo "[inbox] File not found: ${INBOX_FILE}" >&2
    exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "[inbox] Project dir not found: ${PROJECT_DIR}" >&2
    exit 1
fi

# Skip already-processed files (idempotent re-entry by orchestrator)
if ! grep -qE '^\*\*Status:\*\* new' "$INBOX_FILE" 2>/dev/null; then
    echo "[inbox] Skipping (not new): ${INBOX_FILE}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Extract metadata from inbox file
# ---------------------------------------------------------------------------
ROUTE=$(grep -oE '^\*\*Route:\*\* [^ ]+' "$INBOX_FILE" 2>/dev/null | sed 's/\*\*Route:\*\* //' || echo "spark")
ROUTE="${ROUTE:-spark}"

SOURCE=$(grep -oE '^\*\*Source:\*\* [^ ]+' "$INBOX_FILE" 2>/dev/null | sed 's/\*\*Source:\*\* //' || echo "telegram")

# Context: optional link to detailed document (synthesis.md, report.md, spec file)
CONTEXT=$(grep -oE '^\*\*Context:\*\* .+' "$INBOX_FILE" 2>/dev/null | sed 's/\*\*Context:\*\* //' || true)

# Idea text: everything after the --- separator, limited to 50 lines
IDEA_TEXT=$(sed -n '/^---$/,$ { /^---$/d; p; }' "$INBOX_FILE" 2>/dev/null | head -50 | tr '\n' ' ' | xargs)

# Fallback: if no separator, use entire file body (skip metadata header lines)
if [[ -z "$IDEA_TEXT" ]]; then
    IDEA_TEXT=$(grep -vE '^\*\*(Source|Route|Status|Context):\*\*|^#' "$INBOX_FILE" | head -20 | tr '\n' ' ' | xargs)
fi

echo "[inbox] route=${ROUTE} project=${PROJECT_ID} file=$(basename "$INBOX_FILE")"

# ---------------------------------------------------------------------------
# Map route → skill + Claude command
# ---------------------------------------------------------------------------
# ALL inbox tasks run headless (no user to answer questions).
# Telegram messages go through orchestrator → agent without TTY.
HEADLESS_PREFIX="[headless] Source: ${SOURCE}. "
if [[ -n "$CONTEXT" ]]; then
    HEADLESS_PREFIX="${HEADLESS_PREFIX}Context: ${CONTEXT}. "
fi

case "$ROUTE" in
    spark)
        SKILL="spark"
        TASK_CMD="/spark ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    architect)
        SKILL="architect"
        TASK_CMD="/architect ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    council)
        SKILL="council"
        TASK_CMD="/council ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    spark_bug)
        SKILL="spark"
        TASK_CMD="/spark ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    bughunt)
        SKILL="bughunt"
        TASK_CMD="/bughunt ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    qa)
        SKILL="qa"
        TASK_CMD="/qa ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    reflect)
        SKILL="reflect"
        TASK_CMD="/reflect ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    scout)
        SKILL="scout"
        TASK_CMD="/scout ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
    *)
        echo "[inbox] Unknown route '${ROUTE}', defaulting to spark" >&2
        SKILL="spark"
        TASK_CMD="/spark ${HEADLESS_PREFIX}${IDEA_TEXT}"
        ;;
esac

# ---------------------------------------------------------------------------
# Resolve provider from DB
# ---------------------------------------------------------------------------
PROVIDER=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${PROJECT_ID}')
print(state['provider'] if state else 'claude')
" 2>/dev/null || echo "claude")
PROVIDER="${PROVIDER:-claude}"

# Read Provider: header from inbox file (overrides project default)
FILE_PROVIDER=$(grep -oE '^\*\*Provider:\*\* \w+' "$INBOX_FILE" 2>/dev/null | sed 's/\*\*Provider:\*\* //' || true)
if [[ -n "$FILE_PROVIDER" ]]; then
    PROVIDER="$FILE_PROVIDER"
    echo "[inbox] provider override from file: ${FILE_PROVIDER}"
fi

# ---------------------------------------------------------------------------
# Mark file as processing before dispatch (prevents double-submission)
# ---------------------------------------------------------------------------
# sed -i behaves differently on macOS vs Linux
if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' 's/^\*\*Status:\*\* new/**Status:** processing/' "$INBOX_FILE"
else
    sed -i 's/^\*\*Status:\*\* new/**Status:** processing/' "$INBOX_FILE"
fi

# Move to done directory
DONE_DIR="$(dirname "$INBOX_FILE")/done"
mkdir -p "$DONE_DIR"
DONE_FILE="${DONE_DIR}/$(basename "$INBOX_FILE")"
mv "$INBOX_FILE" "$DONE_FILE"

echo "[inbox] Moved to done: ${DONE_FILE}"

# ---------------------------------------------------------------------------
# Send Telegram notification before agent launch
# ---------------------------------------------------------------------------
_SKILL_LABELS_spark="Создаю спеку"
_SKILL_LABELS_autopilot="Запускаю автопилот"
_SKILL_LABELS_architect="Запускаю архитектора"
_SKILL_LABELS_council="Собираю консилиум"
_SKILL_LABELS_bughunt="Охота на баги"
_SKILL_LABELS_reflect="Рефлексия"
_SKILL_LABELS_scout="Разведка"
_SKILL_LABELS_qa="QA проверка"
SKILL_LABEL_VAR="_SKILL_LABELS_${SKILL}"
SKILL_LABEL="${!SKILL_LABEL_VAR:-Обработка}"

NOTIFY_MSG="🚀 *${PROJECT_ID}*: ${SKILL_LABEL}
${IDEA_TEXT:0:200}"

NOTIFY_PY="${SCRIPT_DIR}/notify.py"
if [[ -f "$NOTIFY_PY" ]]; then
    python3 "$NOTIFY_PY" "$PROJECT_ID" "$NOTIFY_MSG" 2>/dev/null || {
        echo "[inbox] WARN: notify.py failed for project=${PROJECT_ID}" >&2
    }
fi

# ---------------------------------------------------------------------------
# Generate task label
# ---------------------------------------------------------------------------
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
TASK_LABEL="${PROJECT_ID}:inbox-${TIMESTAMP}"
PUEUE_GROUP="${PROVIDER}-runner"

# ---------------------------------------------------------------------------
# Submit to Pueue via run-agent.sh
# CLAUDE_PROJECT_DIR and CLAUDE_CURRENT_SPEC_PATH are passed as env vars
# so the agent subprocess knows its workspace and the originating spec file.
# ---------------------------------------------------------------------------
export CLAUDE_PROJECT_DIR="$PROJECT_DIR"
export CLAUDE_CURRENT_SPEC_PATH="$DONE_FILE"

PUEUE_ID=$(pueue add \
    --group "$PUEUE_GROUP" \
    --label "$TASK_LABEL" \
    --print-task-id \
    -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_DIR" "$PROVIDER" "$SKILL" "$TASK_CMD" 2>&1) || {
    echo "[inbox] ERROR: pueue submission failed: ${PUEUE_ID}" >&2
    exit 1
}

echo "[inbox] Submitted pueue_id=${PUEUE_ID} label=${TASK_LABEL} group=${PUEUE_GROUP}"

# ---------------------------------------------------------------------------
# Log task in SQLite + update project phase (parameterized via db.py)
# ---------------------------------------------------------------------------
python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
db.log_task('${PROJECT_ID}', '${TASK_LABEL}', '${SKILL}', 'queued', ${PUEUE_ID})
db.update_project_phase('${PROJECT_ID}', 'processing_inbox', '${TASK_LABEL}')
print('[inbox] DB updated: task_log + phase=processing_inbox')
" || {
    echo "[inbox] WARN: DB logging failed for pueue_id=${PUEUE_ID}" >&2
}

echo "[inbox] Done: route=${ROUTE} skill=${SKILL} pueue_id=${PUEUE_ID} project=${PROJECT_ID}"
