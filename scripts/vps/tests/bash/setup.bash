# scripts/vps/tests/bash/setup.bash
# Shared bats helper for inbox-processor.sh tests.

INBOX_PROCESSOR="$(cd "$(dirname "${BATS_TEST_FILENAME}")/../.." && pwd)/inbox-processor.sh"

# Create a patched copy of inbox-processor.sh that:
#   1. Does NOT source .env (avoids real credentials leaking into test env)
#   2. Does NOT prepend venv/bin to PATH (prevents real python3 overriding shims)
# The copy is placed in BATS_TEST_TMPDIR which is unique per test run.
create_patched_script() {
    local patched="${BATS_TEST_TMPDIR}/inbox-processor.sh"
    sed \
        -e 's|^\[\[ -f "\${SCRIPT_DIR}/\.env" \]\].*|# .env sourcing disabled for testing|' \
        -e 's|^\[\[ -d "\${SCRIPT_DIR}/venv" \]\].*|# venv PATH disabled for testing|' \
        "$INBOX_PROCESSOR" > "$patched"
    chmod +x "$patched"
    echo "$patched"
}

# Create shims directory with mocked binaries.
# Only pueue is strictly required — python3 calls in the script all have
# error fallbacks (|| echo "claude", || { echo "WARN..." }).
create_shims() {
    local shims="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "$shims"

    # pueue mock: record args to a file, return a fake task ID on stdout.
    # The --print-task-id flag makes the script use the printed value as PUEUE_ID.
    cat > "${shims}/pueue" <<'MOCK'
#!/usr/bin/env bash
echo "$@" >> "${BATS_TEST_TMPDIR}/pueue.calls"
echo "42"
MOCK
    chmod +x "${shims}/pueue"

    # python3 mock: swallow all invocations silently so no WARN noise in output.
    # Provider resolution falls back to "claude" if python3 fails → we return it.
    cat > "${shims}/python3" <<'MOCK'
#!/usr/bin/env bash
# If called with -c, might be provider resolution — just emit "claude".
# Otherwise exit 0 silently (DB logging, notify, etc.).
for arg in "$@"; do
    if [[ "$arg" == *"get_project_state"* ]]; then
        echo "claude"
        exit 0
    fi
done
exit 0
MOCK
    chmod +x "${shims}/python3"

    export PATH="${shims}:${PATH}"
}

# Write a minimal inbox *.md file with standard metadata headers.
# Args: dir filename route status [idea_text]
create_inbox_file() {
    local dir="$1"
    local filename="$2"
    local route="${3:-spark}"
    local status="${4:-new}"
    local idea_text="${5:-Fix the broken thing}"

    mkdir -p "$dir"
    cat > "${dir}/${filename}" <<EOF
# Idea: test
**Source:** telegram
**Route:** ${route}
**Status:** ${status}
---
${idea_text}
EOF
}

# Create a throwaway project directory the script can validate.
create_project_dir() {
    local project_dir="${BATS_TEST_TMPDIR}/project"
    mkdir -p "$project_dir"
    echo "$project_dir"
}
