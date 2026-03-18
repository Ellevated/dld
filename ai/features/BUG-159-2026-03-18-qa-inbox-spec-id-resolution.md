# Bug Fix: [BUG-159] QA dispatch resolves real spec_id for inbox-originated tasks

**Status:** in_progress | **Priority:** P1 | **Risk:** R1 | **Date:** 2026-03-18

**Supersedes:** BUG-158 (band-aid: skip QA for inbox tasks entirely)

## Symptom

After autopilot processes an inbox-originated task, `pueue-callback.sh` dispatches QA with
`TASK_LABEL=inbox-20260318-XXXXXX` instead of the real spec ID (e.g., `TECH-157`).
QA can't find the spec file: `QA skipped: spec file not found for inbox-20260318-200931`.

Current band-aid (BUG-158 / existing code at line 365) just skips QA for inbox tasks entirely.
This means code changes from inbox-originated autopilot runs are **never QA-validated**.

## Root Cause (5 Whys Result)

**Why 1:** QA dispatch uses `TASK_LABEL` as spec_id, but `TASK_LABEL=inbox-YYYYMMDD`.
**Why 2:** `TASK_LABEL` comes from pueue label, set by `inbox-processor.sh` at dispatch time.
**Why 3:** `inbox-processor.sh` doesn't know the spec ID — Spark hasn't created it yet.
**Why 4:** After Spark creates the spec, no mechanism writes the spec_id back to where the callback can find it.
**Why 5:** There is no spec_id resolution layer between `TASK_LABEL` and QA dispatch.

**ROOT CAUSE:** Missing spec_id resolution mechanism. The pipeline has no way to map
`inbox-YYYYMMDD` labels back to the `TECH-NNN`/`BUG-NNN` spec IDs that Spark created.

## Cycle Flow (affected)

```
inbox-file (Status: new)
  → inbox-processor.sh (label = project:inbox-YYYYMMDD-HHMMSS)
    → Spark (creates TECH-157, commits/pushes)
      → callback fires (SKILL=spark) → phase=idle [no QA — correct]
        → orchestrator scan_backlog picks up TECH-157
          → autopilot (label = project:TECH-157) → QA works ✓

BUT if spark+autopilot run in same process (auto-handoff):
  → callback fires (SKILL=autopilot, TASK_LABEL=inbox-XXXXXX) → QA fails ✗
```

The fix ensures QA works regardless of which path autopilot takes.

## Fix Approach

Three-layer spec_id resolution in `pueue-callback.sh` + durable metadata in inbox file:

1. **Layer 1:** Extract from `TASK_LABEL` regex (existing, covers orchestrator path)
2. **Layer 2:** Extract from agent output `PREVIEW` (covers any path via grep)
3. **Layer 3:** Read `**SpecID:**` from inbox done file (durable metadata from Spark)

Supporting changes: pass `CLAUDE_CURRENT_SPEC_PATH` through `claude-runner.py` so Spark can
write metadata to the inbox file, and update Spark completion to write `**SpecID:**`.

## Impact Tree Analysis

### Step 1: UP — who uses pueue-callback.sh?
- [x] Pueue daemon (callback config) — no interface change
- [x] run-agent.sh (label format) — no change

### Step 2: DOWN — what depends on changed code?
- [x] `run-agent.sh` → `qa` skill — receives resolved spec_id (not inbox label)
- [x] `qa-loop.sh` — receives correct spec_id, finds spec file
- [x] `claude-runner.py` — passes additional env var through
- [x] Spark completion logic — writes SpecID to inbox file

### Step 3: BY TERM — grep entire project
| File | Line | Status | Action |
|------|------|--------|--------|
| pueue-callback.sh | 88-94 | target | Replace inbox-guard with spec_id resolution |
| pueue-callback.sh | 365-394 | target | Use resolved QA_SPEC_ID instead of TASK_LABEL |
| claude-runner.py | 97-100 | target | Add CLAUDE_CURRENT_SPEC_PATH to env |
| .claude/skills/spark/completion.md | post-write | target | Add SpecID write to inbox file |

### Verification
- [x] All found files added to Allowed Files

## Allowed Files

1. `scripts/vps/pueue-callback.sh` — multi-layer spec_id resolution for QA dispatch
2. `scripts/vps/claude-runner.py` — pass CLAUDE_CURRENT_SPEC_PATH to agent env
3. `.claude/skills/spark/completion.md` — add SpecID write step for headless mode

