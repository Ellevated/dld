#!/usr/bin/env bash
# scripts/vps/cleanup-lifecycle-drift.sh
# One-shot operator helper to recover from dirty ai/lifecycle/ state in a project.
#
# Used after TECH-194 to clean up pre-existing drift from the env=env bug in
# lifecycle.py. Safe to run repeatedly (idempotent).
#
# Strategy: HEAD is the canonical SoT for lifecycle state (ADR-023). Any WT
# divergence is stale — atomic plumbing already wrote the correct value.
#   - staged file (M  /A  /D  )  -> `git restore --staged` + `git checkout HEAD --`
#   - modified WT (` M`)        -> `git checkout HEAD --` (revert to HEAD)
#   - deleted WT  (` D`)        -> `git checkout HEAD --` (restore from HEAD)
#   - untracked   (`??`)        -> ignored (operator must remove manually)
#
# Usage:
#   bash scripts/vps/cleanup-lifecycle-drift.sh [project_path]
#   bash scripts/vps/cleanup-lifecycle-drift.sh                      # all from projects.json
#   bash scripts/vps/cleanup-lifecycle-drift.sh /home/dld/projects/awardybot   # one project
#
# Exit codes:
#   0 — all projects clean (or successfully cleaned)
#   1 — projects.json missing or no targets
#   2 — at least one project still dirty after cleanup (untracked files)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECTS_FILE="${PROJECTS_JSON:-${SCRIPT_DIR}/projects.json}"

clean_project() {
    local proj="$1"
    if [[ ! -d "${proj}/.git" && ! -f "${proj}/.git" ]]; then
        echo "[SKIP] ${proj}: not a git repo"
        return 0
    fi
    if [[ ! -d "${proj}/ai/lifecycle" ]]; then
        echo "[SKIP] ${proj}: no ai/lifecycle/ directory"
        return 0
    fi
    local status_before
    status_before=$(git -C "${proj}" status --porcelain ai/lifecycle/ 2>/dev/null || true)
    if [[ -z "$status_before" ]]; then
        echo "[OK]   ${proj}: lifecycle already clean"
        return 0
    fi
    echo "[FIX]  ${proj}: drift detected"
    echo "$status_before" | sed 's/^/         /'
    # Unstage everything in ai/lifecycle/ first (covers M  / A  / D  / R  / C )
    git -C "${proj}" restore --staged ai/lifecycle/ 2>/dev/null || true
    # Restore WT to HEAD (covers ` M`, ` D`, ` A` after unstage)
    git -C "${proj}" checkout HEAD -- ai/lifecycle/ 2>/dev/null || true
    local status_after
    status_after=$(git -C "${proj}" status --porcelain ai/lifecycle/ 2>/dev/null || true)
    if [[ -z "$status_after" ]]; then
        echo "[DONE] ${proj}: lifecycle clean"
        return 0
    fi
    echo "[WARN] ${proj}: residual drift (likely untracked):"
    echo "$status_after" | sed 's/^/         /'
    return 2
}

# Mode 1: explicit project path
if [[ $# -ge 1 && -n "${1:-}" ]]; then
    clean_project "$1"
    exit $?
fi

# Mode 2: iterate projects.json
if [[ ! -f "$PROJECTS_FILE" ]]; then
    echo "ERROR: projects.json not found at $PROJECTS_FILE (and no project_path given)" >&2
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq required (apt install jq)" >&2
    exit 1
fi

exit_code=0
while IFS= read -r proj_path; do
    [[ -z "$proj_path" ]] && continue
    if ! clean_project "$proj_path"; then
        exit_code=2
    fi
done < <(jq -r '.[].path' "$PROJECTS_FILE")

echo "[DONE] All projects processed (exit_code=$exit_code)."
exit $exit_code
