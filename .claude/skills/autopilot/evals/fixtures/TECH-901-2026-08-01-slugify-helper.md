# Feature: [TECH-901] Slugify helper for public URLs

**Priority:** P2 | **Date:** 2026-08-01

> Eval fixture. Not a real backlog item. Copied into a throwaway clone by the
> autopilot eval harness; never dispatch it against a live repository.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml`.
> Callback is the single writer; status/blocked_reason/transitions live there.

## Why

Titles are pasted into URLs verbatim, so a title with spaces or Cyrillic produces
a percent-encoded URL that is unreadable and breaks when copied out of a chat client.

## Context

Nothing in the tree slugifies today; each call site does its own `.replace()`.
This is the small, contained case — one helper plus its tests.

---

## Scope

**In scope:** a pure `slugify(text) -> str` helper and its unit tests.
**Out of scope:** changing any call site to use it, URL routing, redirects for old URLs.

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [ ] New module, no callers yet → 0 results

### Step 2: DOWN — what depends on?
- [ ] Standard library only (`re`, `unicodedata`)

### Step 3: BY TERM — grep entire project
- [ ] `grep -rn "slugify" .` → 0 results (name is free)

### Step 4: CHECKLIST — mandatory folders
- [ ] `tests/**` checked — new test file added below
- [ ] `db/migrations/**` — N/A, no schema change
- [ ] `ai/glossary/**` — N/A, not money-related

### Verification
- [ ] All found files added to Allowed Files
- [ ] grep by old term = 0

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts. -->

ONLY the files listed below may be modified during implementation.

- `src/shared/slugify.py` — the helper (NEW)
- `tests/test_slugify.py` — unit tests (NEW)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Historical Risks

<!-- lessons-binding v1 -->

none

---

## Approaches

### Approach 1: Hand-rolled regex + unicodedata
**Source:** internal analysis
**Summary:** NFKD-normalise, strip combining marks, lowercase, collapse non-alphanumerics to single hyphens, trim.
**Pros:** No dependency. Fully under our control.
**Cons:** Transliteration of Cyrillic is out of scope, so those characters are dropped.

### Approach 2: Add the `python-slugify` dependency
**Source:** internal analysis
**Summary:** Delegate to a maintained library.
**Cons:** A dependency for ~15 lines, and `pyproject.toml` is not in Allowed Files.

### Selected: 1
**Rationale:** Contained, no dependency, and the boundary forbids editing dependency files.

---

## Design

### User Flow
1. Caller passes a raw title
2. Helper returns a lowercase hyphenated ASCII slug
3. Caller uses it in a URL

### Architecture
Single pure function in `src/shared/`. No IO, no state.

### Database Changes
None.

---

## Implementation Plan

### Research Sources
- Internal analysis only — no external pattern needed for a pure string function.

### Task 1: Implement the helper
**Type:** code
**Files:**
  - create: `src/shared/slugify.py`
**Pattern:** internal
**Acceptance:** `slugify("Hello World")` returns `hello-world`

### Task 2: Cover it with tests
**Type:** test
**Files:**
  - create: `tests/test_slugify.py`
**Pattern:** internal
**Acceptance:** All eval criteria below pass

### Execution Order
1 → 2

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Caller passes raw title | Task 1 | ✓ |
| 2 | Helper returns slug | Task 1 | ✓ |
| 3 | Caller uses it in URL | - | out of scope |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Basic case | `"Hello World"` | `"hello-world"` | deterministic | user | P0 |
| EC-2 | Collapses separators | `"a  --  b"` | `"a-b"` | deterministic | devil | P0 |
| EC-3 | Trims edges | `"  Hi!  "` | `"hi"` | deterministic | devil | P0 |
| EC-4 | Empty input | `""` | `""` | deterministic | devil | P1 |
| EC-5 | Non-ASCII dropped, not crashed | `"Привет"` | `""` | deterministic | devil | P1 |

### Coverage Summary
- Deterministic: 5 | Integration: 0 | LLM-Judge: 0 | Total: 5 (min 3)

### TDD Order
1. Write test from EC-1 -> FAIL -> Implement -> PASS
2. Continue by priority (P0 first)

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Module imports | `python -c "from src.shared.slugify import slugify"` | exit 0 | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Basic slug | none | `python -c "from src.shared.slugify import slugify; assert slugify('Hello World')=='hello-world'"` | exit 0 |

### Verify Command

```bash
python -c "from src.shared.slugify import slugify"
python -m pytest tests/test_slugify.py -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] All eval criteria from ## Eval Criteria section pass
- [ ] Coverage not decreased

### Acceptance Verification
- [ ] AV-S1 passes locally
- [ ] AV-F1 passes locally

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
