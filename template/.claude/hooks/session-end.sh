#!/bin/bash
# Session End Hook - soft reminder about diary entries
# NEVER blocks, only reminds

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
INDEX_FILE="$PROJECT_DIR/ai/diary/index.md"

# Count pending entries from index.md (source of truth)
count_pending() {
    if [ -f "$INDEX_FILE" ]; then
        grep -c "| pending |" "$INDEX_FILE" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

PENDING_COUNT=$(count_pending)

# Always approve stop - just add soft reminder if needed
if [ "$PENDING_COUNT" -gt 5 ]; then
    cat << EOF
{
  "decision": "approve",
  "reason": "Reminder: $PENDING_COUNT pending diary entries. Consider /reflect when convenient."
}
EOF
else
    echo '{}'
fi
