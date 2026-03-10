#!/usr/bin/env bash
# scripts/vps/run-agent.sh
# Provider abstraction dispatcher for Pueue tasks.
# Usage: run-agent.sh <project_dir> <task> <provider> [skill]
#   provider: claude | codex
#   skill: autopilot (default) | spark | architect | council | qa | bughunt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${1:?Usage: run-agent.sh <project_dir> <task> <provider> [skill]}"
TASK="${2:?Missing task argument}"
PROVIDER="${3:?Missing provider argument (claude|codex)}"
SKILL="${4:-autopilot}"

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
        exec "${SCRIPT_DIR}/claude-runner.sh" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    codex)
        exec "${SCRIPT_DIR}/codex-runner.sh" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    *)
        jq -n --arg provider "$PROVIDER" '{"error":"unknown_provider","provider":$provider}' >&2
        exit 1
        ;;
esac
