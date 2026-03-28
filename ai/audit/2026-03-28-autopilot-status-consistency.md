# Audit: Autopilot Status Consistency (Skills ↔ Code)
**Date:** 2026-03-28 | **Scope:** .claude/skills/autopilot/, scripts/vps/callback.py, scripts/vps/orchestrator.py, ai/backlog.md

## Summary
- Issues: 5 (2 critical, 2 warning, 1 info)
- Files: 4 affected

## Findings

| # | File | Line | Issue | Severity |
|---|------|------|-------|----------|
| 1 | orchestrator.py | 300 | `resumed` status never picked up — regex only matches `queued` | critical |
| 2 | orchestrator.py | 300 | Case-sensitive regex — `Queued` or `QUEUED` silently ignored | warning |
| 3 | callback.py | 323 | `_fix_backlog_status` regex replaces wrong column if backlog format changes | info |
| 4 | CLAUDE.md | 315 | `resumed` documented as valid status but no code path handles it | critical |
| 5 | callback.py | 306 | `_fix_spec_status` has no value validation — could write invalid status | warning |

## Detail

### Finding 1: `resumed` status dead — CRITICAL

**Documentation (7 places) says:**
- SKILL.md:135 — "find first queued/resumed"
- SKILL.md:165 — "Verify status is queued or resumed"
- SKILL.md:180 — "Must be queued or resumed → skip otherwise"
- safety-rules.md:10 — "ONLY take tasks with queued or resumed"
- CLAUDE.md:320 — "Recovery: in_progress → blocked → resumed → in_progress"

**Code (orchestrator.py:300) does:**
```python
if re.search(r"\|\s*queued\s*\|", line):
```

**Result:** If a human marks spec as `resumed` after `blocked`, the orchestrator will **never pick it up**. The entire recovery flow is broken.

**Fix:** Change regex to `r"\|\s*(queued|resumed)\s*\|"`

---

### Finding 2: Case-sensitive backlog scan — WARNING

**orchestrator.py:300** uses case-sensitive regex.
**callback.py:351** uses `re.IGNORECASE`.

If callback auto-fix accidentally writes "Done" (possible if regex replacement produces unexpected casing), orchestrator won't recognize it as done and won't pick up next task either.

Low probability but inconsistent — both should use same casing strategy.

**Fix:** Add `re.IGNORECASE` to orchestrator regex, or ensure all writers use lowercase.

---

### Finding 3: Backlog column position assumption — INFO

`_fix_backlog_status` regex `(\|\s*{spec_id}\s*\|.*?\|)\s*\S+\s*(\|)` works correctly on current format because `.*?` (non-greedy) matches only Task column.

Verified against all 3 backlog section formats:
- LAUNCH: `ID | Task | Status | Impact | Feature.md` — works
- GROWTH: `ID | Task | Status | Impact | Feature.md` — works
- INTERNAL: `ID | Task | Status | Priority | Feature.md` — works
- DONE: `ID | Task | Feature.md` — no Status column, but irrelevant

Current risk is low. Would break only if a new column is added between ID and Status.

---

### Finding 4: `resumed` flow contradicts callback auto-fix — CRITICAL

Current callback Step 7 logic:
- `pueue Success` → sets spec/backlog to `done`
- `pueue Failed` → sets spec/backlog to `blocked`

But if autopilot legitimately sets status to `blocked` (e.g., failing tests, merge conflict) and exits with code 0 (which Claude CLI always does), callback will **override `blocked` back to `done`**.

**Scenario:**
1. Autopilot can't fix tests, sets `**Status:** blocked`, exits
2. Claude CLI returns exit 0
3. Pueue sees "Success"
4. Callback maps Success → done
5. `verify_status_sync(target="done")` sees spec is "blocked", not "done"
6. Auto-fix **overwrites blocked → done**
7. Task is falsely marked complete

**Fix:** Before auto-fix, check if current spec status is `blocked`. If so, don't override.

---

### Finding 5: No status value validation — WARNING

`_fix_spec_status()` accepts any `target` string. If called with a typo or invalid value, it will write it to the spec file. No enum validation exists.

Low probability in current code (only called with "done" or "blocked"), but a future caller could pass invalid values.

**Fix:** Add validation: `if target not in ("done", "blocked", "queued", "in_progress", "resumed"): return False`

---

## Recommendations

### P0 (Immediate)
1. **Fix orchestrator.py:300** — add `resumed` to scan regex
2. **Fix callback.py verify_status_sync** — don't override `blocked` when pueue reports Success

### P1 (Soon)
3. **Add case-insensitive** matching to orchestrator.py:300
4. **Add status enum validation** to `_fix_spec_status()` and `_fix_backlog_status()`

### P2 (Low priority)
5. **Document inbox statuses** (`new`, `processing`) separately from backlog statuses

## Create Tasks?
- [ ] BUG-XXX: orchestrator.py doesn't pick up `resumed` tasks (Finding 1)
- [ ] BUG-XXX: callback auto-fix overwrites `blocked` → `done` (Finding 4)
