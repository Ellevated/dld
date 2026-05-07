# BUG-038: QA Instrument Fixes — 5 bugs from QA run

**Status:** done
**Priority:** P0
**Source:** QA report `ai/qa/2026-03-12-ftr031-037-instruments.md`
**Created:** 2026-03-12

## Problem

QA run on FTR-031 to FTR-037 instruments found 5 bugs. Two are Critical (crash on any call), one Major (silent failure), two Minor (missing validation).

### Root Cause Analysis

**F1 (Critical):** `negative_handler.py:17` imports `sanitize_review_text` from `shared.prompt_security`, but the function is defined in `domains/reviews/sanitize.py`. The import was added during FTR-030 (P6 precondition) but pointed to wrong module. Result: entire negative review pipeline is broken — scheduler job crashes on every run.

**F2 (Critical, systemic):** `instruments/seo_intelligence.py` uses `.ok` attribute on `shared.result.Result` objects. `Result` has `.is_ok()` method, not `.ok` property. Same bug exists in 3 more files: `infra/scheduler/jobs_decision.py`, `infra/scheduler/jobs_performance.py`, `domains/decision/auto_actions.py`, `domains/inventory/auto_pause.py`. Note: `domains/intelligence/collector.py` and `infra/sources/registry_test.py` use `.ok` correctly — they operate on `SourceResult` which has `.ok` as a property.

**F3 (Major):** `domains/decision/launch.py` uses fallback defaults when any step fails (steps 1-6). All steps can fail silently and pipeline returns `Ok(LaunchKit)` with empty/default data. No way for caller to know the data is fallback vs real.

**F4 (Minor):** `domains/inventory/pipeline.check_stock()` returns `data_ok=True` with 0 articles for non-existent projects. No project existence validation.

**F5 (Minor):** `domains/decision/briefing.compile_briefing()` catches `no such table: decision_state` error and returns `Ok(DailyBriefing)` with "no data" headline. SQLite error is silently swallowed.

## Tasks

### Task 1: Fix F1 — broken import in negative_handler.py

**File:** `domains/reviews/negative_handler.py`

**Change:** Line 17 — fix import path.

```python
# BEFORE (broken):
from shared.prompt_security import sanitize_review_text

# AFTER (correct):
from domains.reviews.sanitize import sanitize_review_text
```

**Verify:** `python -c "from domains.reviews.negative_handler import process_batch"` — no crash.

### Task 2: Fix F2 — `.ok` → `.is_ok()` across 5 files