## Tasks

### Task 1: pueue-callback.sh — Multi-layer spec_id resolution

Replace the band-aid inbox guard with proper spec_id resolution.

**Step 1-3 (phase logic):** Replace the inline `^inbox-` check with a spec_id resolution
function that determines the correct spec_id for QA:

```bash
# ---------------------------------------------------------------------------
# Resolve spec_id for QA dispatch (multi-layer)
# ---------------------------------------------------------------------------
resolve_spec_id() {
    local task_label="$1" preview="$2" project_path="$3"

    # Layer 1: From TASK_LABEL (orchestrator sets label = spec_id)
    if [[ "$task_label" =~ (TECH|FTR|BUG|ARCH)-[0-9]+ ]]; then
        echo "${BASH_REMATCH[0]}"
        return 0
    fi

    # Layer 2: From agent output preview (spec_id appears in result text)
    if [[ -n "$preview" ]]; then
        local from_preview
        from_preview=$(echo "$preview" | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || true)
        if [[ -n "$from_preview" ]]; then
            echo "$from_preview"
            return 0
        fi
    fi

    # Layer 3: From inbox done file (SpecID metadata written by Spark)
    if [[ -n "$project_path" && "$task_label" =~ ^inbox- ]]; then
        local inbox_done_dir="${project_path}/ai/inbox/done"
        if [[ -d "$inbox_done_dir" ]]; then
            # Search recent done files for SpecID metadata
            local spec_from_inbox
            spec_from_inbox=$(grep -rh '\*\*SpecID:\*\*' "$inbox_done_dir"/*.md 2>/dev/null | \
                tail -1 | grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' || true)
            if [[ -n "$spec_from_inbox" ]]; then
                echo "$spec_from_inbox"
                return 0
            fi
        fi
    fi

    return 1  # No spec_id resolved
}
```

**Step 1-3 (phase update):** Use resolved spec_id for phase logic:

```bash
if [[ "$STATUS" == "done" ]]; then
    # Try to resolve spec_id for QA
    QA_SPEC_ID=$(resolve_spec_id "$TASK_LABEL" "" "" || true)
    if [[ -n "$QA_SPEC_ID" ]]; then
        NEW_PHASE="qa_pending"
    else
        # No spec_id resolvable — skip QA
        NEW_PHASE="idle"
    fi
else
    NEW_PHASE="failed"
fi
```

**Step 7 (QA dispatch):** Use multi-layer resolution with PREVIEW available:

```bash
if [[ "$STATUS" == "done" && "$SKILL" == "autopilot" ]]; then
    # ... resolve project path ...

    if [[ -n "$PROJECT_PATH" ]]; then
        # Resolve spec_id using all available signals
        QA_SPEC_ID=$(resolve_spec_id "$TASK_LABEL" "$PREVIEW" "$PROJECT_PATH" || true)

        if [[ -z "$QA_SPEC_ID" ]]; then
            echo "[callback] Skipping QA: no spec_id resolved from task_label='${TASK_LABEL}' or agent output"
            echo "[$(date)] QA skip: no spec_id task=${TASK_LABEL}" >> "$CALLBACK_LOG"
        else
            QA_LABEL="${PROJECT_ID}:qa-${QA_SPEC_ID}"
            echo "[callback] Resolved QA spec_id=${QA_SPEC_ID} (task_label=${TASK_LABEL})" >> "$CALLBACK_LOG"

            # Dispatch QA with resolved spec_id
            # (existing duplicate-check + pueue add logic, but using QA_SPEC_ID)
            ...
            pueue add --group "$RUNNER_GROUP" --label "$QA_LABEL" \
                -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" \
                "/qa ${QA_SPEC_ID}" 2>/dev/null
        fi

        # Reflect dispatch stays unconditional (existing logic unchanged)
        ...
    fi
fi
```

Remove the old `if [[ "$TASK_LABEL" =~ ^inbox- ]]` guard (line 365) — replaced by resolution logic.

### Task 2: claude-runner.py — Pass CLAUDE_CURRENT_SPEC_PATH to agent env

In `run_task()`, add `CLAUDE_CURRENT_SPEC_PATH` to the env dict (line 97-100):

