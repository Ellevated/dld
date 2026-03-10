#!/usr/bin/env bash
# scripts/vps/db_exec.sh
# Bash SQLite wrapper — prepends WAL + busy_timeout PRAGMAs.
# Usage: ./db_exec.sh "SQL statement"
#   or:  echo "SQL" | ./db_exec.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="${DB_PATH:-${SCRIPT_DIR}/orchestrator.db}"

PRAGMAS="PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;"

if [[ $# -gt 0 ]]; then
    sqlite3 "$DB_PATH" "${PRAGMAS} $1"
else
    # Read from stdin
    SQL=$(cat)
    sqlite3 "$DB_PATH" "${PRAGMAS} ${SQL}"
fi
