#!/usr/bin/env bash
# qa-loop.sh — User-perspective QA testing for completed specs
#
# Runs after autopilot marks specs as "done". Thinks like a real user:
# clicks buttons, calls APIs, tries edge cases.
#
# Results:
#   - PASS → ai/qa/{SPEC_ID}-ok.md
#   - FAIL → ai/inbox/{SPEC_ID}-qa-bugs.md (Spark picks up → you approve)
#
# Usage:
#   ./scripts/vps/qa-loop.sh              # QA all done specs without QA report
#   ./scripts/vps/qa-loop.sh --check      # Show specs pending QA
#   ./scripts/vps/qa-loop.sh --one        # QA only first pending spec
#   ./scripts/vps/qa-loop.sh 10           # Max 10 specs per run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load config
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a; source "$SCRIPT_DIR/.env"; set +a
fi

BACKLOG_FILE="${BACKLOG_FILE:-$PROJECT_DIR/ai/backlog.md}"
FEATURES_DIR="$PROJECT_DIR/ai/features"
QA_DIR="$PROJECT_DIR/ai/qa"
INBOX_DIR="${INBOX_DIR:-$PROJECT_DIR/ai/inbox}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/ai/diary/vps-logs}"
CLAUDE_PERMISSION_FLAGS="${CLAUDE_PERMISSION_FLAGS:---dangerously-skip-permissions}"
MAX_SPECS="${1:-20}"
ONE_ONLY=false

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --one) ONE_ONLY=true ;;
        --check)
            echo -e "${BLUE}DLD QA Loop - Check Mode${NC}"
            echo "Specs done but not QA'd:"
            _found=0
            if [[ -f "$BACKLOG_FILE" ]]; then
                while IFS= read -r line; do
                    spec_id=$(echo "$line" | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1)
                    if [[ -n "$spec_id" ]]; then
                        # Check if QA report already exists
                        if ! ls "$QA_DIR/${spec_id}"-* &>/dev/null; then
                            echo "  - $spec_id (needs QA)"
                            _found=$((_found + 1))
                        fi
                    fi
                done < <(grep -E '\|\s*done\s*\|' "$BACKLOG_FILE" 2>/dev/null || true)
            fi
            if [[ $_found -eq 0 ]]; then
                echo "  (none — all done specs have QA reports)"
            fi
            exit 0
            ;;
        [0-9]*) MAX_SPECS="$arg" ;;
    esac
done

mkdir -p "$QA_DIR" "$LOG_DIR" "$INBOX_DIR"

# Validate prerequisites
if [[ ! -f "$BACKLOG_FILE" ]]; then
    echo -e "${RED}Error: $BACKLOG_FILE not found${NC}"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: claude CLI not found${NC}"
    exit 1
fi

echo -e "${BLUE}"
echo "  ___  ___    _"
echo " / _ \\/ _ |  | |"
echo "| (_) | _|| _| |_"
echo " \\__\\_\\_| |_____|"
echo -e "${NC}"
echo "DLD QA Loop — User-Perspective Testing"
echo ""

# Find done specs that haven't been QA'd
PENDING_QA=()
while IFS= read -r line; do
    spec_id=$(echo "$line" | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1)
    if [[ -n "$spec_id" ]]; then
        # Check if QA report already exists (ok or bugs)
        if ! ls "$QA_DIR/${spec_id}"-* &>/dev/null; then
            PENDING_QA+=("$spec_id")
        fi
    fi
done < <(grep -E '\|\s*done\s*\|' "$BACKLOG_FILE" 2>/dev/null || true)

