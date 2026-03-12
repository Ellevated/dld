# Tech: [TECH-077] mypy Type Checking in CI

**Status:** done | **Priority:** P3 | **Date:** 2026-02-02

## Why

Python hooks без type checking — потенциальный источник runtime ошибок. mypy ловит баги до выполнения. Особенно важно для hooks, которые запускаются на каждый tool call.

## Context

Текущее состояние:
- Python hooks в `template/.claude/hooks/` (5 файлов)
- `utils.py` уже полностью типизирован
- Остальные hooks имеют частичные type hints
- TECH-051 добавил ruff (linting), но не static typing
- CI уже имеет `python-lint` и `python-test` jobs

Python файлы для проверки:
```
template/.claude/hooks/utils.py      # 349 LOC, fully typed
template/.claude/hooks/pre_bash.py   # 128 LOC, partial
template/.claude/hooks/pre_edit.py   # 195 LOC, partial
template/.claude/hooks/post_edit.py  # 121 LOC, partial
template/.claude/hooks/prompt_guard.py # 90 LOC, partial
```

---

## Scope

**In scope:**
- Добавить mypy в CI workflow (extend python-lint job)
- Добавить [tool.mypy] в template/pyproject.toml
- Добавить type hint `-> None` к main() функциям
- Исправить найденные ошибки

**Out of scope:**
- 100% type coverage
- strict mode
- Type stubs для внешних библиотек
- Root pyproject.toml (только template)

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [ ] `grep -r "from.*hooks" . --include="*.py"` → 0 results (hooks standalone)
- [ ] CI workflow uses hooks indirectly via tests

### Step 2: DOWN — what depends on?
- [ ] Hooks depend on: json, sys, os, re, subprocess, fnmatch, glob
- [ ] All stdlib — no external deps

### Step 3: BY TERM — grep entire project
- [ ] `grep -rn "mypy" . --include="*.py" --include="*.yml"` → 0 results

### Step 4: CHECKLIST — mandatory folders
- [x] `tests/**` — hooks have tests in tests/hooks/
- [ ] `.github/workflows/**` — ci.yml needs update

### Verification
- [ ] mypy runs without errors in CI
- [ ] All hooks pass type check

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `.github/workflows/ci.yml` — add mypy to python-lint job
2. `template/pyproject.toml` — add [tool.mypy] section
3. `template/.claude/hooks/pre_bash.py` — add `-> None` to main()
4. `template/.claude/hooks/pre_edit.py` — add `-> None` to main()
5. `template/.claude/hooks/post_edit.py` — add `-> None` to main()
6. `template/.claude/hooks/prompt_guard.py` — add `-> None` to main()

**New files:** None

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Gradual typing with check_untyped_defs (SELECTED)

**Source:** https://mypy.readthedocs.io/en/stable/config_file.html
**Summary:** Start with permissive config, type-check function bodies without requiring annotations
**Pros:**
- Zero breaking changes
- Catches bugs inside functions immediately
- Can incrementally tighten rules
**Cons:**
- Won't catch all type errors until full annotations
**When:** Existing codebases with partial typing

### Approach 2: Strict mode immediately

**Source:** mypy docs
**Summary:** Enable all strict flags from day 1
**Pros:** Maximum type safety
**Cons:** Requires annotating entire codebase before merging
**When:** New projects or small codebases

### Selected: 1

**Rationale:** Hooks already have good partial typing. Gradual approach allows immediate CI integration without blocking PRs.

---

## Design

### Configuration (pyproject.toml)

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_ignores = true
check_untyped_defs = true
ignore_missing_imports = true

# Gradual: don't require annotations yet
disallow_untyped_defs = false
disallow_incomplete_defs = false
```

### CI Integration

Extend existing `python-lint` job:

```yaml
- run: pip install mypy
- run: mypy template/.claude/hooks/
```

---

## Implementation Plan

### Research Sources
- [mypy Configuration](https://mypy.readthedocs.io/en/stable/config_file.html) — config reference
- [Gradual Typing Guide](https://medium.com/@tihomir.manushev/a-strategic-guide-to-gradual-typing-in-python-49ac85f6dbdd) — adoption strategy

### Task 1: Add mypy config to template/pyproject.toml

**Type:** code
**Files:**
  - modify: `template/pyproject.toml`
**Pattern:** pyproject.toml [tool.mypy] section
**Acceptance:** `cat template/pyproject.toml | grep -A10 "tool.mypy"` shows config

### Task 2: Add type hints to hook main() functions

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/pre_bash.py`
  - modify: `template/.claude/hooks/pre_edit.py`
  - modify: `template/.claude/hooks/post_edit.py`
  - modify: `template/.claude/hooks/prompt_guard.py`
**Pattern:** `def main() -> None:`
**Acceptance:** All hooks have `-> None` return type annotation

### Task 3: Add mypy to CI workflow

**Type:** code
**Files:**
  - modify: `.github/workflows/ci.yml`
**Pattern:** Add mypy check to python-lint job
**Acceptance:** `mypy template/.claude/hooks/` passes in CI

### Task 4: Verify and fix any mypy errors

**Type:** code
**Files:**
  - modify: any hook file if mypy finds errors
**Pattern:** Fix type errors
**Acceptance:** `mypy template/.claude/hooks/` exits with code 0

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix

| # | Step | Covered by Task | Status |
|---|------|-----------------|--------|
| 1 | Add mypy config | Task 1 | pending |
| 2 | Annotate functions | Task 2 | pending |
| 3 | Integrate CI | Task 3 | pending |
| 4 | Fix errors | Task 4 | pending |

---

## Definition of Done

### Functional
- [ ] mypy config in template/pyproject.toml
- [ ] All hook main() functions have `-> None`
- [ ] CI runs mypy check

### Technical
- [ ] `mypy template/.claude/hooks/` exits 0
- [ ] CI python-lint job passes
- [ ] No regressions in existing tests

---

## Autopilot Log
[Auto-populated by autopilot during execution]
