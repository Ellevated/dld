#!/usr/bin/env bash
# scripts/vps/orchestrator.sh
# Main daemon loop for multi-project orchestration.
# Runs as systemd service (dld-orchestrator.service).
#
# Each cycle:
#   1. Hot-reloads projects.json → SQLite via db.py seed_projects_from_json
#   2. Per project: git pull, scan ai/inbox/, scan ai/backlog.md, dispatch QA
#
# Env vars:
#   POLL_INTERVAL   — seconds between full cycles (default: 300)
#   PROJECTS_JSON   — path to projects.json (default: $SCRIPT_DIR/projects.json)
#   DB_PATH         — override SQLite path (passed to db.py)
#
# Trigger files:
#   .run-now-{project_id} — touch to trigger immediate cycle for that project
#
# Exit codes:
#   signals SIGTERM/SIGINT — clean shutdown (removes PID file)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

# Activate venv for python3 (notify.py, db.py need dotenv, telegram, etc.)
[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

POLL_INTERVAL="${POLL_INTERVAL:-300}"
PROJECTS_JSON="${PROJECTS_JSON:-${SCRIPT_DIR}/projects.json}"

# File-based logging (rotated daily, 7 days retention)
LOG_DIR="${LOG_DIR:-/var/log/dld-orchestrator}"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${SCRIPT_DIR}/logs" && mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/orchestrator-$(date '+%Y-%m-%d').log"

# Clean logs older than 7 days
find "$LOG_DIR" -name "orchestrator-*.log" -mtime +7 -delete 2>/dev/null || true

# PID file for health checks
PID_FILE="${SCRIPT_DIR}/.orchestrator.pid"
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"; log_json "info" "Orchestrator stopped (pid=$$)"' EXIT INT TERM

# ---------------------------------------------------------------------------
# Logging (stdout + file)
# ---------------------------------------------------------------------------

log_json() {
    local level="$1" msg="$2"
    local extras=""
    shift 2
    while [[ $# -ge 2 ]]; do
        extras="${extras},\"${1}\":\"${2}\""
        shift 2
    done
    local line
    line=$(printf '{"ts":"%s","level":"%s","msg":"%s"%s}' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        "$level" \
        "$msg" \
        "$extras")
    echo "$line"
    echo "$line" >> "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# Sync projects.json → SQLite (hot-reload every cycle)
# ---------------------------------------------------------------------------

sync_projects() {
    if [[ ! -f "$PROJECTS_JSON" ]]; then
        log_json "warn" "projects.json not found" "path" "$PROJECTS_JSON"
        return
    fi
    local result
    result=$(python3 -c "
import json, sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
with open('${PROJECTS_JSON}') as f:
    projects = json.load(f)
db.seed_projects_from_json(projects)
print(len(projects))
" 2>&1) || {
        log_json "error" "sync_projects failed" "detail" "$result"
        return
    }
    log_json "info" "synced projects" "count" "$result"
}

# ---------------------------------------------------------------------------
# Get all enabled projects as "project_id|path" lines
# ---------------------------------------------------------------------------

get_projects() {
    python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
for p in db.get_all_projects():
    print(f\"{p['project_id']}|{p['path']}\")
" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Git pull (skip on failure, log warning)
# ---------------------------------------------------------------------------

git_pull() {
    local project_id="$1" project_dir="$2"
    if [[ ! -d "${project_dir}/.git" ]]; then
        log_json "warn" "not a git repo" "path" "$project_dir"
        return 1
    fi

    # SAFETY: skip pull entirely if an agent is running in this project
    if pueue status --json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('tasks', {}).values():
    label = t.get('label', '')
    status = t.get('status', '')
    if label.startswith('${project_id}:') and isinstance(status, dict) and 'Running' in status:
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
        log_json "info" "skip git pull — agent running" "project" "$project_id"
        return 0
    fi

    # Working tree clean → fast path: pull --rebase
    if git -C "$project_dir" diff --quiet 2>/dev/null && \
       git -C "$project_dir" diff --cached --quiet 2>/dev/null; then
        local output
        output=$(git -C "$project_dir" pull --rebase origin develop 2>&1) || {
            log_json "warn" "git pull failed" "path" "$project_dir" "detail" "${output:0:200}"
            return 1
        }
        return 0
    fi

    # Dirty working tree, no agent running → fetch + rebase with autostash
    local output
    output=$(git -C "$project_dir" fetch origin develop 2>&1) || {
        log_json "warn" "git fetch failed" "path" "$project_dir" "detail" "${output:0:200}"
        return 1
    }
    output=$(git -C "$project_dir" rebase --autostash origin/develop 2>&1) || {
        # Abort failed rebase to leave repo in consistent state
        git -C "$project_dir" rebase --abort 2>/dev/null || true
        log_json "warn" "git rebase failed, aborted" "path" "$project_dir" "detail" "${output:0:200}"
        return 1
    }
    return 0
}

# ---------------------------------------------------------------------------
# Scan ai/inbox/ for new files
# ---------------------------------------------------------------------------

scan_inbox() {
    local project_id="$1" project_dir="$2"
    local inbox_dir="${project_dir}/ai/inbox"

    [[ ! -d "$inbox_dir" ]] && return

    local count=0
    local inbox_file
    for inbox_file in "${inbox_dir}"/*.md; do
        [[ ! -f "$inbox_file" ]] && continue
        # Only process files with Status: new
        if grep -q '^\*\*Status:\*\* new' "$inbox_file" 2>/dev/null; then
            log_json "info" "processing inbox file" "project" "$project_id" "file" "$(basename "$inbox_file")"
            "${SCRIPT_DIR}/inbox-processor.sh" "$project_id" "$project_dir" "$inbox_file" || {
                log_json "error" "inbox-processor failed" "project" "$project_id" "file" "$(basename "$inbox_file")"
            }
            count=$((count + 1))
        fi
    done

    if (( count > 0 )); then
        log_json "info" "inbox scan complete" "project" "$project_id" "processed" "$count"
    fi
}

# ---------------------------------------------------------------------------
# Scan ai/backlog.md for first queued spec and submit to Pueue
# ---------------------------------------------------------------------------

scan_backlog() {
    local project_id="$1" project_dir="$2"
    local backlog="${project_dir}/ai/backlog.md"

    [[ ! -f "$backlog" ]] && return

    # Find first queued spec ID (e.g. FTR-146, TECH-055, BUG-084, ARCH-003)
    local spec_id
    spec_id=$(grep -E '\|\s*queued\s*\|' "$backlog" 2>/dev/null | head -1 | \
              grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || true)

    [[ -z "$spec_id" ]] && return

    # Resolve provider from DB
    local provider
    provider=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${project_id}')
print(state['provider'] if state else 'claude')
" 2>/dev/null || echo "claude")
    provider="${provider:-claude}"

    # Check available slots
    local available
    available=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
print(db.get_available_slots('${provider}'))
" 2>/dev/null || echo "0")

    if (( available < 1 )); then
        log_json "info" "no slots available" "project" "$project_id" "provider" "$provider"
        return
    fi

    # Find spec file in ai/features/
    local spec_file
    spec_file=$(find "${project_dir}/ai/features/" -name "${spec_id}*" -type f 2>/dev/null | head -1 || true)

    if [[ -z "$spec_file" ]]; then
        log_json "warn" "spec file not found" "project" "$project_id" "spec_id" "$spec_id"
        return
    fi

    # Task-level provider override from spec frontmatter (e.g. "provider: gemini")
    local task_provider
    task_provider=$(grep -oE '^provider:\s+\w+' "$spec_file" 2>/dev/null | awk '{print $2}' || true)
    if [[ -n "$task_provider" ]]; then
        # Validate provider has compute slots
        local task_slots
        task_slots=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
print(db.get_available_slots('${task_provider}'))
" 2>/dev/null || echo "-1")
        if [[ "$task_slots" == "-1" ]] || (( task_slots < 0 )); then
            log_json "warn" "unknown provider in spec, using project default" "project" "$project_id" "spec_provider" "$task_provider"
        else
            provider="$task_provider"
        fi
    fi

    # Submit autopilot task to Pueue
    local task_label="${project_id}:${spec_id}"
    local pueue_group="${provider}-runner"
    local task_cmd="/autopilot ${spec_id}"

    log_json "info" "submitting autopilot" "project" "$project_id" "spec" "$spec_id" "provider" "$provider"

    local pueue_id
    pueue_id=$(pueue add \
        --group "$pueue_group" \
        --label "$task_label" \
        --print-task-id \
        -- "${SCRIPT_DIR}/run-agent.sh" "$project_dir" "$provider" "autopilot" "$task_cmd" 2>&1) || {
        log_json "error" "pueue submission failed" "project" "$project_id" "spec" "$spec_id" "detail" "${pueue_id:0:200}"
        return
    }

    # Acquire slot in DB
    python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
slot = db.try_acquire_slot('${project_id}', '${provider}', ${pueue_id})
if slot is None:
    print('[orchestrator] WARN: slot acquisition failed (race condition)', flush=True)
else:
    print(f'[orchestrator] slot={slot} acquired', flush=True)
" || {
        log_json "warn" "slot acquisition error" "project" "$project_id" "pueue_id" "$pueue_id"
    }

    # Log task + update phase
    python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
db.log_task('${project_id}', '${task_label}', 'autopilot', 'running', ${pueue_id})
db.update_project_phase('${project_id}', 'autopilot', '${spec_id}')
" || {
        log_json "warn" "DB update failed" "project" "$project_id" "pueue_id" "$pueue_id"
    }

    log_json "info" "autopilot submitted" "project" "$project_id" "spec" "$spec_id" "pueue_id" "$pueue_id"
}

# ---------------------------------------------------------------------------
# Dispatch night reviewer if .review-trigger file exists
# ---------------------------------------------------------------------------

dispatch_night_review() {
    local trigger_file="${SCRIPT_DIR}/.review-trigger"
    [[ ! -f "$trigger_file" ]] && return

    local project_ids
    project_ids=$(cat "$trigger_file")
    rm -f "$trigger_file"

    [[ -z "$project_ids" ]] && return

    log_json "info" "dispatching night review" "projects" "$project_ids"

    # Submit to pueue night-reviewer group (non-blocking)
    set +e
    pueue add --group night-reviewer --label "night-review" -- \
        "${SCRIPT_DIR}/night-reviewer.sh" $project_ids 2>/dev/null
    set -e
}

# ---------------------------------------------------------------------------
# Check for qa_pending phase and dispatch QA
# ---------------------------------------------------------------------------

dispatch_qa() {
    local project_id="$1" project_dir="$2"

    local phase current_task
    phase=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${project_id}')
print(state['phase'] if state else '')
" 2>/dev/null || true)

    [[ "$phase" != "qa_pending" ]] && return

    current_task=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${project_id}')
print(state['current_task'] if state and state['current_task'] else '')
" 2>/dev/null || true)

    # QA+Reflect are already dispatched by pueue-callback.sh Step 7.
    # If current_task is empty, callback already handled it — just reset to idle.
    if [[ -z "$current_task" ]]; then
        log_json "info" "qa_pending with no current_task — resetting to idle" "project" "$project_id"
        python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
db.update_project_phase('${project_id}', 'idle')
" 2>/dev/null || true
        return
    fi

    log_json "info" "dispatching QA" "project" "$project_id" "task" "$current_task"
    # qa-loop.sh created in Task 8 — background dispatch
    "${SCRIPT_DIR}/qa-loop.sh" "$project_id" "$project_dir" "$current_task" &
}

# ---------------------------------------------------------------------------
# Dispatch reflect after autopilot (parallel with QA)
# ---------------------------------------------------------------------------

dispatch_reflect() {
    local project_id="$1" project_dir="$2"

    local phase
    phase=$(python3 -c "
import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import db
s = db.get_project_state('${project_id}')
print(s['phase'] if s else '')
" 2>/dev/null || true)

    # Reflect runs in parallel with QA on qa_pending or qa_running phase
    [[ "$phase" != "qa_pending" && "$phase" != "qa_running" ]] && return

    # Check if reflect is already running in pueue for this project
    if pueue status --json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('tasks', {}).values():
    label = t.get('label', '')
    status = t.get('status', '')
    if '${project_id}:reflect' in label and isinstance(status, dict) and ('Running' in status or 'Queued' in status):
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
        return
    fi

    # Check if diary has enough pending entries (min 3 for reflect)
    local diary_index="${project_dir}/ai/diary/index.md"
    [[ ! -f "$diary_index" ]] && return

    local pending_count
    pending_count=$(grep -c '| pending |' "$diary_index" 2>/dev/null || true)
    pending_count=$(( pending_count + 0 ))  # sanitize to integer
    (( pending_count < 3 )) && return

    local provider
    provider=$(python3 -c "
import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import db
s = db.get_project_state('${project_id}')
print(s['provider'] if s else 'claude')
" 2>/dev/null || echo "claude")

    local pueue_group="${provider}-runner"
    local task_label="${project_id}:reflect-$(date '+%Y%m%d')"

    log_json "info" "dispatching reflect" "project" "$project_id" "pending" "$pending_count"

    pueue add --group "$pueue_group" --label "$task_label" \
        -- "${SCRIPT_DIR}/run-agent.sh" "$project_dir" "$provider" "reflect" "/reflect" 2>/dev/null || {
        log_json "warn" "reflect dispatch failed" "project" "$project_id"
    }
}

# ---------------------------------------------------------------------------
# Scan backlog for draft specs and send Telegram approval notifications
# ---------------------------------------------------------------------------

scan_drafts() {
    local project_id="$1" project_dir="$2"
    local backlog="${project_dir}/ai/backlog.md"

    [[ ! -f "$backlog" ]] && return

    # Find all draft spec IDs (exclude status documentation table)
    local draft_ids
    draft_ids=$(grep -E '^\|\s*(TECH|FTR|BUG|ARCH)-[0-9]+\s*\|.*\|\s*draft\s*\|' "$backlog" 2>/dev/null | \
                grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' || true)

    [[ -z "$draft_ids" ]] && return

    # Track which drafts we've already notified about (avoid spam)
    local notified_file="${SCRIPT_DIR}/.notified-drafts-${project_id}"
    touch "$notified_file"

    while IFS= read -r spec_id; do
        [[ -z "$spec_id" ]] && continue

        # Skip if already notified
        if grep -qF "$spec_id" "$notified_file" 2>/dev/null; then
            continue
        fi

        # Find spec file
        local spec_file
        spec_file=$(find "${project_dir}/ai/features/" -name "${spec_id}*" -type f 2>/dev/null | head -1 || true)
        [[ -z "$spec_file" ]] && continue

        # Extract title and problem from spec (flexible: handles Symptom, Why, Root Cause, Problem)
        local title problem tasks_count
        title=$(grep -m1 '^# ' "$spec_file" 2>/dev/null | sed 's/^# //' | head -c 100 || true)
        title="${title:-$spec_id}"
        # Try multiple section names for problem description
        problem=$(grep -A1 -E '^## (Why|Symptom|Problem|Root Cause)' "$spec_file" 2>/dev/null | tail -1 | head -c 200 || true)
        problem="${problem:-—}"
        # Count tasks: try "### Task" and "## Task" patterns
        tasks_count=$(grep -c -E '^#{2,3} Task' "$spec_file" 2>/dev/null || true)
        tasks_count=$(( tasks_count + 0 ))

        log_json "info" "sending draft approval" "project" "$project_id" "spec" "$spec_id"

        # Send approval notification via notify.py
        python3 "${SCRIPT_DIR}/notify.py" --spec-approval \
            "$project_id" "$spec_id" "$title" "$problem" "$tasks_count" 2>/dev/null && {
            # Mark as notified
            echo "$spec_id" >> "$notified_file"
            log_json "info" "draft notification sent" "project" "$project_id" "spec" "$spec_id"
        } || {
            log_json "error" "draft notification failed" "project" "$project_id" "spec" "$spec_id"
        }

    done <<< "$draft_ids"
}

# ---------------------------------------------------------------------------
# Process a single project (all steps)
# ---------------------------------------------------------------------------

process_project() {
    local project_id="$1" project_dir="$2"

    log_json "info" "processing project" "project" "$project_id"

    # Step 1: git pull (non-fatal on failure, skips if agent running)
    git_pull "$project_id" "$project_dir" || true

    # Step 2: scan inbox
    scan_inbox "$project_id" "$project_dir"

    # Step 3: scan backlog for draft specs → send approval notifications
    scan_drafts "$project_id" "$project_dir"

    # Step 4: scan backlog for queued specs → submit to autopilot
    scan_backlog "$project_id" "$project_dir"

    # Step 5: dispatch QA if phase=qa_pending
    dispatch_qa "$project_id" "$project_dir"

    # Step 6: dispatch reflect (parallel with QA, needs 3+ diary entries)
    dispatch_reflect "$project_id" "$project_dir"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

log_json "info" "orchestrator starting" "pid" "$$" "poll_interval" "$POLL_INTERVAL"

while true; do
    # Hot-reload projects from JSON → SQLite
    sync_projects

    # Dispatch night reviewer if trigger file exists (global, not per-project)
    dispatch_night_review

    # Fetch enabled projects
    local_projects=$(get_projects)

    if [[ -z "$local_projects" ]]; then
        log_json "warn" "no enabled projects found"
    else
        while IFS='|' read -r project_id project_dir; do
            [[ -z "$project_id" ]] && continue

            # Check for /run trigger file (immediate cycle)
            trigger_file="${SCRIPT_DIR}/.run-now-${project_id}"
            if [[ -f "$trigger_file" ]]; then
                rm -f "$trigger_file"
                log_json "info" "run-now trigger fired" "project" "$project_id"
            fi

            process_project "$project_id" "$project_dir"

        done <<< "$local_projects"
    fi

    log_json "info" "cycle complete" "sleeping" "${POLL_INTERVAL}s"
    sleep "$POLL_INTERVAL"
done
