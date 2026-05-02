#!/usr/bin/env bash
# scripts/vps/setup-vps.sh
# One-command VPS bootstrap for DLD Multi-Project Orchestrator.
# Usage: bash setup-vps.sh
#
# Covers all Devil's Advocate traps:
#   DA-1: loginctl enable-linger (pueued survives SSH disconnect)
#   DA-2: PTB pinned to v21.9+ <22.0 (breaking changes in v22.0)
#   DA-6: Pueue v4.0.4 arch-aware binary download
#   DA-9: Claude CLI --output-format json flag verification
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# ── Shared function: sync DLD skills to global ~/.claude/skills/ ─────────────
update_skills() {
    local DLD_REPO="${DLD_REPO:-$HOME/dev/dld}"
    if [[ ! -d "$DLD_REPO/.claude/skills" ]]; then
        warn "DLD repo not found at $DLD_REPO — cannot sync skills"
        return 1
    fi
    mkdir -p ~/.claude/skills ~/.claude/rules
    rsync -a --delete "$DLD_REPO/.claude/skills/" ~/.claude/skills/
    cp "$DLD_REPO/.claude/rules/localization.md" ~/.claude/rules/localization.md 2>/dev/null || true
    ok "DLD skills synced to ~/.claude/skills/ ($(ls ~/.claude/skills/ | wc -l) skills)"
}

# ── --update-skills: standalone skills sync ──────────────────────────────────
if [[ "${1:-}" == "--update-skills" ]]; then
    update_skills
    exit 0
fi

