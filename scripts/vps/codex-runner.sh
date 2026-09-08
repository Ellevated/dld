#!/usr/bin/env bash
# scripts/vps/codex-runner.sh
# ChatGPT Codex CLI wrapper.
# Called by run-agent.sh, never directly.
set -euo pipefail

PROJECT_DIR="${1:?Missing project_dir}"
TASK="${2:?Missing task}"
SKILL="${3:-autopilot}"

CODEX_BIN="${CODEX_PATH:-codex}"

# Record which binary actually ran. A stale global CLI shadowing the maintained one
# is invisible in the transcript otherwise — it cost three awardybot specs on
# 2026-09-07 (see the PATH note in run-agent.sh).
echo "codex-runner: $(command -v "$CODEX_BIN") $("$CODEX_BIN" --version 2>&1 | head -1)" >&2

cd "$PROJECT_DIR"

# Codex uses sandbox mode for safety
# set +e: prevent set -euo pipefail from terminating on non-zero exit (timeout/codex)
set +e
# stdin from /dev/null: `codex exec` appends stdin to the prompt and blocks until EOF.
# Under pueue stdin never closes, so 0.149.1 sat on "Reading additional input from stdin"
# until the 900s timeout — measured 2026-09-08, task 1547. A manual ssh run hid this,
# because ssh closes stdin for it.
timeout 900 "$CODEX_BIN" exec \
    "$TASK" \
    --sandbox workspace-write \
    --json \
    </dev/null \
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
