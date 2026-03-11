#!/usr/bin/env bash
# scripts/vps/nexus-cache-refresh.sh
# Cron script: refresh Nexus project context into local JSON cache files.
# Runs every 5 min via cron (installed by setup-vps.sh --phase3).
# Also triggered on-demand by /nexussync Telegram command.
#
# Cache dir: /var/dld/nexus-cache/{project_id}.json
# Resilience: if Nexus CLI fails, stale cache files remain (last-known-good).
set -euo pipefail

CACHE_DIR="${NEXUS_CACHE_DIR:-/var/dld/nexus-cache}"
mkdir -p "$CACHE_DIR"

# Find Nexus CLI (bootstrap or nexus)
NEXUS_BIN=""
if command -v nexus &>/dev/null; then
    NEXUS_BIN="nexus"
elif command -v bootstrap &>/dev/null; then
    NEXUS_BIN="bootstrap"
else
    echo "[nexus-cache] ERROR: nexus/bootstrap CLI not found in PATH" >&2
    exit 1
fi

# Get list of project IDs
PROJECT_IDS=$("$NEXUS_BIN" list-projects --ids 2>/dev/null) || {
    echo "[nexus-cache] WARN: list-projects failed — using stale cache" >&2
    exit 0
}

if [[ -z "$PROJECT_IDS" ]]; then
    echo "[nexus-cache] No projects found in Nexus"
    exit 0
fi

COUNT=0
while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    # Atomic write: tmp file + mv (prevents partial reads by orchestrator)
    if "$NEXUS_BIN" get-project-context "$pid" > "${CACHE_DIR}/${pid}.json.tmp" 2>/dev/null; then
        mv "${CACHE_DIR}/${pid}.json.tmp" "${CACHE_DIR}/${pid}.json"
        COUNT=$((COUNT + 1))
    else
        rm -f "${CACHE_DIR}/${pid}.json.tmp"
        echo "[nexus-cache] WARN: get-project-context failed for ${pid}" >&2
    fi
done <<< "$PROJECT_IDS"

echo "[nexus-cache] Refreshed ${COUNT} project(s) in ${CACHE_DIR}"
