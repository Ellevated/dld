#!/usr/bin/env bash
# scripts/vps/install-hooks-all-worktrees.sh
# Migration helper: re-set absolute core.hooksPath for all projects in projects.json.
# Safe to run repeatedly (idempotent). Reads projects.json, sets absolute hooksPath
# per project. Shared git config is inherited by all worktrees -> covers worktrees
# too without per-worktree iteration.
#
# Usage: bash install-hooks-all-worktrees.sh [path/to/projects.json]
#
# TECH-194 C1: replaces relative .git-hooks with absolute ${proj_path}/.git-hooks
# so git resolves the hook from any worktree CWD.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECTS_FILE="${1:-${PROJECTS_JSON:-${SCRIPT_DIR}/projects.json}}"

if [[ ! -f "$PROJECTS_FILE" ]]; then
    echo "ERROR: projects.json not found at $PROJECTS_FILE" >&2
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq required (apt install jq)" >&2
    exit 1
fi

while IFS= read -r proj_path; do
    [[ -z "$proj_path" ]] && continue
    # Accept both bare .git dir (main repo) and .git file (worktree pointer)
    if [[ ! -d "${proj_path}/.git" && ! -f "${proj_path}/.git" ]]; then
        echo "[SKIP] ${proj_path}: not a git repo"
        continue
    fi
    abs_hooks="${proj_path}/.git-hooks"
    if [[ ! -d "$abs_hooks" ]]; then
        echo "[SKIP] ${proj_path}: no ${abs_hooks} directory"
        continue
    fi
    current=$(git -C "${proj_path}" config core.hooksPath 2>/dev/null || echo "")
    if [[ "$current" == "$abs_hooks" ]]; then
        echo "[OK]   ${proj_path}: already absolute"
        continue
    fi
    git -C "${proj_path}" config core.hooksPath "$abs_hooks"
    echo "[FIX]  ${proj_path}: core.hooksPath=${abs_hooks} (was: ${current:-<unset>})"
done < <(jq -r '.[].path' "$PROJECTS_FILE")

echo "[DONE] All projects processed."
