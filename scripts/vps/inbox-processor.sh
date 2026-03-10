#!/usr/bin/env bash
# inbox-processor.sh — Convert ideas from ai/inbox/ into specs via Spark
#
# Each idea file gets processed by claude --print with /spark in headless mode.
# Spark creates spec in ai/features/ and adds to ai/backlog.md.
# Processed ideas move to ai/inbox/done/.
#
# Usage:
#   ./scripts/vps/inbox-processor.sh           # Process all pending ideas
#   ./scripts/vps/inbox-processor.sh --dry-run # Show what would be processed
#   ./scripts/vps/inbox-processor.sh --one     # Process only first idea

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load config
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a; source "$SCRIPT_DIR/.env"; set +a
fi

INBOX_DIR="${INBOX_DIR:-$PROJECT_DIR/ai/inbox}"
DONE_DIR="$INBOX_DIR/done"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/ai/diary/vps-logs}"
CLAUDE_PERMISSION_FLAGS="${CLAUDE_PERMISSION_FLAGS:---dangerously-skip-permissions}"
MAX_BUDGET="${MAX_BUDGET_PER_SPEC:-5.00}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=false
ONE_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --one) ONE_ONLY=true ;;
    esac
done

mkdir -p "$DONE_DIR" "$LOG_DIR"

echo -e "${BLUE}DLD Inbox Processor${NC}"
echo "Project: $PROJECT_DIR"
echo "Inbox: $INBOX_DIR"

# Find pending ideas (exclude done/ directory)
PENDING_FILES=()
if [[ -d "$INBOX_DIR" ]]; then
    while IFS= read -r -d '' file; do
        PENDING_FILES+=("$file")
    done < <(find "$INBOX_DIR" -maxdepth 1 -name "*.md" -type f -print0 | sort -z)
fi

if [[ ${#PENDING_FILES[@]} -eq 0 ]]; then
    echo "No pending ideas in inbox."
    exit 0
fi

echo "Found ${#PENDING_FILES[@]} pending idea(s)"

if $DRY_RUN; then
    echo -e "\n${YELLOW}DRY RUN — would process:${NC}"
    for f in "${PENDING_FILES[@]}"; do
        echo "  - $(basename "$f")"
    done
    exit 0
fi

PROCESSED=0
FAILED=0

for idea_file in "${PENDING_FILES[@]}"; do
    IDEA_NAME="$(basename "$idea_file" .md)"
    LOG_FILE="$LOG_DIR/inbox-${IDEA_NAME}.log"

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE} Processing: $IDEA_NAME${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"

    # Read idea content (skip metadata header)
    IDEA_TEXT=$(sed -n '/^---$/,$ { /^---$/d; p; }' "$idea_file")
    if [[ -z "$IDEA_TEXT" ]]; then
        # No --- separator — use full content
        IDEA_TEXT=$(cat "$idea_file")
    fi

    # Build prompt for Spark — let it work naturally, but autonomously
    PROMPT="/spark

${IDEA_TEXT}

---
Ты работаешь автономно на VPS. Человека рядом нет.
Постарайся выполнить самостоятельно. Если нужны ответы на уточняющие вопросы — спроси у консилиума (/council).
Приоритет P1 если в идее не указано иначе."

    # Run Claude in headless mode
    set +e
    cd "$PROJECT_DIR"
    claude --print \
        $CLAUDE_PERMISSION_FLAGS \
        --max-turns 50 \
        "$PROMPT" \
        > "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    set -e

    if [[ $EXIT_CODE -eq 0 ]]; then
        echo -e "${GREEN}Done: $IDEA_NAME${NC}"
        mv "$idea_file" "$DONE_DIR/"
        PROCESSED=$((PROCESSED + 1))
    else
        echo -e "${RED}Failed: $IDEA_NAME (exit=$EXIT_CODE)${NC}"
        echo "Log: $LOG_FILE"
        FAILED=$((FAILED + 1))
    fi

    if $ONE_ONLY; then
        echo "One-only mode — stopping."
        break
    fi

    # Brief pause between specs
    sleep 3
done

echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo "Processed: $PROCESSED | Failed: $FAILED"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Send notification if notify.sh exists
if [[ -x "$SCRIPT_DIR/notify.sh" ]]; then
    "$SCRIPT_DIR/notify.sh" "Inbox processed: $PROCESSED done, $FAILED failed"
fi
