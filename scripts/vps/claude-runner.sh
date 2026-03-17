#!/usr/bin/env bash
# scripts/vps/claude-runner.sh
# DEPRECATED: Legacy bash fallback. Use claude-runner.py (Agent SDK) instead.
# Kept as fallback if claude-agent-sdk is not installed.
#
# Limitation: pipe-to-stdin mode may not reliably trigger Skills.
# The Agent SDK (claude-runner.py) is the correct approach.
set -euo pipefail

echo "[claude-runner.sh] WARNING: using legacy bash runner. Install claude-agent-sdk for Skill support." >&2

PROJECT_DIR="${1:?Missing project_dir}"
TASK="${2:?Missing task}"
SKILL="${3:-autopilot}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_BIN="${CLAUDE_PATH:-claude}"

unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true
cd "$PROJECT_DIR"

if [[ "$TASK" == /* ]]; then
    PROMPT="$TASK"
else
    PROMPT="/${SKILL} ${TASK}"
fi

LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(basename "$PROJECT_DIR")-$(date '+%Y%m%d-%H%M%S').log"

set +e
timeout 1800 "$CLAUDE_BIN" \
    --print \
    --permission-mode bypassPermissions \
    --max-turns 30 \
    "$PROMPT" \
    2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
set -e

jq -n \
    --arg exit_code "$EXIT_CODE" \
    --arg project "$(basename "$PROJECT_DIR")" \
    --arg skill "$SKILL" \
    --arg task "$TASK" \
    '{exit_code: ($exit_code | tonumber), project: $project, skill: $skill, task: $task}'

exit "$EXIT_CODE"
