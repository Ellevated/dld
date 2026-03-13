#!/usr/bin/env bats
# scripts/vps/tests/bash/test_inbox_processor.bats
# Contract tests for inbox-processor.sh.
#
# Run:  bats scripts/vps/tests/bash/test_inbox_processor.bats
#   or: cd scripts/vps/tests/bash && bats test_inbox_processor.bats

load 'setup'

setup() {
    create_shims
    PROJECT_DIR="$(create_project_dir)"
    PATCHED_SCRIPT="$(create_patched_script)"
}


# ---------------------------------------------------------------------------
# EC-1: skip file that is not "new" (Status: processing)
# ---------------------------------------------------------------------------

@test "skip file with Status: processing — exits 0, no pueue call" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "spark" "processing"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    [[ "$output" == *"Skipping (not new)"* ]]
    [ ! -f "${BATS_TEST_TMPDIR}/pueue.calls" ]
}


# ---------------------------------------------------------------------------
# EC-2: unknown route defaults to spark with stderr warning
# ---------------------------------------------------------------------------

@test "unknown route defaults to spark — warning in output, pueue called" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "badroute" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    [[ "$output" == *"Unknown route 'badroute', defaulting to spark"* ]]
    [ -f "${BATS_TEST_TMPDIR}/pueue.calls" ]
}


# ---------------------------------------------------------------------------
# EC-3: file is moved from inbox/ to inbox/done/ after processing
# ---------------------------------------------------------------------------

@test "file moved to done/ after successful processing" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "my-task.md" "spark" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/my-task.md"

    [ "$status" -eq 0 ]
    [ ! -f "${inbox_dir}/my-task.md" ]
    [ -f "${inbox_dir}/done/my-task.md" ]
}


# ---------------------------------------------------------------------------
# EC-4: Status header patched from "new" to "processing" in the moved file
# ---------------------------------------------------------------------------

@test "status patched to processing in done/ file" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "spark" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    grep -q '^\*\*Status:\*\* processing' "${inbox_dir}/done/test.md"
    ! grep -q '^\*\*Status:\*\* new' "${inbox_dir}/done/test.md"
}


# ---------------------------------------------------------------------------
# EC-5: known routes map correctly
# ---------------------------------------------------------------------------

@test "council route — output contains route=council" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "council" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    [[ "$output" == *"route=council"* ]]
}

@test "spark_bug route — output contains route=spark_bug" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "spark_bug" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    [[ "$output" == *"route=spark_bug"* ]]
}

@test "bughunt route — output contains route=bughunt" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "bughunt" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    [[ "$output" == *"route=bughunt"* ]]
}


# ---------------------------------------------------------------------------
# EC-6: missing inbox file → exit 1
# ---------------------------------------------------------------------------

@test "missing inbox file — exits 1 with File not found message" {
    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "/nonexistent/path/file.md"

    [ "$status" -eq 1 ]
    [[ "$output" == *"File not found"* ]]
}


# ---------------------------------------------------------------------------
# EC-7: pueue called with correct group name for default provider
# ---------------------------------------------------------------------------

@test "pueue called with claude-runner group for default provider" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    create_inbox_file "$inbox_dir" "test.md" "spark" "new"

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    grep -q "claude-runner" "${BATS_TEST_TMPDIR}/pueue.calls"
}


# ---------------------------------------------------------------------------
# EC-8: Provider: header in inbox file overrides project default
# ---------------------------------------------------------------------------

@test "Provider: header in file overrides default provider" {
    local inbox_dir="${BATS_TEST_TMPDIR}/inbox"
    mkdir -p "$inbox_dir"
    cat > "${inbox_dir}/test.md" <<'EOF'
# Idea: test
**Source:** telegram
**Route:** spark
**Status:** new
**Provider:** codex
---
Do something with codex
EOF

    run bash "$PATCHED_SCRIPT" "testproject" "$PROJECT_DIR" "${inbox_dir}/test.md"

    [ "$status" -eq 0 ]
    [[ "$output" == *"provider override from file: codex"* ]]
    grep -q "codex-runner" "${BATS_TEST_TMPDIR}/pueue.calls"
}
