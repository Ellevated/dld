#!/usr/bin/env bash
# scripts/vps/gemini-runner.sh
# Google Gemini CLI headless wrapper.
# Called by run-agent.sh, never directly.
#
# Requires GEMINI_API_KEY in .env (no OAuth dance on VDS).
# Gemini CLI: npm install -g @google/gemini-cli
set -euo pipefail

PROJECT_DIR="${1:?Missing project_dir}"
TASK="${2:?Missing task}"
SKILL="${3:-autopilot}"

GEMINI_BIN="${GEMINI_PATH:-gemini}"

# Validate Gemini CLI is available
if ! command -v "$GEMINI_BIN" &>/dev/null && [[ ! -x "$GEMINI_BIN" ]]; then
    jq -n '{"error":"gemini_not_found","detail":"Install: npm install -g @google/gemini-cli"}' >&2
    exit 42  # input error
fi

# Validate API key
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    jq -n '{"error":"gemini_api_key_missing","detail":"Set GEMINI_API_KEY in .env"}' >&2
    exit 42
fi

cd "$PROJECT_DIR"

PROMPT="/${SKILL} ${TASK}"

# Gemini CLI headless mode with API key auth
# set +e: prevent set -euo pipefail from terminating on non-zero exit (timeout/gemini)
set +e
timeout 1800 "$GEMINI_BIN" \
    -p "$PROMPT" \
    2>&1
EXIT_CODE=$?
set -e

# Output structured result via jq to prevent JSON injection from TASK/SKILL values
jq -n \
    --arg exit_code "$EXIT_CODE" \
    --arg project "$(basename "$PROJECT_DIR")" \
    --arg skill "$SKILL" \
    --arg task "$TASK" \
    '{exit_code: ($exit_code | tonumber), project: $project, skill: $skill, task: $task}'

exit "$EXIT_CODE"