# ── --phase3: Phase 3 incremental setup ──────────────────────────────────────
if [[ "${1:-}" == "--phase3" ]]; then
    echo "=== Phase 3 Setup ==="

    # 1. Gemini CLI check
    GEMINI_BIN="${GEMINI_PATH:-gemini}"
    if command -v "$GEMINI_BIN" &>/dev/null || [[ -x "$GEMINI_BIN" ]]; then
        ok "Gemini CLI found: $($GEMINI_BIN --version 2>/dev/null || echo 'available')"
    else
        warn "Gemini CLI not found. Install: npm install -g @google/gemini-cli"
    fi

    # 2. Pueue gemini-runner group
    pueue group add gemini-runner 2>/dev/null || true
    pueue parallel 1 --group gemini-runner 2>/dev/null || true
    ok "Pueue gemini-runner group configured (parallel=1)"

    # 3. Global DLD skills
    update_skills || warn "Skills sync failed — run manually: bash setup-vps.sh --update-skills"

    # 4. Nexus cache directory
    NEXUS_CACHE_DIR="/var/dld/nexus-cache"
    sudo mkdir -p "$NEXUS_CACHE_DIR" 2>/dev/null || mkdir -p "$NEXUS_CACHE_DIR" 2>/dev/null || true
    sudo chown "$(whoami):$(whoami)" "$NEXUS_CACHE_DIR" 2>/dev/null || true
    ok "Nexus cache directory: $NEXUS_CACHE_DIR"

    # 5. Install cron for nexus-cache-refresh.sh
    CACHE_SCRIPT="${SCRIPT_DIR}/nexus-cache-refresh.sh"
    if [[ -f "$CACHE_SCRIPT" ]]; then
        CRON_LINE="*/5 * * * * bash ${CACHE_SCRIPT} >> /var/log/dld-orchestrator/nexus-cache.log 2>&1"
        (crontab -l 2>/dev/null | grep -v "nexus-cache-refresh"; echo "$CRON_LINE") | crontab -
        ok "Cron installed: nexus-cache-refresh.sh every 5 min"
    else
        warn "nexus-cache-refresh.sh not found — cron not installed"
    fi

    # 6. GEMINI_API_KEY in .env
    if [[ -f "${SCRIPT_DIR}/.env" ]]; then
        if ! grep -q "^GEMINI_API_KEY=" "${SCRIPT_DIR}/.env"; then
            echo "GEMINI_API_KEY=" >> "${SCRIPT_DIR}/.env"
            warn "GEMINI_API_KEY added to .env — fill in your key from Google AI Studio"
        else
            ok "GEMINI_API_KEY already in .env"
        fi
    fi

    # 7. Re-apply schema (adds gemini slot idempotently)
    DB_PATH="${DB_PATH:-${SCRIPT_DIR}/orchestrator.db}"
    if [[ -f "${SCRIPT_DIR}/schema.sql" ]]; then
        sqlite3 "$DB_PATH" < "${SCRIPT_DIR}/schema.sql"
        ok "Schema updated (gemini slot seeded)"
    fi

    # 8. Cron for daily callback audit digest @ 09:00 UTC (TECH-171)
    DIGEST_SCRIPT="${SCRIPT_DIR}/audit_digest.py"
    if [[ -f "$DIGEST_SCRIPT" ]]; then
        AUDIT_LOG_PATH="${CALLBACK_AUDIT_LOG:-${SCRIPT_DIR}/callback-audit.jsonl}"
        DIGEST_CRON_LINE="0 9 * * * CALLBACK_AUDIT_LOG=${AUDIT_LOG_PATH} ${SCRIPT_DIR}/venv/bin/python3 ${DIGEST_SCRIPT} >> /var/log/dld-orchestrator/audit-digest.log 2>&1"
        (crontab -l 2>/dev/null | grep -v "audit_digest.py"; echo "$DIGEST_CRON_LINE") | crontab -
        ok "Cron installed: audit_digest.py daily @ 09:00 UTC"
    else
        warn "audit_digest.py not found — cron not installed"
    fi

    # 9. Logrotate config for callback-audit.jsonl (TECH-171)
    LOGROTATE_TEMPLATE="${SCRIPT_DIR}/logrotate.callback-audit"
    LOGROTATE_DEST="/etc/logrotate.d/dld-callback-audit"
    AUDIT_LOG_FOR_ROTATE="${CALLBACK_AUDIT_LOG:-${SCRIPT_DIR}/callback-audit.jsonl}"
    if [[ -f "$LOGROTATE_TEMPLATE" ]]; then
        if command -v logrotate &>/dev/null; then
            LOGROTATE_CONTENT=$(sed "s|{{LOG_PATH}}|${AUDIT_LOG_FOR_ROTATE}|g" "$LOGROTATE_TEMPLATE")
            if [[ -w "$(dirname "$LOGROTATE_DEST")" ]]; then
                echo "$LOGROTATE_CONTENT" > "$LOGROTATE_DEST"
                ok "logrotate config installed: ${LOGROTATE_DEST}"
            else
                # Fallback: install with sudo
                echo "$LOGROTATE_CONTENT" | sudo tee "$LOGROTATE_DEST" > /dev/null 2>/dev/null \
                    && ok "logrotate config installed (sudo): ${LOGROTATE_DEST}" \
                    || warn "logrotate install failed — run manually: sudo tee ${LOGROTATE_DEST} < ${LOGROTATE_TEMPLATE}"
            fi
        else
            warn "logrotate not found — skipping config install"
        fi
    else
        warn "logrotate.callback-audit template not found"
    fi

    echo ""
    echo "=== Phase 3 Setup complete ==="
    exit 0
fi

echo "=== DLD Multi-Project Orchestrator Setup ==="
echo ""

# ── Pre-flight checks ──────────────────────────────────────────────────────────
echo "--- Pre-flight checks ---"

# DA-1: loginctl enable-linger so pueued survives SSH disconnect
if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$(whoami)" 2>/dev/null \
        && ok "loginctl enable-linger set for $(whoami)" \
        || warn "loginctl enable-linger failed (may need sudo; run manually if needed)"
else
    warn "loginctl not found — pueued may stop on SSH disconnect (non-systemd system?)"
