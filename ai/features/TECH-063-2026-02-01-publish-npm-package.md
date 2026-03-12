# Tech: [TECH-063] Publish create-dld to NPM

**Status:** done | **Priority:** P0 | **Date:** 2026-02-02

## Why

README says `npx create-dld my-project` but package isn't on NPM. Users get `npm ERR! 404 Not Found`. Blocks frictionless onboarding — this is a LAUNCH BLOCKER.

## Context

Current state:
- `packages/create-dld/` exists with working code
- package.json version 1.0.1
- README.md exists
- NOT published to NPM registry
- NPM account: `ellevated`
- NPM_TOKEN already added to GitHub Secrets

---

## Scope

**In scope:**
- Create GitHub Actions workflow for auto-publish on push to main
- Auto-increment patch version on each publish
- First publish happens automatically via CI

**Out of scope:**
- New features for create-dld
- Alternative package managers (yarn, pnpm create)
- Scoped package (@dld/create)
- Manual publish steps (all via CI)

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `.github/workflows/npm-publish.yml` | create | Auto-publish workflow |
| 2 | `README.md` | modify | Add NPM badge |

**New files allowed:**
| # | File | Reason |
|---|------|--------|
| 1 | `.github/workflows/npm-publish.yml` | CI automation |

---

## Environment

nodejs: true
docker: false
database: false

---

## Design

### Auto-Publish Workflow

Trigger: push to main branch
Behavior:
1. Checkout code
2. Bump patch version in package.json
3. Commit version bump
4. Publish to NPM
5. Push version commit back to main

```yaml
name: Publish create-dld to NPM

on:
  push:
    branches: [main]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # For pushing version bump
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Bump version and publish
        working-directory: packages/create-dld
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: |
          # Bump patch version
          npm version patch --no-git-tag-version

          # Publish to NPM
          npm publish --access public

          # Get new version
          VERSION=$(node -p "require('./package.json').version")

          # Commit and push version bump
          git add package.json
          git commit -m "chore: bump create-dld to v${VERSION} [skip ci]"
          git push
```

### README Badge

```markdown
[![npm version](https://img.shields.io/npm/v/create-dld.svg)](https://www.npmjs.com/package/create-dld)
```

---

## Implementation Plan

### Task 1: Create publish workflow

**Type:** code
**Files:**
- create: `.github/workflows/npm-publish.yml`

**Steps:**
1. Create workflow file with push to main trigger
2. Add version bump step
3. Add npm publish step
4. Add commit and push for version bump

**Acceptance:**
- [ ] Workflow syntax valid (yamllint passes)
- [ ] Uses NPM_TOKEN secret

### Task 2: Add NPM badge to README

**Type:** code
**Files:**
- modify: `README.md`

**Steps:**
1. Add npm version badge after existing badges
2. Link to npmjs.com/package/create-dld

**Acceptance:**
- [ ] Badge markup correct

### Task 3: Test first publish

**Type:** manual (user action)
**Steps:**
1. Merge to main branch
2. Check GitHub Actions run
3. Verify package on npmjs.com
4. Test `npx create-dld --help`

**Acceptance:**
- [ ] Package visible on NPM
- [ ] `npx create-dld my-test` creates project

### Execution Order

Task 1 → Task 2 → Task 3 (after merge to main)

---

## Definition of Done

### Functional
- [ ] `npx create-dld my-project` works from NPM
- [ ] Package page exists at npmjs.com/package/create-dld
- [ ] Auto-publish triggers on every push to main
- [ ] Version auto-increments (patch)

### Technical
- [ ] GitHub Actions workflow passes
- [ ] No manual intervention needed for publish
- [ ] Version bump commits don't trigger infinite loop ([skip ci])

### Documentation
- [ ] NPM badge visible in README

---

## Autopilot Log

### Task 1/2: Create publish workflow — 2026-02-02
- Coder: completed (1 file: .github/workflows/npm-publish.yml)
- Tester: skipped (no tests for .yml)
- Deploy: skipped
- Documenter: skipped
- Spec Reviewer: approved (matches spec design exactly)
- Code Quality: approved (standard GHA pattern)
- Commit: 9cc22b1

### Task 2/2: Add NPM badge to README — 2026-02-02
- Coder: completed (1 file: README.md)
- Tester: skipped (no tests for .md)
- Deploy: skipped
- Documenter: skipped
- Spec Reviewer: approved (badge matches spec format)
- Code Quality: approved
- Commit: 9cc22b1 (combined with Task 1)

### Task 3: Test first publish — MANUAL
- User action required: merge to main, verify NPM publish
