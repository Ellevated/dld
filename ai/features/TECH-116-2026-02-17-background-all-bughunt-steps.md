# Feature: [TECH-116] Background ALL Bug Hunt Steps — Fix Context Crash

**Status:** done | **Priority:** P0 | **Date:** 2026-02-17

## Problem

Bug Hunt pipeline crashes between Step 5 and Step 6 due to context overflow in Spark orchestrator.

**Evidence:** Session `20260217-hooks` — Steps 0-5 completed successfully, Step 6 (solution-architects) never launched. Report BUG-115 has `Specs created: TBD`, all groups `pending`.

**Root cause:** ADR-008 (`run_in_background: true`) was applied only to parallel fan-out steps (1, 6). Sequential steps (0, 2, 3, 4, 5) run as foreground agents — their full responses accumulate in Spark's context.

**Context budget before fix:**
- Spark initial context (CLAUDE.md + SKILL.md + bug-mode.md + rules): ~20K tokens
- Step 0 foreground response: ~1K
- Step 1 background (ADR-008): ~300 tokens ✅
- Step 2 foreground response: ~5K
- Step 3 foreground response: ~10-30K
- Step 4 foreground response: ~5K
- Step 5 foreground response: ~10-30K
- **Total by Step 6: 50-90K+ accumulated** → crash

## Solution: ADR-009 — Background ALL Steps

Every Task call in the pipeline uses `run_in_background: true`. Spark communicates with agents exclusively through file IPC (convention paths). Spark NEVER reads agent responses into its own context.

**Context budget after fix:**
- Steps 0-6: each ~50 tokens (output_file path only)
- **Total: ~350 tokens** for all agent communication
- **Reduction: ~200x**

### New step pattern (uniform for ALL steps):

```
1. Launch: Task(run_in_background: true, subagent_type: X, prompt: ...)
2. Receive: {task_id, output_file} (~50 tokens)
3. Verify: Glob("{convention_path}") → file exists?
4. If missing: Read(output_file, limit: 5) → check if agent finished
5. If still missing after retries: apply fallback (ADR-007 caller-writes)
6. Proceed to next step
```

### Additional fixes

1. **Convention path consistency:** Spec must go to `ai/features/BUG-{ID}-bughunt.md` (flat file), NOT `ai/features/BUG-{ID}/BUG-{ID}.md` (subdirectory). Fix in spec-assembler prompt.

2. **File gate for Step 5:** Currently says "Groups available (from response or validator file)". After background, there's no "from response". Change to: read groups from `validator-output.yaml` directly.

3. **Handoff simplification:** After Step 6 completes, Spark reads validator-output.yaml for group list and verifies spec files exist. No need to parse agent responses.

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] `bug-mode.md` — Spark skill instructions for Bug Hunt pipeline
- [x] `completion.md` — Bug Hunt handoff (unchanged, downstream)

### Step 2: DOWN — what depends on?
- [x] All 12 bug-hunt agents — unchanged (they write to convention paths regardless of foreground/background)
- [x] ADR-008 — extended, not contradicted
- [x] ADR-007 — unchanged (caller-writes fallback still applies)

### Step 3: BY TERM — grep entire project
| Term | Files | Action |
|------|-------|--------|
| `run_in_background` | bug-mode.md | Add to Steps 0, 2, 3, 4, 5 |
| `Step 2.*Collect` | bug-mode.md | Add background + polling |
| `Step 3.*Assemble` | bug-mode.md | Add background + polling |
| `Step 4.*Validate` | bug-mode.md | Add background + polling |
| `Step 5.*Update` | bug-mode.md | Add background + polling |
| `from response` | bug-mode.md | Remove — no foreground responses |
| `BUG-{ID}-bughunt` | spec-assembler.md | Verify convention path |

### Verification
- [x] All found files added to Allowed Files

## Detailed Changes

### 1. bug-mode.md: Steps 0, 2, 3, 4, 5 — add `run_in_background: true`

