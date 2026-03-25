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
# PROJECT_DIR env var allows orchestrator to specify project path (multi-project VPS)
BASE_DIR="${PROJECT_DIR:-.}"
BACKLOG_FILE="${BASE_DIR}/ai/backlog.md"
PROGRESS_FILE="${BASE_DIR}/ai/diary/autopilot-progress.md"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Worktree cleanup functions (TECH-149: deterministic cleanup after merge)
# ---------------------------------------------------------------------------

# Derive branch prefix from SPEC_ID
_branch_prefix() {
    local spec_id="$1"
    case "$spec_id" in
        FTR-*)  echo "feature" ;;
        BUG-*)  echo "fix" ;;
        TECH-*) echo "tech" ;;
        ARCH-*) echo "arch" ;;
        *)      echo "task" ;;
    esac
}

# Clean up a single worktree + branch for a given SPEC_ID.
# Safe: skips if uncommitted changes or branch not merged.
# Idempotent: running twice is harmless.
cleanup_worktree() {
    local spec_id="${1:-}"
    [[ -z "$spec_id" ]] && return 0

    local prefix
    prefix=$(_branch_prefix "$spec_id")
    local branch="${prefix}/${spec_id}"
    local wt_dir

    # Find worktree directory
    for candidate in ".worktrees/${spec_id}" "worktrees/${spec_id}"; do
        [[ -d "${BASE_DIR}/${candidate}" ]] && wt_dir="${BASE_DIR}/${candidate}" && break
    done

    # No worktree found — nothing to clean
    [[ -z "${wt_dir:-}" ]] && return 0

    # Safety: skip if uncommitted changes
    if [[ -n "$(git -C "$wt_dir" status --porcelain 2>/dev/null)" ]]; then
        echo -e "${YELLOW}[cleanup] SKIP: $wt_dir has uncommitted changes${NC}"
        return 0
    fi

    # Safety: skip if branch not merged to develop
    if ! git -C "${BASE_DIR}" branch --merged develop 2>/dev/null | grep -q "$branch"; then
        echo -e "${YELLOW}[cleanup] SKIP: $branch not merged to develop${NC}"
        return 0
    fi

    # Remove .claude symlink first (prevent hook resolution race)
    rm -f "${wt_dir}/.claude" 2>/dev/null || true

    # Remove worktree
    git -C "${BASE_DIR}" worktree remove "$wt_dir" --force 2>/dev/null || true

    # Delete local branch (safe -d, not -D)
    git -C "${BASE_DIR}" branch -d "$branch" 2>/dev/null || true

    # Prune stale worktree references
    git -C "${BASE_DIR}" worktree prune 2>/dev/null || true

    echo -e "${GREEN}[cleanup] Removed worktree $wt_dir + branch $branch${NC}"
}

# Sweep ALL orphaned worktrees + branches + stashes.
# Called once before main loop starts.
sweep_all_orphans() {
    echo -e "${BLUE}[sweep] Checking for orphaned worktrees...${NC}"
    local found=0

    # 1. Remove orphaned worktrees (merged to develop)
    while IFS= read -r wt; do
        [[ -z "$wt" ]] && continue
        # Skip main repo worktree
        local toplevel
        toplevel=$(git -C "${BASE_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "")
        [[ "$wt" == "$toplevel" ]] && continue

        local wt_branch
        wt_branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
        [[ -z "$wt_branch" ]] && continue

        # Skip protected branches
        [[ "$wt_branch" =~ ^(main|master|develop)$ ]] && continue

        # Skip if uncommitted changes
        if [[ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]]; then
            echo -e "${YELLOW}[sweep] SKIP: $wt has uncommitted changes${NC}"
            continue
        fi

        # Only remove if merged to develop
        if git -C "${BASE_DIR}" branch --merged develop 2>/dev/null | grep -q "$wt_branch"; then
            rm -f "$wt/.claude" 2>/dev/null || true
            git -C "${BASE_DIR}" worktree remove "$wt" --force 2>/dev/null || true
            git -C "${BASE_DIR}" branch -d "$wt_branch" 2>/dev/null || true
            echo -e "${GREEN}[sweep] Removed orphan worktree: $wt ($wt_branch)${NC}"
            found=$((found + 1))
        fi
    done < <(git -C "${BASE_DIR}" worktree list --porcelain 2>/dev/null | grep '^worktree ' | awk '{print $2}')

    # 2. Prune merged local branches without worktrees
    while IFS= read -r branch; do
        branch=$(echo "$branch" | tr -d ' ')
        [[ -z "$branch" ]] && continue
        [[ "$branch" =~ ^(main|master|develop)$ ]] && continue
        git -C "${BASE_DIR}" branch -d "$branch" 2>/dev/null || true
        echo -e "${GREEN}[sweep] Pruned merged branch: $branch${NC}"
        found=$((found + 1))
    done < <(git -C "${BASE_DIR}" branch --merged develop 2>/dev/null | grep -E '^\s+(feature|fix|tech|arch)/')

    # 3. Drop orphaned autopilot stashes
    git -C "${BASE_DIR}" stash list 2>/dev/null | grep -E 'autopilot-(phase3|temp)' | \
        grep -oE 'stash@\{[0-9]+\}' | sort -t'{' -k2 -rn | \
        while read -r stash_ref; do
            git -C "${BASE_DIR}" stash drop "$stash_ref" 2>/dev/null || true
            echo -e "${GREEN}[sweep] Dropped stash: $stash_ref${NC}"
            found=$((found + 1))
        done

    # 4. Prune stale worktree references
    git -C "${BASE_DIR}" worktree prune 2>/dev/null || true

    if [[ $found -eq 0 ]]; then
        echo -e "${GREEN}[sweep] No orphans found — clean state${NC}"
    fi
}

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

# Sweep orphans from previous crashed runs before starting
sweep_all_orphans

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

    # 3.5. Backup cleanup: remove worktree if agent left it behind
    cleanup_worktree "$SPEC_ID"

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
