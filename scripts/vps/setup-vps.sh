#!/usr/bin/env bash
# setup-vps.sh — One-command setup for DLD autonomous pipeline on VPS
#
# What it does:
#   1. Installs Python dependencies for Telegram bot
#   2. Creates ai/inbox/ directory
#   3. Creates systemd services (optional)
#   4. Validates configuration
#
# Usage:
#   ./scripts/vps/setup-vps.sh              # Interactive setup
#   ./scripts/vps/setup-vps.sh --systemd    # Also install systemd services
#   ./scripts/vps/setup-vps.sh --check      # Validate setup only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "  ___  _    ___    __   __  ___  ___"
echo " |   \| |  |   \   \ \ / / | _ \/ __|"
echo " | |) | |__| |) |   \ V /  |  _/\__ \\"
echo " |___/|____|___/     \_/   |_|  |___/"
echo -e "${NC}"
echo "DLD Autonomous Pipeline — VPS Setup"
echo ""

INSTALL_SYSTEMD=false
CHECK_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --systemd) INSTALL_SYSTEMD=true ;;
        --check) CHECK_ONLY=true ;;
    esac
done

# ── Validation ──

ERRORS=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $name"
    else
        echo -e "  ${RED}✗${NC} $name"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "Checking prerequisites..."
check "Python 3.8+" "python3 --version"
check "pip" "python3 -m pip --version"
check "Claude Code CLI" "command -v claude"
check "curl" "command -v curl"
check "tmux" "command -v tmux"
check "git" "command -v git"

echo ""
echo "Checking configuration..."
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    echo -e "  ${GREEN}✓${NC} .env file exists"
    set -a; source "$SCRIPT_DIR/.env"; set +a

    if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && "${TELEGRAM_BOT_TOKEN}" != "your_bot_token_here" ]]; then
        echo -e "  ${GREEN}✓${NC} TELEGRAM_BOT_TOKEN set"
    else
        echo -e "  ${YELLOW}!${NC} TELEGRAM_BOT_TOKEN not set (Telegram bot won't work)"
    fi

    if [[ -n "${TELEGRAM_ALLOWED_USERS:-}" ]]; then
        echo -e "  ${GREEN}✓${NC} TELEGRAM_ALLOWED_USERS set"
    else
        echo -e "  ${RED}✗${NC} TELEGRAM_ALLOWED_USERS not set (REQUIRED for security)"
        ERRORS=$((ERRORS + 1))
    fi

    if [[ -n "${GROQ_API_KEY:-}" || -n "${OPENAI_API_KEY:-}" ]]; then
        echo -e "  ${GREEN}✓${NC} Whisper API key set (${WHISPER_PROVIDER:-groq})"
    else
        echo -e "  ${YELLOW}!${NC} No Whisper API key (voice messages won't work)"
    fi
else
    echo -e "  ${RED}✗${NC} .env not found — copy from .env.example"
    echo "    cp $SCRIPT_DIR/.env.example $SCRIPT_DIR/.env"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "Checking project structure..."
check "ai/inbox/ directory" "test -d '$PROJECT_DIR/ai/inbox' || mkdir -p '$PROJECT_DIR/ai/inbox'"
check "ai/backlog.md" "test -f '$PROJECT_DIR/ai/backlog.md'"
check "scripts/autopilot-loop.sh" "test -f '$PROJECT_DIR/scripts/autopilot-loop.sh'"

if $CHECK_ONLY; then
    echo ""
    if [[ $ERRORS -eq 0 ]]; then
        echo -e "${GREEN}All checks passed!${NC}"
    else
        echo -e "${RED}$ERRORS error(s) found${NC}"
    fi
    exit $ERRORS
fi

# ── Install dependencies ──

echo ""
echo "Installing Python dependencies..."
python3 -m pip install --quiet --user \
    python-telegram-bot \
    python-dotenv \
    groq \
    openai \
    2>&1 | tail -3

echo -e "  ${GREEN}✓${NC} Python packages installed"

# ── Create directories ──

mkdir -p "$PROJECT_DIR/ai/inbox"
mkdir -p "$PROJECT_DIR/ai/diary/vps-logs"
echo -e "  ${GREEN}✓${NC} Directories created"

# ── Make scripts executable ──

chmod +x "$SCRIPT_DIR/telegram-bot.py"
chmod +x "$SCRIPT_DIR/inbox-processor.sh"
chmod +x "$SCRIPT_DIR/orchestrator.sh"
chmod +x "$SCRIPT_DIR/notify.sh"
chmod +x "$PROJECT_DIR/scripts/autopilot-loop.sh" 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Scripts made executable"

# ── Systemd services (optional) ──

if $INSTALL_SYSTEMD; then
    echo ""
    echo "Installing systemd services..."

    CLAUDE_PATH=$(which claude)
    PYTHON_PATH=$(which python3)
    CURRENT_USER=$(whoami)

    # Telegram bot service
    sudo tee /etc/systemd/system/dld-telegram-bot.service > /dev/null << EOF
[Unit]
Description=DLD Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH $SCRIPT_DIR/telegram-bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PATH=$PATH

[Install]
WantedBy=multi-user.target
EOF

    # Orchestrator service
    sudo tee /etc/systemd/system/dld-orchestrator.service > /dev/null << EOF
[Unit]
Description=DLD Orchestrator (Autonomous Pipeline)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$SCRIPT_DIR/orchestrator.sh
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
Environment=PATH=$PATH

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    echo -e "  ${GREEN}✓${NC} Systemd services installed"
    echo ""
    echo "To start:"
    echo "  sudo systemctl enable --now dld-telegram-bot"
    echo "  sudo systemctl enable --now dld-orchestrator"
    echo ""
    echo "To check logs:"
    echo "  journalctl -u dld-telegram-bot -f"
    echo "  journalctl -u dld-orchestrator -f"
fi

# ── Summary ──

echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""
echo "Quick start (tmux):"
echo ""
echo "  # Terminal 1: Telegram bot"
echo "  tmux new-session -d -s dld-bot 'python3 $SCRIPT_DIR/telegram-bot.py'"
echo ""
echo "  # Terminal 2: Orchestrator (inbox → spark → autopilot)"
echo "  tmux new-session -d -s dld-orch '$SCRIPT_DIR/orchestrator.sh'"
echo ""
echo "  # Check status"
echo "  tmux ls"
echo "  $SCRIPT_DIR/orchestrator.sh --status"
echo ""
echo "Or with systemd (recommended for production):"
echo "  $0 --systemd"
echo ""
echo "Flow:"
echo "  Telegram → ai/inbox/ → Spark (spec) → backlog → Autopilot → done"
echo ""
