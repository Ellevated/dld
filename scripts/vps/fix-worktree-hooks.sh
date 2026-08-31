#!/bin/bash
# Fix worktree hooks by creating .claude symlink in all worktrees
# Run this once to fix existing worktrees

set -e

ROOT=$(git worktree list --porcelain | head -1 | sed "s/^worktree //")

echo "Root repository: $ROOT"
echo ""

# Get all worktrees (skip the first one which is main repo)
fixed=0
git worktree list --porcelain | grep "^worktree " | sed "s/^worktree //" | while read worktree; do
    if [ "$worktree" = "$ROOT" ]; then
        continue
    fi

    if [ -L "$worktree/.claude" ]; then
        echo "✓ Already symlinked: $worktree/.claude"
    elif [ -d "$worktree/.claude" ]; then
        echo "⚠ Directory exists (not symlink): $worktree/.claude"
    elif [ ! -e "$worktree/.claude" ]; then
        echo "→ Creating symlink: $worktree/.claude"
        ln -s "$ROOT/.claude" "$worktree/.claude"
        fixed=$((fixed + 1))
    fi
done

echo ""
echo "Done!"
echo ""
echo "IMPORTANT: Restart Claude Code session to apply hook changes."
echo "  (Close terminal and reopen, or use 'claude --continue')"
