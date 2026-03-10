#!/usr/bin/env bash
# orchestrator.sh — Main daemon: watches inbox + backlog, runs Spark + Autopilot + QA
#
# This is the "brain" that ties everything together:
#   1. Polls ai/inbox/ for new ideas → runs inbox-processor.sh (Spark)
#   2. Polls ai/backlog.md for queued specs → runs autopilot-loop.sh
#   3. Runs QA on done specs → qa-loop.sh (user-perspective testing)
#   4. Sends notifications on events (done/blocked/error)
#   5. Responds to .run-now trigger file (from Telegram /run command)
#
# Usage:
#   ./scripts/vps/orchestrator.sh              # Run forever (daemon mode)
#   ./scripts/vps/orchestrator.sh --once       # Single pass, then exit
#   ./scripts/vps/orchestrator.sh --status     # Show current state
#
# Run in tmux:
#   tmux new-session -d -s dld-orchestrator "./scripts/vps/orchestrator.sh"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load config
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a; source "$SCRIPT_DIR/.env"; set +a
fi

INBOX_DIR="${INBOX_DIR:-$PROJECT_DIR/ai/inbox}"
BACKLOG_FILE="${BACKLOG_FILE:-$PROJECT_DIR/ai/backlog.md}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/ai/diary/vps-logs}"
INBOX_POLL="${INBOX_POLL_INTERVAL:-300}"
BACKLOG_POLL="${BACKLOG_POLL_INTERVAL:-60}"
QA_POLL="${QA_POLL_INTERVAL:-120}"
MAX_SPECS="${MAX_SPECS_PER_RUN:-10}"
QA_DIR="$PROJECT_DIR/ai/qa"
LOCKFILE="$PROJECT_DIR/.orchestrator.lock"
PIDFILE="$PROJECT_DIR/.orchestrator.pid"
RUN_TRIGGER="$PROJECT_DIR/.run-now"
STATE_FILE="$PROJECT_DIR/.orchestrator-state.json"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

mkdir -p "$LOG_DIR" "$INBOX_DIR" "$QA_DIR"

# ── Helpers ──

log() { echo -e "$(date '+%H:%M:%S') $*"; }
log_info() { log "${BLUE}[INFO]${NC} $*"; }
log_ok() { log "${GREEN}[OK]${NC} $*"; }
log_warn() { log "${YELLOW}[WARN]${NC} $*"; }
log_err() { log "${RED}[ERR]${NC} $*"; }

update_state() {
    local phase="$1"
    local detail="${2:-}"
    cat > "$STATE_FILE" <<EOF
{
  "phase": "$phase",
  "detail": "$detail",
  "updated": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "pid": $$
}
EOF
}

count_inbox() {
    find "$INBOX_DIR" -maxdepth 1 -name "*.md" -type f 2>/dev/null | wc -l
}

