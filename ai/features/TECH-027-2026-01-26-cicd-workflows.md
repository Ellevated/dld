# Feature: [TECH-027] GitHub Actions CI/CD Workflows

**Status:** done | **Priority:** P1 | **Date:** 2026-01-26

## Why

No CI/CD workflows = no trust badge. For a methodology that preaches quality, having no automated checks is ironic. Contributors can't verify their PRs work.

## Context

Current `.github/` structure:
- `ISSUE_TEMPLATE/` — 3 templates ✓
- `PULL_REQUEST_TEMPLATE.md` ✓
- `SECURITY.md` ✓
- `FUNDING.yml` — commented out

Missing:
- `.github/workflows/` — no CI at all

---

## Scope

**In scope:**
- Markdown lint (markdownlint-cli2)
- Link checker (lychee)
- Spell check (cspell)
- YAML lint (yamllint)

**Out of scope:**
- Auto-release (requires tokens)
- Deploy docs (no docs site yet)
- Python tests (hooks are minimal)

---

## Impact Tree Analysis

### Step 1: Files to create
- `.github/workflows/ci.yml` — main CI workflow

### Step 2: Dependencies
- markdownlint-cli2 — npm package
- lychee — GitHub Action
- cspell — npm package
- yamllint — pip package

### Verification
- [ ] All new files documented

---

## Allowed Files

**New files allowed:**
1. `.github/workflows/ci.yml` — main CI workflow
2. `.markdownlint.json` — markdownlint config
3. `cspell.json` — spell check config

**FORBIDDEN:** All other files.

---

## Environment

nodejs: true (for markdownlint, cspell)
docker: false
database: false

---

## Approaches

### Approach 1: Single workflow file
One `ci.yml` with all jobs in parallel.
- Pros: Simple, one file
- Cons: Can't rerun individual checks

### Approach 2: Multiple workflow files
Separate files for each check.
- Pros: Granular control
- Cons: More files to maintain

### Selected: Approach 1

Single file is enough for documentation-only repo. Easy to understand.

---

## Design

### `.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [develop, main]
  pull_request:
    branches: [develop, main]

jobs:
  markdown-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: DavidAnson/markdownlint-cli2-action@v18
        with:
          globs: "**/*.md"

  link-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: lycheeverse/lychee-action@v2
        with:
          args: --verbose --no-progress "**/*.md"
          fail: true

  spell-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: streetsidesoftware/cspell-action@v6
        with:
          files: "**/*.md"

  yaml-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ibiqlik/action-yamllint@v3
        with:
          file_or_dir: .
          config_file: .yamllint.yml
```

### `.markdownlint.json`:
```json
{
  "default": true,
  "MD013": false,
  "MD033": false,
  "MD041": false
}
```

### `cspell.json`:
```json
{
  "version": "0.2",
  "language": "en",
  "words": [
    "autopilot",
    "subagent",
    "worktree",
    "codebase",
    "DLD"
  ],
  "ignorePaths": [
    "node_modules",
    ".git"
  ]
}
```

---

## Implementation Plan

### Task 1: Create CI workflow
**Type:** create
**Files:** create `.github/workflows/ci.yml`
**Acceptance:**
- [ ] File created with 4 jobs
- [ ] Triggers on push/PR to develop/main

### Task 2: Create markdownlint config
**Type:** create
**Files:** create `.markdownlint.json`
**Acceptance:**
- [ ] Disables line length (MD013)
- [ ] Allows HTML in markdown (MD033)

### Task 3: Create cspell config
**Type:** create
**Files:** create `cspell.json`
**Acceptance:**
- [ ] Includes project-specific words
- [ ] Ignores node_modules

### Execution Order
1 → 2 → 3 (independent, can run in parallel)

---

## Definition of Done

### Functional
- [ ] CI runs on push to develop/main
- [ ] CI runs on PRs
- [ ] All 4 checks pass on current codebase

### Technical
- [ ] No workflow syntax errors
- [ ] Badge can be added to README