Each step's Task call gets `run_in_background: true`. Remove any expectation of parsing agent response content.

**Step 0:**
```yaml
Task:
  subagent_type: bughunt-scope-decomposer
  run_in_background: true     # ← ADD
  description: "Bug Hunt: scope decomposition"
```
After launch: poll `{SESSION_DIR}/step0/zones.yaml` with Glob. Read zones from file, not from response.

**Step 2:**
```yaml
Task:
  subagent_type: bughunt-findings-collector
  run_in_background: true     # ← ADD
  description: "Bug Hunt: collect findings"
```
After launch: poll `{SESSION_DIR}/step2/findings-summary.yaml`.

**Step 3:**
```yaml
Task:
  subagent_type: bughunt-spec-assembler
  run_in_background: true     # ← ADD
  description: "Bug Hunt: assemble spec"
```
After launch: poll `ai/features/BUG-*-bughunt.md` (NOT subdirectory).

**Step 4:**
```yaml
Task:
  subagent_type: bughunt-validator
  run_in_background: true     # ← ADD
  description: "Bug Hunt: validate findings"
```
After launch: poll `{SESSION_DIR}/step4/validator-output.yaml`.

**Step 5:**
```yaml
Task:
  subagent_type: bughunt-report-updater
  run_in_background: true     # ← ADD
  description: "Bug Hunt: update report"
```
After launch: verify report updated (check file mtime or content hash).

### 2. bug-mode.md: Remove "from response" fallbacks

Lines referencing "parse X from response" must change to "read X from convention path file":

- Step 0: "Parse zone names from response" → "Read zone names from zones.yaml"
- Step 3: "Returns spec_id and spec_path" → "Glob for spec file, extract ID from filename"
- Step 5: "Returns groups with priorities for Step 6" → "Read groups from validator-output.yaml"

### 3. bug-mode.md: Add universal polling pattern

Add a reusable polling description at the top of "Execution" section:

```
### Background Step Pattern (ALL steps)

Every step uses run_in_background: true. After launch:

Poll loop (max 15 attempts, 3 sec between):
  1. Glob("{convention_path}") → file exists?
  2. If exists → step complete, proceed
  3. If not → TaskOutput(task_id, block: false) → check status
  4. If task done but no file → ADR-007 fallback (read output_file, extract, write)
  5. Continue polling
```

### 4. spec-assembler agent: Fix convention path

Verify that `bughunt-spec-assembler.md` instructs writing to `ai/features/BUG-{ID}-bughunt.md` (flat), not `ai/features/BUG-{ID}/BUG-{ID}.md`.

### 5. architecture.md: Add ADR-009

```
| ADR-009 | Background ALL pipeline steps | 2026-02 | Sequential foreground agents accumulate in orchestrator context. All steps use run_in_background. |
```

## Research Sources
- ADR-008: Background fan-out (proven for parallel steps)
- ADR-007: Caller-writes (fallback for file IPC)
- Session `20260217-hooks`: empirical evidence of context crash
- Memory: "Compaction = Enemy of Pipeline" (Feb 16)

## Allowed Files
1. `template/.claude/skills/spark/bug-mode.md` — rewrite all steps to background
2. `.claude/skills/spark/bug-mode.md` — sync from template
3. `template/.claude/agents/bug-hunt/spec-assembler.md` — fix convention path
4. `.claude/agents/bug-hunt/spec-assembler.md` — sync from template
5. `template/.claude/rules/architecture.md` — add ADR-009
6. `.claude/rules/architecture.md` — sync from template

## Definition of Done
- [ ] ALL steps (0-5) use `run_in_background: true`
- [ ] No foreground Task calls remain in bug-mode.md pipeline
- [ ] All "from response" parsing replaced with file reads
- [ ] Universal polling pattern documented
- [ ] spec-assembler convention path fixed (flat file, not subdirectory)
- [ ] ADR-009 added to architecture.md
- [ ] Template and root .claude/ synced
- [ ] Manual test: Bug Hunt on small target completes all 7 steps without context crash
