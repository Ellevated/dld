#!/usr/bin/env bash
set -euo pipefail

# smoke-test.sh - Validates DLD project structure created from template/
#
# Tests that copying template/ produces a valid DLD project with:
# - All required files present
# - Valid JSON configuration
# - Non-empty critical files

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0

# Temp directory for test
TEMP_DIR=""

# Cleanup on exit
cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
        echo "Cleaned up temp directory"
    fi
}
trap cleanup EXIT

# Logging functions
log_test() {
    echo -e "${YELLOW}[TEST]${NC} $1"
    TESTS_RUN=$((TESTS_RUN + 1))
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1" >&2
    exit 1
}

log_info() {
    echo -e "[INFO] $1"
}

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_DIR="$PROJECT_ROOT/template"

# Verify template directory exists
if [ ! -d "$TEMPLATE_DIR" ]; then
    log_fail "Template directory not found: $TEMPLATE_DIR"
fi

log_info "Starting smoke test for DLD template structure"
log_info "Template: $TEMPLATE_DIR"

# Check Node.js availability (required for JSON validation)
if ! command -v node >/dev/null 2>&1; then
    log_fail "Node.js not found. Install Node.js 18+ to run smoke tests."
fi

# Create temp directory
TEMP_DIR=$(mktemp -d)
TEST_PROJECT="$TEMP_DIR/test-project"

log_info "Created temp directory: $TEMP_DIR"

# Copy template to temp directory
log_test "Copying template to temp directory"
cp -r "$TEMPLATE_DIR" "$TEST_PROJECT"
log_pass "Template copied successfully"

# Test 1: Root files
log_test "Checking root files"
if [ ! -f "$TEST_PROJECT/CLAUDE.md" ]; then
    log_fail "Missing CLAUDE.md"
fi
if [ ! -s "$TEST_PROJECT/CLAUDE.md" ]; then
    log_fail "CLAUDE.md is empty"
fi
log_pass "Root files present and non-empty"

# Test 1b: README.md and .gitignore
log_test "Checking README.md and .gitignore"
if [ ! -f "$TEST_PROJECT/README.md" ]; then
    log_fail "Missing README.md"
fi
if [ ! -f "$TEST_PROJECT/.gitignore" ]; then
    log_fail "Missing .gitignore"
fi
log_pass "README.md and .gitignore present"

# Test 2: .claude/settings.json
log_test "Checking .claude/settings.json"
SETTINGS_FILE="$TEST_PROJECT/.claude/settings.json"
if [ ! -f "$SETTINGS_FILE" ]; then
    log_fail "Missing .claude/settings.json"
fi
# Validate JSON
if ! node -e "JSON.parse(require('fs').readFileSync(0,'utf-8'))" < "$SETTINGS_FILE" 2>/dev/null; then
    log_fail ".claude/settings.json is not valid JSON"
fi
log_pass ".claude/settings.json is valid JSON"

# Test 3: Hooks
log_test "Checking .claude/hooks"
HOOKS_DIR="$TEST_PROJECT/.claude/hooks"
if [ ! -f "$HOOKS_DIR/README.md" ]; then
    log_fail "Missing .claude/hooks/README.md"
fi

REQUIRED_HOOKS=(
    "pre-bash.mjs"
    "pre-edit.mjs"
    "post-edit.mjs"
    "prompt-guard.mjs"
    "session-end.mjs"
    "validate-spec-complete.mjs"
    "utils.mjs"
    "run-hook.mjs"
)

for hook in "${REQUIRED_HOOKS[@]}"; do
    if [ ! -f "$HOOKS_DIR/$hook" ]; then
        log_fail "Missing hook: .claude/hooks/$hook"
    fi
done
log_pass "All required hooks present (${#REQUIRED_HOOKS[@]} files)"

# Test 4: Skills
log_test "Checking .claude/skills"
SKILLS_DIR="$TEST_PROJECT/.claude/skills"

REQUIRED_SKILLS=(
    "spark"
    "autopilot"
    "council"
    "planner"
    "coder"
    "tester"
    "review"
    "scout"
    "audit"
    "reflect"
    "skill-writer"
    "bootstrap"
)

for skill in "${REQUIRED_SKILLS[@]}"; do
    if [ ! -f "$SKILLS_DIR/$skill/SKILL.md" ]; then
        log_fail "Missing skill: .claude/skills/$skill/SKILL.md"
    fi
done
log_pass "All required skills present (${#REQUIRED_SKILLS[@]} skills)"

# Test 5: Agents
log_test "Checking .claude/agents"
AGENTS_DIR="$TEST_PROJECT/.claude/agents"

REQUIRED_AGENTS=(
    "_shared/context-loader.md"
    "_shared/context-updater.md"
    "planner.md"
    "coder.md"
    "tester.md"
    "review.md"
    "scout.md"
)

for agent in "${REQUIRED_AGENTS[@]}"; do
    if [ ! -f "$AGENTS_DIR/$agent" ]; then
        log_fail "Missing agent: .claude/agents/$agent"
    fi
done
log_pass "All required agents present (${#REQUIRED_AGENTS[@]} files)"

# Test 6: Rules
log_test "Checking .claude/rules"
RULES_DIR="$TEST_PROJECT/.claude/rules"

REQUIRED_RULES=(
    "architecture.md"
    "dependencies.md"
    "domains/_template.md"
    "localization.md"
)

for rule in "${REQUIRED_RULES[@]}"; do
    if [ ! -f "$RULES_DIR/$rule" ]; then
        log_fail "Missing rule: .claude/rules/$rule"
    fi
done
log_pass "All required rules present (${#REQUIRED_RULES[@]} files)"

# Test 7: AI directory structure
log_test "Checking ai/ directory structure"
AI_DIR="$TEST_PROJECT/ai"

REQUIRED_AI_FILES=(
    "backlog.md"
    "ideas.md"
    "archive.md"
    "diary/index.md"
)

for file in "${REQUIRED_AI_FILES[@]}"; do
    if [ ! -f "$AI_DIR/$file" ]; then
        log_fail "Missing ai file: ai/$file"
    fi
done
log_pass "All required ai/ files present (${#REQUIRED_AI_FILES[@]} files)"

# Final summary
echo ""
echo "========================================"
echo -e "${GREEN}SMOKE TEST SUMMARY${NC}"
echo "========================================"
echo "Tests run:    $TESTS_RUN"
echo "Tests passed: $TESTS_PASSED"
echo ""

if [ "$TESTS_RUN" -eq "$TESTS_PASSED" ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