if [[ ${#PENDING_QA[@]} -eq 0 ]]; then
    echo "No specs pending QA. All done specs have been tested."
    exit 0
fi

echo "Found ${#PENDING_QA[@]} spec(s) pending QA"
echo ""

PASSED=0
FAILED=0
ITERATION=0

notify() {
    if [[ -x "$SCRIPT_DIR/notify.sh" ]]; then
        "$SCRIPT_DIR/notify.sh" "$@" || true
    fi
}

for spec_id in "${PENDING_QA[@]}"; do
    ITERATION=$((ITERATION + 1))
    if [[ $ITERATION -gt $MAX_SPECS ]]; then
        break
    fi

    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE} QA [$ITERATION/${#PENDING_QA[@]}]: $spec_id${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"

    # Find spec file
    SPEC_FILE=$(find "$FEATURES_DIR" -maxdepth 1 -name "${spec_id}*" -type f 2>/dev/null | head -1)
    if [[ -z "$SPEC_FILE" ]]; then
        echo -e "${YELLOW}Spec file not found for $spec_id — skipping${NC}"
        continue
    fi

    # Get git diff for what was changed (last commits mentioning this spec)
    DIFF_SUMMARY=$(cd "$PROJECT_DIR" && git log --oneline --all --grep="$spec_id" 2>/dev/null | head -5 || echo "no commits found")

    LOG_FILE="$LOG_DIR/qa-${spec_id}.log"

    # Build QA prompt
    PROMPT="You are a QA tester. Read the agent prompt from template/.claude/agents/qa-tester.md for your full instructions.

Spec to test: $spec_id
Spec file: $SPEC_FILE
Recent commits: $DIFF_SUMMARY

Read the spec file first, then test the feature as a real user would.
Write your QA report to stdout in the format described in qa-tester.md.

IMPORTANT: At the very end of your output, on a separate line, write exactly one of:
QA_VERDICT: PASS
QA_VERDICT: FAIL
QA_VERDICT: WARN"

    # Run Claude QA
    set +e
    OUTPUT=$(cd "$PROJECT_DIR" && claude --print \
        $CLAUDE_PERMISSION_FLAGS \
        --max-turns 30 \
        "$PROMPT" 2>&1 | tee "$LOG_FILE")
    EXIT_CODE=$?
    set -e

    # Parse verdict from output
    VERDICT=$(echo "$OUTPUT" | grep -oE 'QA_VERDICT: (PASS|FAIL|WARN)' | tail -1 | cut -d' ' -f2)

    if [[ -z "$VERDICT" ]]; then
        VERDICT="UNKNOWN"
    fi

    # Get spec title for report
    SPEC_TITLE=$(head -5 "$SPEC_FILE" | grep -E '^#' | head -1 | sed 's/^#* //')

    case "$VERDICT" in
        PASS)
            echo -e "${GREEN}✅ QA PASS: $spec_id${NC}"
            # Save OK report
            cat > "$QA_DIR/${spec_id}-ok.md" << EOF
# QA Report: $spec_id — PASS

**Spec:** $SPEC_TITLE
**Date:** $(date -u '+%Y-%m-%d %H:%M UTC')
**Verdict:** ✅ PASS

---

$(echo "$OUTPUT" | head -200)
EOF
            PASSED=$((PASSED + 1))
            notify "✅ QA PASS: $spec_id — $SPEC_TITLE"
            ;;

        FAIL|WARN)
            echo -e "${RED}❌ QA $VERDICT: $spec_id — bugs found${NC}"
            # Save bugs to inbox for Spark to pick up
            BUGS_FILE="$INBOX_DIR/${spec_id}-qa-bugs.md"
            cat > "$BUGS_FILE" << EOF
# QA Bugs: $spec_id

**Source:** qa-loop
**Spec:** $SPEC_TITLE
**Date:** $(date -u '+%Y-%m-%d %H:%M UTC')
**QA Verdict:** $VERDICT

---

QA тестирование нашло проблемы в $spec_id ($SPEC_TITLE).

Создай отдельные BUG-спеки для каждого найденного бага ниже.
Каждый баг = отдельная спека в backlog.

## QA Report

$(echo "$OUTPUT" | head -300)
EOF
            # Also save to QA dir so we don't re-test
            cat > "$QA_DIR/${spec_id}-bugs.md" << EOF
# QA Report: $spec_id — $VERDICT

**Spec:** $SPEC_TITLE
**Date:** $(date -u '+%Y-%m-%d %H:%M UTC')
**Verdict:** ❌ $VERDICT
**Bugs filed:** $BUGS_FILE

---

$(echo "$OUTPUT" | head -200)
EOF
            FAILED=$((FAILED + 1))
            notify "❌ QA $VERDICT: $spec_id — $SPEC_TITLE. Bugs filed to inbox."
            ;;

        *)
            echo -e "${YELLOW}⚠️ QA inconclusive for $spec_id${NC}"
            # Don't create report — will retry next run
            notify "⚠️ QA inconclusive: $spec_id — will retry"
            ;;
    esac

    if $ONE_ONLY; then
        echo "One-only mode — stopping."
        break
    fi

    sleep 2
done

echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo "QA Complete: $PASSED passed, $FAILED with bugs"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Notify summary
if [[ $((PASSED + FAILED)) -gt 0 ]]; then
    notify "QA done: $PASSED passed, $FAILED with bugs (out of ${#PENDING_QA[@]} pending)"
fi