fi

# Python 3.12+
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if python3 -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
        ok "Python ${PY_VERSION}"
    else
        fail "Python 3.12+ required, found ${PY_VERSION}. Install: apt install python3.12"
    fi
else
    fail "python3 not found. Install: apt install python3"
fi

# sqlite3
if command -v sqlite3 &>/dev/null; then
    ok "sqlite3 $(sqlite3 --version | awk '{print $1}')"
else
    fail "sqlite3 not found. Install: apt install sqlite3"
fi

# jq
if command -v jq &>/dev/null; then
    ok "jq $(jq --version)"
else
    fail "jq not found. Install: apt install jq"
fi

# git
if command -v git &>/dev/null; then
    ok "git $(git --version | awk '{print $3}')"
else
    fail "git not found. Install: apt install git"
fi

echo ""
echo "--- Python dependencies ---"

# Create venv if not exists
if [[ ! -d "${SCRIPT_DIR}/venv" ]]; then
    python3 -m venv "${SCRIPT_DIR}/venv"
    ok "Created Python venv at ${SCRIPT_DIR}/venv"
else
    ok "Python venv already exists"
fi

# DA-2: Install PTB v21.9+ pinned below v22.0 (v22.0 has breaking message_thread_id changes)
"${SCRIPT_DIR}/venv/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt" --quiet
ok "Python requirements installed (PTB >=21.9,<22.0)"

echo ""
echo "--- Pueue setup ---"

# DA-6: Install Pueue v4.0.4 with arch detection if not already present
PUEUE_VERSION="4.0.4"
if ! command -v pueue &>/dev/null; then
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  PUEUE_ARCH="x86_64-unknown-linux-musl" ;;
        aarch64) PUEUE_ARCH="aarch64-unknown-linux-musl" ;;
        *)       fail "Unsupported architecture: ${ARCH} (supported: x86_64, aarch64)" ;;
    esac

    PUEUE_BASE="https://github.com/Nukesor/pueue/releases/download/v${PUEUE_VERSION}"
    PUEUE_BIN="pueue-${PUEUE_ARCH}"
    PUEUED_BIN="pueued-${PUEUE_ARCH}"

    echo "Downloading Pueue v${PUEUE_VERSION} for ${ARCH}..."

    # Try system-wide first, fall back to ~/.local/bin
    INSTALL_DIR="/usr/local/bin"
    if [[ ! -w "$INSTALL_DIR" ]]; then
        INSTALL_DIR="${HOME}/.local/bin"
        mkdir -p "$INSTALL_DIR"
        warn "No write access to /usr/local/bin — installing to ${INSTALL_DIR}"
        warn "Ensure ${INSTALL_DIR} is in your PATH"
    fi

    curl -fsSL "${PUEUE_BASE}/${PUEUE_BIN}" -o "${INSTALL_DIR}/pueue"
    curl -fsSL "${PUEUE_BASE}/${PUEUED_BIN}" -o "${INSTALL_DIR}/pueued"
    chmod +x "${INSTALL_DIR}/pueue" "${INSTALL_DIR}/pueued"
    ok "Pueue v${PUEUE_VERSION} installed to ${INSTALL_DIR}"
else
    FOUND_VER=$(pueue --version 2>/dev/null | awk '{print $NF}' || echo "unknown")
    ok "pueue already installed (${FOUND_VER})"
fi

# Start pueued if not running
if ! pueue status &>/dev/null; then
    pueued --daemonize 2>/dev/null || true
    sleep 1
    if pueue status &>/dev/null; then
        ok "pueued started"
    else
        warn "pueued may not have started — check 'pueue status' manually"
    fi
else
    ok "pueued already running"
fi

