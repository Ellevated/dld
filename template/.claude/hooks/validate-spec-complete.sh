#!/bin/bash
# Block git commit if spec has unfilled Impact Tree checkboxes
#
# This hook ensures that Impact Tree Analysis is completed before committing.
# It checks for unchecked boxes (- [ ]) in the Impact Tree section of feature specs.

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // ""')

# Only check for git commit
if [[ "$command" != *"git commit"* ]]; then
    exit 0
fi

# Find spec in current changes
spec_file=$(git diff --cached --name-only | grep -E "^ai/features/.*\.md$" | head -1)

if [ -n "$spec_file" ] && [ -f "$spec_file" ]; then
    # Check for unfilled checkboxes in Impact Tree section
    if grep -A 50 "## Impact Tree Analysis" "$spec_file" | grep -q "\- \[ \]"; then
        cat << 'EOF'
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "permissionDecisionReason": "Spec has unfilled Impact Tree checkboxes!\n\nComplete the Impact Tree Analysis before committing:\n1. Fill all checkboxes in Impact Tree section\n2. Ensure grep results are recorded\n3. Verify all found files are in Allowed Files\n\nSee: CLAUDE.md -> Impact Tree Analysis"
  }
}
EOF
        exit 0
    fi
fi

exit 0
