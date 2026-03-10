#!/usr/bin/env bash
# notify.sh — Send notifications to Telegram
#
# Usage:
#   ./scripts/vps/notify.sh "message text"
#   echo "message" | ./scripts/vps/notify.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load config
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a; source "$SCRIPT_DIR/.env"; set +a
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
# Use first allowed user as notification target
CHAT_ID="${TELEGRAM_NOTIFY_CHAT_ID:-$(echo "${TELEGRAM_ALLOWED_USERS:-}" | cut -d',' -f1)}"

if [[ -z "$BOT_TOKEN" || -z "$CHAT_ID" ]]; then
    echo "[notify] Telegram not configured — printing to stdout"
    echo "$*"
    exit 0
fi

# Get message from args or stdin
if [[ $# -gt 0 ]]; then
    MESSAGE="$*"
else
    MESSAGE=$(cat)
fi

# Prepend DLD prefix
MESSAGE="🔧 DLD: ${MESSAGE}"

# Send via Telegram Bot API
curl -s -X POST \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="$CHAT_ID" \
    -d text="$MESSAGE" \
    -d parse_mode="Markdown" \
    > /dev/null 2>&1 || {
    echo "[notify] Failed to send Telegram message"
    echo "$MESSAGE"
}
