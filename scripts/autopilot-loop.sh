#!/usr/bin/env bash
# autopilot-loop.sh - Long-running autonomous spec execution loop
# Each spec gets a fresh Claude context. Memory persists via files.
#
# Usage:
#   ./scripts/autopilot-loop.sh              # Run max 20 iterations
#   ./scripts/autopilot-loop.sh 50           # Run max 50 iterations
#   ./scripts/autopilot-loop.sh --check      # Show next queued spec only

set -euo pipefail

# Configuration
MAX_ITERATIONS="${1:-20}"
BACKLOG_FILE="ai/backlog.md"
PROGRESS_FILE="ai/diary/autopilot-progress.md"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
if [[ "${1:-}" == "--check" ]]; then
    echo -e "${BLUE}DLD Autopilot Loop - Check Mode${NC}"
    SPEC_ID=$(grep -E '\|\s*(queued|resumed)\s*\|' "$BACKLOG_FILE" 2>/dev/null | head -1 | \
              grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || echo "")
    if [[ -z "$SPEC_ID" ]]; then
        echo "No queued/resumed specs found."
        exit 0
    fi
    echo "Next spec: $SPEC_ID"
    grep "$SPEC_ID" "$BACKLOG_FILE"
    exit 0
fi

# Validate prerequisites
if [[ ! -f "$BACKLOG_FILE" ]]; then
    echo -e "${RED}Error: $BACKLOG_FILE not found${NC}"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: claude CLI not found${NC}"
    echo "Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# Initialize progress file
mkdir -p "$(dirname "$PROGRESS_FILE")"
if [[ ! -f "$PROGRESS_FILE" ]]; then
    cat > "$PROGRESS_FILE" << 'EOF'
# Autopilot Loop Progress

Progress log for autonomous spec execution.
Each spec = fresh Claude context. Memory persists via files.

---

EOF
fi

# Add session header
{
    echo ""
    echo "## Session: $(date '+%Y-%m-%d %H:%M')"
    echo ""
} >> "$PROGRESS_FILE"

echo -e "${BLUE}"
echo "  ___  _    ___"
echo " |   \| |  |   \\"
echo " | |) | |__| |) |"
echo " |___/|____|___/"
echo ""
echo -e "${NC}"
echo "DLD Autopilot Loop - Fresh Context per Spec"
echo "Max iterations: $MAX_ITERATIONS"
echo ""

ITERATION=0

while [[ $ITERATION -lt $MAX_ITERATIONS ]]; do
    ITERATION=$((ITERATION + 1))

    # 1. Get next queued/resumed spec from backlog
    SPEC_ID=$(grep -E '\|\s*(queued|resumed)\s*\|' "$BACKLOG_FILE" 2>/dev/null | head -1 | \
              grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || echo "")

    # 2. Exit if no more queued
    if [[ -z "$SPEC_ID" ]]; then
        echo -e "${GREEN}=== ALL SPECS COMPLETE ===${NC}"
        echo "Completed at iteration $ITERATION"
        {
            echo "### Result: ALL COMPLETE"
            echo "Finished: $(date '+%Y-%m-%d %H:%M')"
            echo "Total iterations: $ITERATION"
        } >> "$PROGRESS_FILE"
        exit 0
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} Iteration $ITERATION/$MAX_ITERATIONS: $SPEC_ID${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

    # Log iteration start
    {
        echo "### Iteration $ITERATION: $SPEC_ID"
        echo "Started: $(date '+%Y-%m-%d %H:%M')"
    } >> "$PROGRESS_FILE"

    # 3. Run Claude with fresh context
    # --print captures output, autopilot processes single spec
    set +e
    OUTPUT=$(claude --print "autopilot $SPEC_ID" 2>&1 | tee /dev/stderr)
    EXIT_CODE=$?
    set -e

    # 4. Log result
    echo "Exit code: $EXIT_CODE" >> "$PROGRESS_FILE"

    # 5. Check updated status in backlog
    STATUS=$(grep "$SPEC_ID" "$BACKLOG_FILE" 2>/dev/null | grep -oE 'done|blocked|in_progress|queued' | head -1 || echo "unknown")
    echo "Status: $STATUS" >> "$PROGRESS_FILE"

    # 6. Handle blocked - requires human intervention
    if [[ "$STATUS" == "blocked" ]]; then
        echo -e "${RED}=== BLOCKED: $SPEC_ID ===${NC}"
        echo "Human intervention required. Check spec for ACTION REQUIRED."
        {
            echo "**BLOCKED** - Human intervention required"
            echo "Stopped: $(date '+%Y-%m-%d %H:%M')"
        } >> "$PROGRESS_FILE"
        exit 1
    fi

    # 7. Handle still in_progress (incomplete - may need retry)
    if [[ "$STATUS" == "in_progress" ]]; then
        echo -e "${YELLOW}=== WARNING: $SPEC_ID still in_progress ===${NC}"
        echo "Session may have ended early. Will retry next iteration."
        echo "**WARNING** - Still in_progress, will retry" >> "$PROGRESS_FILE"
    fi

    # 8. Log completion
    if [[ "$STATUS" == "done" ]]; then
        echo -e "${GREEN}=== DONE: $SPEC_ID ===${NC}"
        echo "**DONE**" >> "$PROGRESS_FILE"
    fi

    echo "Completed: $(date '+%Y-%m-%d %H:%M')" >> "$PROGRESS_FILE"
    echo "" >> "$PROGRESS_FILE"

    # Brief pause between iterations
    sleep 2
done

echo -e "${YELLOW}=== MAX ITERATIONS REACHED ===${NC}"
echo "Reached $MAX_ITERATIONS iterations. May need to continue."
{
    echo "### Result: MAX ITERATIONS"
    echo "Stopped at: $(date '+%Y-%m-%d %H:%M')"
} >> "$PROGRESS_FILE"
exit 2