```python
options = ClaudeAgentOptions(
    cwd=str(project_path),
    setting_sources=["user", "project"],
    allowed_tools=ALLOWED_TOOLS,
    permission_mode="bypassPermissions",
    max_turns=MAX_TURNS,
    env={
        "PROJECT_DIR": str(project_path),
        "CLAUDE_PROJECT_DIR": str(project_path),
        "CLAUDE_CURRENT_SPEC_PATH": os.environ.get("CLAUDE_CURRENT_SPEC_PATH", ""),
    },
)
```

This allows the Spark agent to know where the inbox file is and write SpecID metadata to it.

### Task 3: Spark completion — Write SpecID to inbox done file

Add a post-spec-creation step in `.claude/skills/spark/completion.md`:

After the "Auto-Commit + Push" section, add a new section:

```markdown
## Headless Mode: Write SpecID to Inbox File (MANDATORY)

When running in headless mode (inbox-originated), write the spec ID back to the
originating inbox file so the pipeline can map inbox labels to real spec IDs.

After spec is created and BEFORE auto-commit:

1. Check env var: `CLAUDE_CURRENT_SPEC_PATH`
2. If set and file exists at that path:
   - Append line: `**SpecID:** {TASK_ID}` to the file
   - This enables pueue-callback.sh to resolve real spec_id for QA dispatch

Example:
\`\`\`bash
# The inbox done file at CLAUDE_CURRENT_SPEC_PATH gets:
**SpecID:** TECH-157
\`\`\`

**Why:** Without this, QA dispatch after autopilot can't find the spec file
because the pueue task label contains the inbox filename, not the spec ID.
```

## Tests

### Deterministic

| # | Input | Expected | Verification |
|---|-------|----------|-------------|
| 1 | TASK_LABEL=`inbox-20260318-200931`, PREVIEW contains "TECH-157" | QA dispatched with `/qa TECH-157` | grep callback-debug.log for "Resolved QA spec_id=TECH-157" |
| 2 | TASK_LABEL=`FTR-146`, any PREVIEW | QA dispatched with `/qa FTR-146` (Layer 1) | pueue status shows qa-FTR-146 task |
| 3 | TASK_LABEL=`BUG-155`, any PREVIEW | QA dispatched with `/qa BUG-155` (Layer 1) | pueue status shows qa-BUG-155 task |
| 4 | TASK_LABEL=`inbox-XXXX`, empty PREVIEW, no SpecID in file | QA NOT dispatched, log says "no spec_id resolved" | grep callback-debug.log for "no spec_id" |
| 5 | TASK_LABEL=`inbox-XXXX`, PREVIEW has "spec_path: ai/features/BUG-160-..." | QA dispatched with `/qa BUG-160` (Layer 2) | grep callback-debug.log for "Resolved QA spec_id=BUG-160" |
| 6 | TASK_LABEL=`inbox-XXXX`, inbox done file has `**SpecID:** TECH-161` | QA dispatched with `/qa TECH-161` (Layer 3) | grep callback-debug.log for "Resolved QA spec_id=TECH-161" |

### Integration

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Send inbox message → spark creates spec → autopilot → callback | QA dispatched with real spec_id, spec file found |
| 2 | Orchestrator scan_backlog → autopilot → callback | QA works as before (Layer 1) |
| 3 | Inbox task where spark fails → callback with empty preview | QA gracefully skipped (no noise notification) |

### LLM-Judge

| # | Criterion | Evaluator |
|---|-----------|-----------|
| 1 | Backward compatibility: existing orchestrator path QA works unchanged | Code review |
| 2 | resolve_spec_id returns first valid ID, not false positives from unrelated text | Edge case review |

## Definition of Done

- [ ] Multi-layer spec_id resolution in pueue-callback.sh
- [ ] Old `^inbox-` band-aid guard removed
- [ ] CLAUDE_CURRENT_SPEC_PATH passed through claude-runner.py
- [ ] Spark completion writes SpecID to inbox done file
- [ ] Inbox-originated autopilot tasks get QA with correct spec_id
- [ ] Orchestrator-dispatched tasks work unchanged (regression check)
- [ ] Reflect still dispatches unconditionally for all tasks

## Blueprint Reference

**System Blueprint:** Orchestrator north-star cycle (inbox → spark → autopilot → QA → reflect)
**ADR-017:** SQL only via Python (no impact — no SQL changes)
**Existing guard:** BUG-158 band-aid superseded — remove `^inbox-` skip, replace with resolution
