# Tech: [TECH-051] Add Python linting to CI

**Status:** done | **Priority:** P1 | **Date:** 2026-01-30

## Problem

CI workflow (`.github/workflows/ci.yml`) checks:
- ✅ Markdown lint
- ✅ Link check
- ✅ Spell check
- ✅ YAML lint
- ❌ Python (5 hook files not checked!)

Python syntax errors or style issues won't be caught until runtime.

**Python files not tested:**
- `.claude/hooks/pre_bash.py`
- `.claude/hooks/pre_edit.py`
- `.claude/hooks/post_edit.py`
- `.claude/hooks/prompt_guard.py`
- `.claude/hooks/utils.py`
- `template/.claude/hooks/*.py`

## Solution

Add Python linting job to CI using ruff (fast, modern linter).

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `.github/workflows/ci.yml` | modify | Add Python lint job |

## Tasks

### Task 1: Add Python linting job

**Files:** `.github/workflows/ci.yml`

**Steps:**
1. Add new job after yaml-lint:
   ```yaml
   python-lint:
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
         with:
           python-version: '3.12'
       - run: pip install ruff
       - run: ruff check .
       - run: ruff format --check .
   ```

**Acceptance:**
- [ ] Python files are linted
- [ ] Format is checked
- [ ] Job runs on push/PR

## DoD

- [ ] CI includes Python lint
- [ ] All Python files pass ruff
- [ ] CI still passes