count_queued() {
    if [[ -f "$BACKLOG_FILE" ]]; then
        grep -cE '\|\s*(queued|resumed)\s*\|' "$BACKLOG_FILE" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

count_qa_pending() {
    local count=0
    if [[ -f "$BACKLOG_FILE" ]]; then
        while IFS= read -r line; do
            local sid
            sid=$(echo "$line" | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1)
            if [[ -n "$sid" ]] && ! ls "$QA_DIR/${sid}"-* &>/dev/null; then
                count=$((count + 1))
            fi
        done < <(grep -E '\|\s*done\s*\|' "$BACKLOG_FILE" 2>/dev/null || true)
    fi
    echo "$count"
}

# ── Lock management ──

acquire_lock() {
    if [[ -f "$LOCKFILE" ]]; then
        local old_pid
        old_pid=$(cat "$LOCKFILE" 2>/dev/null || echo "")
        if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
            log_err "Another orchestrator is running (PID $old_pid)"
            exit 1
        fi
        log_warn "Stale lock found, removing"
        rm -f "$LOCKFILE"
    fi
    echo $$ > "$LOCKFILE"
    echo $$ > "$PIDFILE"
}

release_lock() {
    rm -f "$LOCKFILE" "$PIDFILE" "$RUN_TRIGGER"
    update_state "stopped"
}
trap release_lock EXIT INT TERM

# ── Status command ──

if [[ "${1:-}" == "--status" ]]; then
    echo -e "${BLUE}DLD Orchestrator Status${NC}"
    echo ""

    if [[ -f "$STATE_FILE" ]]; then
        echo "State:"
        cat "$STATE_FILE" | python3 -m json.tool 2>/dev/null || cat "$STATE_FILE"
    else
        echo "State: not running"
    fi

    echo ""
    echo "Inbox: $(count_inbox) ideas"
    echo "Queued: $(count_queued) specs"
    echo "QA pending: $(count_qa_pending) specs"

    if [[ -f "$LOCKFILE" ]]; then
        echo "Lock: $(cat "$LOCKFILE") ($(kill -0 "$(cat "$LOCKFILE")" 2>/dev/null && echo "alive" || echo "stale"))"
    else
        echo "Lock: none"
    fi
    exit 0
fi

# ── Main ──

ONCE=false
[[ "${1:-}" == "--once" ]] && ONCE=true

acquire_lock

echo -e "${BLUE}"
echo "  ___  _    ___"
echo " |   \| |  |   \\"
echo " | |) | |__| |) |"
echo " |___/|____|___/"
echo -e "${NC}"
echo "DLD Orchestrator — Autonomous Pipeline"
echo "Project: $PROJECT_DIR"
echo "Inbox poll: ${INBOX_POLL}s | Backlog poll: ${BACKLOG_POLL}s | QA poll: ${QA_POLL}s"
echo ""

LAST_INBOX_CHECK=0
LAST_BACKLOG_CHECK=0
LAST_QA_CHECK=0

notify() {
    if [[ -x "$SCRIPT_DIR/notify.sh" ]]; then
        "$SCRIPT_DIR/notify.sh" "$@" || true
    fi
}

# Notify startup
notify "Orchestrator started on $(hostname)"

while true; do
    NOW=$(date +%s)

    # ── Check for manual trigger ──

    if [[ -f "$RUN_TRIGGER" ]]; then
        log_info "Manual trigger detected (.run-now)"
        rm -f "$RUN_TRIGGER"
        LAST_INBOX_CHECK=0
        LAST_BACKLOG_CHECK=0
        LAST_QA_CHECK=0
    fi

    # ── Phase 1: Process inbox (ideas → specs via Spark) ──

    INBOX_ELAPSED=$((NOW - LAST_INBOX_CHECK))
    if [[ $INBOX_ELAPSED -ge $INBOX_POLL ]]; then
        INBOX_COUNT=$(count_inbox)
        if [[ $INBOX_COUNT -gt 0 ]]; then
            log_info "Inbox has $INBOX_COUNT idea(s) — running Spark"
            update_state "spark" "Processing $INBOX_COUNT ideas"
            notify "Processing $INBOX_COUNT idea(s) from inbox..."

            set +e
            "$SCRIPT_DIR/inbox-processor.sh" 2>&1 | tee -a "$LOG_DIR/orchestrator.log"
            INBOX_EXIT=$?
            set -e

            if [[ $INBOX_EXIT -eq 0 ]]; then
                log_ok "Inbox processed"
                # Force immediate backlog check after new specs created
                LAST_BACKLOG_CHECK=0
            else
                log_err "Inbox processing failed (exit=$INBOX_EXIT)"
                notify "Inbox processing failed (exit=$INBOX_EXIT)"
            fi
        fi
        LAST_INBOX_CHECK=$NOW
    fi

    # ── Phase 2: Run autopilot on queued specs ──

    BACKLOG_ELAPSED=$((NOW - LAST_BACKLOG_CHECK))
    if [[ $BACKLOG_ELAPSED -ge $BACKLOG_POLL ]]; then
        QUEUED_COUNT=$(count_queued)
        if [[ $QUEUED_COUNT -gt 0 ]]; then
            log_info "Backlog has $QUEUED_COUNT queued spec(s) — running Autopilot"
            update_state "autopilot" "$QUEUED_COUNT queued specs"
            notify "Running autopilot on $QUEUED_COUNT queued spec(s)..."

            set +e
            cd "$PROJECT_DIR"
            "$PROJECT_DIR/scripts/autopilot-loop.sh" "$MAX_SPECS" 2>&1 | tee -a "$LOG_DIR/orchestrator.log"
            AUTOPILOT_EXIT=$?
            set -e

            case $AUTOPILOT_EXIT in
                0) log_ok "All specs completed"
                   notify "All queued specs completed!" ;;
                1) log_warn "Autopilot blocked — human intervention needed"
                   notify "BLOCKED: Autopilot needs human intervention. Check specs for ACTION REQUIRED." ;;
                2) log_warn "Max iterations reached"
                   notify "Autopilot hit max iterations. May need to continue." ;;
                *) log_err "Autopilot failed (exit=$AUTOPILOT_EXIT)"
                   notify "Autopilot failed (exit=$AUTOPILOT_EXIT)" ;;
            esac
        fi
        LAST_BACKLOG_CHECK=$NOW
    fi

    # ── Phase 3: QA testing on done specs ──

    QA_ELAPSED=$((NOW - LAST_QA_CHECK))
    if [[ $QA_ELAPSED -ge $QA_POLL ]]; then
        QA_PENDING=$(count_qa_pending)
        if [[ $QA_PENDING -gt 0 ]]; then
            log_info "QA pending for $QA_PENDING done spec(s) — running QA loop"
            update_state "qa" "Testing $QA_PENDING done specs"
            notify "🔍 Running QA on $QA_PENDING completed spec(s)..."

            set +e
            cd "$PROJECT_DIR"
            "$SCRIPT_DIR/qa-loop.sh" "$MAX_SPECS" 2>&1 | tee -a "$LOG_DIR/orchestrator.log"
            QA_EXIT=$?
            set -e

            case $QA_EXIT in
                0) log_ok "QA complete"
                   # Force inbox check — QA may have filed bugs
                   LAST_INBOX_CHECK=0 ;;
                *) log_err "QA loop failed (exit=$QA_EXIT)"
                   notify "QA loop failed (exit=$QA_EXIT)" ;;
            esac
        fi
        LAST_QA_CHECK=$NOW
    fi

    # ── Idle ──

    update_state "idle" "inbox=$(count_inbox) queued=$(count_queued) qa_pending=$(count_qa_pending)"

    if $ONCE; then
        log_info "Single pass complete (--once mode)"
        exit 0
    fi

    # Sleep in short increments to catch triggers quickly
    for _ in $(seq 1 10); do
        if [[ -f "$RUN_TRIGGER" ]]; then
            break
        fi
        sleep 3
    done
done