**Systemic fix.** Replace `.ok` with `.is_ok()` ONLY where the object is `shared.result.Result` (Ok/Err). Do NOT change code using `SourceResult.ok` (that's a valid property).

**Files to fix:**

1. `instruments/seo_intelligence.py` — lines 40, 41, 48, 49
```python
# BEFORE:
collect_value = collect_result.value if collect_result.ok else None
classify_value = classify_result.value if classify_result.ok else []
"collect_ok": collect_result.ok,
"classify_ok": classify_result.ok,

# AFTER:
collect_value = collect_result.value if collect_result.is_ok() else None
classify_value = classify_result.value if classify_result.is_ok() else []
"collect_ok": collect_result.is_ok(),
"classify_ok": classify_result.is_ok(),
```

2. `infra/scheduler/jobs_decision.py` — lines 72, 102
```python
# BEFORE:
if eval_result.ok:
if briefing_result.ok:

# AFTER:
if eval_result.is_ok():
if briefing_result.is_ok():
```

3. `infra/scheduler/jobs_performance.py` — lines 133, 142
```python
# BEFORE:
if result.ok:
if cls_result.ok:

# AFTER:
if result.is_ok():
if cls_result.is_ok():
```

4. `domains/decision/auto_actions.py` — line 132
```python
# BEFORE:
if result.ok:

# AFTER:
if result.is_ok():
```

5. `domains/inventory/auto_pause.py` — line 103
```python
# BEFORE:
action_id: str | None = result.value if result.ok else None

# AFTER:
action_id: str | None = result.value if result.is_ok() else None
```

**Do NOT change:** `domains/intelligence/collector.py`, `infra/sources/registry_test.py` — these use `SourceResult.ok` (property, not method).

### Task 3: Fix F3 — Launch Copilot silent failure tracking

**File:** `domains/decision/launch.py`

**Change:** Add `steps_failed: list[str]` field to `LaunchKit` model, populate it when steps use fallback, and return `Err` when ALL LLM steps fail.

```python
# In run_launch_pipeline(), track failed steps:
steps_failed: list[str] = []

# After each step fallback, add to list:
if niche_result.is_err():
    steps_failed.append("niche_scan")
    niche_result = Ok(_make_default_niche(niche_category))

# ... same for steps 2, 4, 6

# Before returning Ok(kit), add steps_failed to kit:
kit = LaunchKit(
    ...
    steps_failed=steps_failed,
)

# If ALL LLM steps failed (steps 1+4+6), return Err:
if len(steps_failed) >= 3 and all(s in steps_failed for s in ["niche_scan", "seo_build", "launch_plan"]):
    return Err(
        code="PIPELINE_ALL_LLM_FAILED",
        message=f"All LLM steps failed: {', '.join(steps_failed)}. Check ANTHROPIC_API_KEY and connectivity.",
        action="Verify API key and retry",
    )
```

**File:** `domains/decision/launch_models.py`

**Change:** Add `steps_failed: list[str] = []` field to `LaunchKit`.

### Task 4: Fix F4 + F5 — project validation (Minor)

**File:** `domains/inventory/pipeline.py`

**Change:** When `articles_checked == 0` after loading snapshots, set `data_ok=False` and `error="no_data_for_project"`.

**File:** `domains/decision/briefing.py`

**Change:** When `read_decision_state()` throws SQLite error, return `Err` instead of empty `Ok`.

```python
# In compile_briefing():
try:
    rows = await _read_state(project_id)
except Exception as e:
    return Err(
        code="DB_ERROR",
        message=f"Cannot read decision_state for {project_id}: {e}",
        action="Check that migration has been applied",
    )
```

## Allowlist

Only these files may be modified:

- `domains/reviews/negative_handler.py` (Task 1)
- `instruments/seo_intelligence.py` (Task 2)
- `infra/scheduler/jobs_decision.py` (Task 2)
- `infra/scheduler/jobs_performance.py` (Task 2)
- `domains/decision/auto_actions.py` (Task 2)
- `domains/inventory/auto_pause.py` (Task 2)
- `domains/decision/launch.py` (Task 3)
- `domains/decision/launch_models.py` (Task 3)
- `domains/inventory/pipeline.py` (Task 4)
- `domains/decision/briefing.py` (Task 4)

## Tests

### Deterministic

- `python -c "from domains.reviews.negative_handler import process_batch"` — no ImportError
- `instruments/seo_intelligence.py` — `.is_ok()` calls don't raise AttributeError
- `jobs_decision.py`, `jobs_performance.py`, `auto_actions.py`, `auto_pause.py` — `.is_ok()` calls work
- LaunchKit model accepts `steps_failed` field

### Integration

- Run `await instruments.seo_intelligence.run('grisha', nm_ids=[])` — returns Ok with summary dict
- Run `await compile_briefing('nonexistent')` — returns Err with DB_ERROR code
- Run `await check_stock('nonexistent')` — returns `data_ok=False`

### Regression

- Existing 542 unit tests pass (`.venv/bin/python -m pytest domains/ -v`)
- `infra/sources/registry_test.py` — still uses `.ok` property on SourceResult (unchanged)

## Blueprint Reference

- ADR-002: Result instead of exceptions — `.is_ok()` is the canonical method
- P6 precondition (FTR-030): `sanitize_review_text` call before prompt builders