# Create groups with parallelism limits
pueue group add claude-runner 2>/dev/null || true
pueue group add codex-runner  2>/dev/null || true
pueue group add night-reviewer 2>/dev/null || true
pueue parallel 2 --group claude-runner 2>/dev/null || true
pueue parallel 1 --group codex-runner  2>/dev/null || true
pueue parallel 1 --group night-reviewer 2>/dev/null || true
ok "Pueue groups configured (claude-runner=2, codex-runner=1, night-reviewer=1)"

# Configure pueue.yml callback
PUEUE_CONFIG_DIR="${HOME}/.config/pueue"
mkdir -p "$PUEUE_CONFIG_DIR"
PUEUE_CONFIG="${PUEUE_CONFIG_DIR}/pueue.yml"
CALLBACK_LINE="${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/callback.py {{ id }} '{{ group }}' '{{ result }}'"

if [[ -f "$PUEUE_CONFIG" ]]; then
    # Patch existing file — update callback line if present, otherwise append to daemon section
    if grep -q "callback:" "$PUEUE_CONFIG"; then
        sed -i "s|callback:.*|callback: \"${CALLBACK_LINE}\"|" "$PUEUE_CONFIG"
    else
        # Append under daemon: section
        printf '  callback: "%s"\n' "${CALLBACK_LINE}" >> "$PUEUE_CONFIG"
    fi
else
    cat > "$PUEUE_CONFIG" << PUEUE_YAML
---
client:
  restart_in_place: false
  read_local_logs: true
  show_confirmation_questions: false
  show_expanded_aliases: false
  dark_mode: false
  max_status_lines: null
  status_time_format: "%H:%M:%S"
  status_datetime_format: "%Y-%m-%d\n%H:%M:%S"
daemon:
  default_parallel_tasks: 1
  pause_group_on_failure: false
  pause_all_on_failure: false
  callback: "${CALLBACK_LINE}"
  callback_log_lines: 10
shared:
  use_unix_socket: true
  host: "127.0.0.1"
  port: "6924"
PUEUE_YAML
fi
ok "Pueue callback configured in ${PUEUE_CONFIG}"

echo ""
echo "--- SQLite setup ---"

# Load DB_PATH from .env if available, else default
DB_PATH="${DB_PATH:-${SCRIPT_DIR}/orchestrator.db}"
if [[ -f "${SCRIPT_DIR}/schema.sql" ]]; then
    sqlite3 "$DB_PATH" < "${SCRIPT_DIR}/schema.sql"
    ok "SQLite database initialized: ${DB_PATH}"
else
    warn "schema.sql not found at ${SCRIPT_DIR}/schema.sql — database not initialized"
fi

echo ""
echo "--- Make scripts executable ---"
# shellcheck disable=SC2046
chmod +x $(find "${SCRIPT_DIR}" -maxdepth 1 -name "*.sh" -o -name "*.py" 2>/dev/null) 2>/dev/null || true
ok "Scripts in ${SCRIPT_DIR} made executable"

echo ""
echo "--- Environment check ---"

if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
    warn ".env not found. Create it from the template:"
    echo "  cp ${SCRIPT_DIR}/.env.example ${SCRIPT_DIR}/.env"
    echo "  # Then fill in your API keys and project paths"
else
    ok ".env exists"
fi

if [[ ! -f "${SCRIPT_DIR}/projects.json" ]]; then
    warn "projects.json not found. Create it from the template:"
    echo "  cp ${SCRIPT_DIR}/projects.json.example ${SCRIPT_DIR}/projects.json"
    echo "  # Then set your project paths, topic IDs, and providers"
else
    ok "projects.json exists"
fi

# DA-9: Verify Claude CLI supports --output-format json (required by claude-runner.sh)
CLAUDE_BIN="${CLAUDE_PATH:-claude}"
if command -v "${CLAUDE_BIN}" &>/dev/null || [[ -x "${CLAUDE_BIN}" ]]; then
    if "${CLAUDE_BIN}" --output-format json --help &>/dev/null 2>&1; then
        ok "Claude CLI found and supports --output-format json"
    else
        warn "Claude CLI found but may not support --output-format json — verify version (need >=1.x)"
    fi
