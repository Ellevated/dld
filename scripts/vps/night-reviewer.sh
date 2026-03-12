#!/usr/bin/env bash
# scripts/vps/night-reviewer.sh
# Nightly project scanner triggered by evening prompt.
# Runs /audit night for each project, dedup findings via SQLite.
#
# Usage: night-reviewer.sh project_id1 project_id2 ...
# Exit: 0 on success, 1 on critical error
#
# Module: night-reviewer
# Role: Nightly /audit night scan per project; dedup findings via SQLite fingerprinting.
# Uses: db.py (update-phase, save-finding, get-new-findings), notify.py, claude CLI, flock
# Used by: orchestrator.sh (via pueue night-reviewer group)

set -uo pipefail
# NOTE: -e intentionally omitted — each step has its own error handling for fail-safe behavior

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a
[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

PID_FILE="/tmp/night-reviewer.pid"

# ---------------------------------------------------------------------------
# PID file guard — prevent concurrent runs
# ---------------------------------------------------------------------------

if [[ -f "$PID_FILE" ]]; then
    existing_pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        echo "[night-reviewer] already running (pid=$existing_pid), exiting" >&2
        exit 1
    fi
    # Stale PID file — remove and continue
    rm -f "$PID_FILE"
fi

echo $$ > "$PID_FILE"

# ---------------------------------------------------------------------------
# Track which projects entered night_reviewing (for cleanup trap)
# ---------------------------------------------------------------------------

REVIEWING_PROJECTS=()

cleanup() {
    # Reset any still-processing projects to idle
    for pid in "${REVIEWING_PROJECTS[@]:-}"; do
        set +e
        python3 "${SCRIPT_DIR}/db.py" update-phase "$pid" idle 2>/dev/null
        set -e
    done
    rm -f "$PID_FILE"
}

trap 'cleanup' EXIT

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log() {
    local level="$1" msg="$2"
    printf '{"ts":"%s","level":"%s","component":"night-reviewer","msg":"%s"}\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$level" "$msg"
}

# ---------------------------------------------------------------------------
# Compute SHA256 fingerprint for a finding
# ---------------------------------------------------------------------------

fingerprint() {
    local project_id="$1" file="$2" issue_type="$3"
    printf '%s%s%s' "$project_id" "$file" "$issue_type" | sha256sum | cut -d' ' -f1
}

# ---------------------------------------------------------------------------
# Process a single project
# ---------------------------------------------------------------------------

process_project() {
    local PROJECT_ID="$1"

    # Look up project path from DB
    local PROJECT_PATH
    set +e
    PROJECT_PATH=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
s = db.get_project_state('${PROJECT_ID}')
print(s['path'] if s else '')
" 2>/dev/null)
    set -e

    if [[ -z "$PROJECT_PATH" ]]; then
        log "warn" "project not found or no path: ${PROJECT_ID}"
        return
    fi

    log "info" "starting night review for ${PROJECT_ID} at ${PROJECT_PATH}"

    # Mark as reviewing (track for cleanup)
    REVIEWING_PROJECTS+=("$PROJECT_ID")
    set +e
    python3 "${SCRIPT_DIR}/db.py" update-phase "${PROJECT_ID}" night_reviewing
    set -e

    # Run /audit night via claude with flock for OAuth safety
    local claude_output
    set +e
    claude_output=$(flock --timeout 120 /tmp/claude-oauth.lock \
        "${CLAUDE_PATH:-claude}" \
        --print \
        --output-format json \
        --max-turns 30 \
        --cwd "${PROJECT_PATH}" \
        -p "/audit night" 2>/tmp/night-reviewer-claude-stderr-$$.txt)
    local claude_exit=$?
    set -e

    if (( claude_exit != 0 )); then
        local stderr_snippet
        stderr_snippet=$(head -5 /tmp/night-reviewer-claude-stderr-$$.txt 2>/dev/null || echo "")
        log "error" "claude exited ${claude_exit} for ${PROJECT_ID}: ${stderr_snippet}"
        rm -f /tmp/night-reviewer-claude-stderr-$$.txt
        set +e
        python3 "${SCRIPT_DIR}/db.py" update-phase "${PROJECT_ID}" idle
        set -e
        # Remove from cleanup list since we already reset
        REVIEWING_PROJECTS=("${REVIEWING_PROJECTS[@]/$PROJECT_ID}")
        return
    fi
    rm -f /tmp/night-reviewer-claude-stderr-$$.txt

    # Parse findings: claude --output-format json returns {"result":"<text>","..."}
    # The audit night output is a JSON array embedded in the result field
    local findings_json
    set +e
    findings_json=$(printf '%s' "$claude_output" | jq -r '.result' 2>/dev/null | jq '.' 2>/dev/null)
    local jq_exit=$?
    set -e

    if (( jq_exit != 0 )) || [[ -z "$findings_json" ]] || [[ "$findings_json" == "null" ]]; then
        log "error" "failed to parse findings JSON for ${PROJECT_ID}"
        set +e
        python3 "${SCRIPT_DIR}/db.py" update-phase "${PROJECT_ID}" idle
        set -e
        REVIEWING_PROJECTS=("${REVIEWING_PROJECTS[@]/$PROJECT_ID}")
        return
    fi

    local finding_count
    finding_count=$(printf '%s' "$findings_json" | jq 'length' 2>/dev/null || echo "0")
    log "info" "parsed ${finding_count} findings for ${PROJECT_ID}"

    # Save each finding to SQLite (INSERT OR IGNORE dedup)
    local i=0
    while IFS= read -r finding_line; do
        local file issue_type description suggestion severity confidence line_range fp
        set +e
        file=$(printf '%s' "$finding_line" | jq -r '.file // ""')
        issue_type=$(printf '%s' "$finding_line" | jq -r '.issue_type // ""')
        description=$(printf '%s' "$finding_line" | jq -r '.description // ""')
        suggestion=$(printf '%s' "$finding_line" | jq -r '.suggestion // ""')
        severity=$(printf '%s' "$finding_line" | jq -r '.severity // "medium"')
        confidence=$(printf '%s' "$finding_line" | jq -r '.confidence // "medium"')
        line_range=$(printf '%s' "$finding_line" | jq -r '.line // ""')
        set -e

        fp=$(fingerprint "${PROJECT_ID}" "${file}" "${issue_type}")

        set +e
        python3 "${SCRIPT_DIR}/db.py" save-finding \
            "${PROJECT_ID}" "${fp}" "${severity}" "${confidence}" \
            "${file}" "${line_range}" "${description}" "${suggestion}" 2>/dev/null
        set -e

        i=$((i + 1))
    done < <(printf '%s' "$findings_json" | jq -c '.[]' 2>/dev/null)

    # Fetch new (unseen) findings and notify via Telegram
    local new_findings_json
    set +e
    new_findings_json=$(python3 "${SCRIPT_DIR}/db.py" get-new-findings "${PROJECT_ID}" 2>/dev/null)
    set -e

    if [[ -z "$new_findings_json" ]] || [[ "$new_findings_json" == "[]" ]]; then
        log "info" "no new findings for ${PROJECT_ID}"
    else
        local new_count
        new_count=$(printf '%s' "$new_findings_json" | jq 'length' 2>/dev/null || echo "0")
        log "info" "sending ${new_count} new findings for ${PROJECT_ID}"

        while IFS= read -r nf; do
            local nf_severity nf_confidence nf_file nf_line nf_desc nf_sugg nf_id
            set +e
            nf_id=$(printf '%s' "$nf" | jq -r '.id // ""')
            nf_severity=$(printf '%s' "$nf" | jq -r '.severity // "medium"')
            nf_confidence=$(printf '%s' "$nf" | jq -r '.confidence // "medium"')
            nf_file=$(printf '%s' "$nf" | jq -r '.file_path // ""')
            nf_line=$(printf '%s' "$nf" | jq -r '.line_range // ""')
            nf_desc=$(printf '%s' "$nf" | jq -r '.summary // ""')
            nf_sugg=$(printf '%s' "$nf" | jq -r '.suggestion // ""')
            set -e

            local msg
            msg="[${nf_severity}/${nf_confidence}] Finding #${nf_id}
File: ${nf_file}:${nf_line}
${nf_desc}
Suggestion: ${nf_sugg}"

            set +e
            python3 "${SCRIPT_DIR}/notify.py" "${PROJECT_ID}" "${msg}" 2>/dev/null
            set -e

        done < <(printf '%s' "$new_findings_json" | jq -c '.[]' 2>/dev/null)
    fi

    # Reset phase to idle
    set +e
    python3 "${SCRIPT_DIR}/db.py" update-phase "${PROJECT_ID}" idle
    set -e

    # Remove from cleanup list — already handled
    REVIEWING_PROJECTS=("${REVIEWING_PROJECTS[@]/$PROJECT_ID}")
    log "info" "night review complete for ${PROJECT_ID}"
}

# ---------------------------------------------------------------------------
# Main: iterate over all project IDs passed as arguments
# ---------------------------------------------------------------------------

if [[ $# -eq 0 ]]; then
    log "error" "no project IDs provided"
    exit 1
fi

log "info" "night-reviewer starting for: $*"

for PROJECT_ID in "$@"; do
    [[ -z "$PROJECT_ID" ]] && continue
    process_project "$PROJECT_ID"
done

log "info" "night-reviewer done"
