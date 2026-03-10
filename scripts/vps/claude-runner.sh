#!/usr/bin/env bash
# scripts/vps/claude-runner.sh
# Claude Code CLI wrapper with per-project isolation.
# Called by run-agent.sh, never directly.
set -euo pipefail

PROJECT_DIR="${1:?Missing project_dir}"
TASK="${2:?Missing task}"
SKILL="${3:-autopilot}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_BIN="${CLAUDE_PATH:-claude}"

# Per-project config dir (prevents cross-session contamination — DA-9)
CONFIG_DIR="${PROJECT_DIR}/.claude-config"
mkdir -p "$CONFIG_DIR"

# Export env vars for Claude and DLD hooks
export CLAUDE_CODE_CONFIG_DIR="$CONFIG_DIR"
export CLAUDE_PROJECT_DIR="$PROJECT_DIR"
export PROJECT_DIR="$PROJECT_DIR"

# Build command based on skill
PROMPT="/${SKILL} ${TASK}"

# Structured JSON output, bounded turns
# flock serializes OAuth refresh across concurrent sessions (#27933)
# --timeout 120: wait up to 2min for lock, then proceed without (better than deadlock)
# set +e: prevent set -euo pipefail from terminating on non-zero exit (timeout/claude)
set +e
flock --timeout 120 /tmp/claude-oauth.lock \
    timeout 900 "$CLAUDE_BIN" \
    --print \
    --output-format json \
    --max-turns 30 \
    --verbose \
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
