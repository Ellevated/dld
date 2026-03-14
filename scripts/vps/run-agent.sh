#!/usr/bin/env bash
# scripts/vps/run-agent.sh
# Provider abstraction dispatcher for Pueue tasks.
# Usage: run-agent.sh <project_dir> <provider> <skill> <task...>
#   provider: claude | codex | gemini
#   skill: autopilot | spark | architect | council | qa | bughunt
#   task: everything after skill is joined as the task string
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${1:?Usage: run-agent.sh <project_dir> <provider> <skill> <task...>}"
PROVIDER="${2:?Missing provider argument (claude|codex|gemini)}"
SKILL="${3:?Missing skill argument}"
shift 3
TASK="$*"
# If single arg is a .task-cmd file, read task text from it (shell-safe)
if [[ -f "$TASK" && "$TASK" == *.txt ]]; then
    TASK_FILE="$TASK"
    TASK=$(cat "$TASK_FILE")
    rm -f "$TASK_FILE"
fi
[[ -z "$TASK" ]] && { echo '{"error":"missing_task"}' >&2; exit 1; }

# Source environment if available
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

# RAM floor gate: require 3GB free before launching an LLM agent
check_ram() {
    if [[ -f /proc/meminfo ]]; then
        local avail_kb
        avail_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
        local avail_gb=$(( avail_kb / 1048576 ))
        if (( avail_gb < 3 )); then
            jq -n --arg avail "$avail_gb" \
                '{"error":"insufficient_ram","available_gb":($avail|tonumber),"required_gb":3}' >&2
            exit 78  # EX_CONFIG
        fi
    fi
    # Skip check on non-Linux (macOS dev)
}

check_ram

# Validate project directory exists
if [[ ! -d "$PROJECT_DIR" ]]; then
    jq -n --arg path "$PROJECT_DIR" '{"error":"project_dir_not_found","path":$path}' >&2
    exit 1
fi

# Dispatch to provider-specific runner
case "$PROVIDER" in
    claude)
        # Agent SDK (Python) — native Skill support, structured output
        VENV_PY="${SCRIPT_DIR}/venv/bin/python3"
        [[ -x "$VENV_PY" ]] || { echo '{"error":"venv python not found"}' >&2; exit 1; }
        exec "$VENV_PY" "${SCRIPT_DIR}/claude-runner.py" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    codex)
        exec "${SCRIPT_DIR}/codex-runner.sh" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    gemini)
        exec "${SCRIPT_DIR}/gemini-runner.sh" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    *)
        jq -n --arg provider "$PROVIDER" '{"error":"unknown_provider","provider":$provider}' >&2
        exit 1
        ;;
esac