else
    warn "Claude CLI not found at '${CLAUDE_BIN}'. Set CLAUDE_PATH in .env after install."
fi

echo ""
echo "--- Global CLAUDE.md ---"
GLOBAL_CLAUDE_DIR="${HOME}/.claude"
mkdir -p "$GLOBAL_CLAUDE_DIR"
if [[ -f "${SCRIPT_DIR}/global-claude-md.template" ]]; then
    cp "${SCRIPT_DIR}/global-claude-md.template" "${GLOBAL_CLAUDE_DIR}/CLAUDE.md"
    ok "Global CLAUDE.md installed at ${GLOBAL_CLAUDE_DIR}/CLAUDE.md"
else
    warn "global-claude-md.template not found — skip"
fi

echo ""
echo "--- Nexus integration (optional) ---"
if command -v nexus &>/dev/null || command -v bootstrap &>/dev/null; then
    NEXUS_BIN=$(command -v nexus || command -v bootstrap)
    if [[ ! -f "${SCRIPT_DIR}/projects.json" ]]; then
        echo "Nexus detected — attempting to populate projects.json..."
        set +e
        NEXUS_PROJECTS=$("${NEXUS_BIN}" list-projects --format json 2>/dev/null)
        set -e
        if [[ -n "$NEXUS_PROJECTS" ]] && echo "$NEXUS_PROJECTS" | jq '.' &>/dev/null; then
            echo "$NEXUS_PROJECTS" | jq '[.[] | {project_id: .name, path: .path, topic_id: null, provider: "claude", auto_approve_timeout: 30}]' > "${SCRIPT_DIR}/projects.json"
            ok "projects.json pre-populated from Nexus (review and add topic_ids manually)"
        else
            warn "Nexus list-projects failed — create projects.json manually"
        fi
    else
        ok "projects.json exists — skipping Nexus project import"
    fi
    # Try to pull GROQ_API_KEY from Nexus secrets
    if [[ -f "${SCRIPT_DIR}/.env" ]] && ! grep -q "^GROQ_API_KEY=." "${SCRIPT_DIR}/.env"; then
        set +e
        GROQ_KEY=$("${NEXUS_BIN}" get-secret GROQ_API_KEY --env prod 2>/dev/null)
        set -e
        if [[ -n "$GROQ_KEY" ]]; then
            sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=${GROQ_KEY}|" "${SCRIPT_DIR}/.env"
            ok "GROQ_API_KEY populated from Nexus secrets"
        fi
    fi
else
    ok "Nexus not found — manual projects.json setup required"
fi

echo ""
echo "--- systemd units ---"

SYSTEMD_DIR="${HOME}/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

cat > "${SYSTEMD_DIR}/dld-orchestrator.service" << EOF
[Unit]
Description=DLD Multi-Project Orchestrator
After=network.target

[Service]
Type=simple
ExecStart=${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/orchestrator.py
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${SCRIPT_DIR}/.env
MemoryMax=27G
MemorySwapMax=0
KillMode=control-group
Restart=on-failure
RestartSec=1s
RestartMaxDelaySec=60s
RestartSteps=5
StartLimitBurst=10
StartLimitIntervalSec=300s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dld-orchestrator

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload 2>/dev/null \
    && ok "systemd units installed and daemon reloaded" \
    || warn "systemctl daemon-reload failed — units written but not loaded (no systemd?)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Fill in .env:       ${SCRIPT_DIR}/.env"
echo "  2. Fill in projects:   ${SCRIPT_DIR}/projects.json"
echo ""
echo "Enable services:"
echo "  systemctl --user enable --now dld-orchestrator"
echo ""
echo "Check status:"
echo "  systemctl --user status dld-orchestrator"
echo "  journalctl --user -u dld-orchestrator -f"
