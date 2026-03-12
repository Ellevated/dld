# TECH: [TECH-006] GitHub Community Files

**Status:** done | **Priority:** P2 | **Date:** 2026-01-24

## Problem

No GitHub community files exist:
- No LICENSE
- No CONTRIBUTING.md
- No CODE_OF_CONDUCT.md
- No issue/PR templates

GitHub won't recognize project as properly maintained open source.

## Solution

Create standard GitHub community files for open source project.

---

## Scope

**In scope:**
- MIT License
- Contributing guidelines
- Code of Conduct (Contributor Covenant)
- Issue templates (bug, feature, question)
- PR template

**Out of scope:**
- GitHub Actions workflows
- Security policy (SECURITY.md)

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `LICENSE` | MIT license |
| 2 | `CONTRIBUTING.md` | Contribution guidelines |
| 3 | `CODE_OF_CONDUCT.md` | Contributor Covenant |
| 4 | `.github/ISSUE_TEMPLATE/bug-report.md` | Bug report template |
| 5 | `.github/ISSUE_TEMPLATE/feature-request.md` | Feature request template |
| 6 | `.github/ISSUE_TEMPLATE/question.md` | Question template |
| 7 | `.github/PULL_REQUEST_TEMPLATE.md` | PR template |
| 8 | `.github/ISSUE_TEMPLATE/config.yml` | Issue template config |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Create LICENSE

**Files:**
- Create: `LICENSE`

**Steps:**
1. Use MIT License template
2. Set year to 2026
3. Set copyright holder (ask user or use placeholder)

**Acceptance:**
- [ ] Valid MIT license

### Task 2: Create CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

**Steps:**
1. Write guidelines covering:
   - How to report bugs
   - How to suggest features
   - How to submit PRs
   - Code style expectations
   - DLD-specific: how to add examples, translations

**Acceptance:**
- [ ] Clear contribution process
- [ ] Links to relevant docs

### Task 3: Create CODE_OF_CONDUCT.md

**Files:**
- Create: `CODE_OF_CONDUCT.md`

**Steps:**
1. Use Contributor Covenant v2.1
2. Add contact email placeholder

**Acceptance:**
- [ ] Standard Contributor Covenant

### Task 4: Create Issue Templates

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug-report.md`
- Create: `.github/ISSUE_TEMPLATE/feature-request.md`
- Create: `.github/ISSUE_TEMPLATE/question.md`
- Create: `.github/ISSUE_TEMPLATE/config.yml`

**Steps:**
1. Bug report: steps to reproduce, expected/actual, environment
2. Feature request: problem, proposed solution, alternatives
3. Question: context, what you tried
4. Config: enable blank issues, add external links

**Acceptance:**
- [ ] All templates created
- [ ] Templates use GitHub frontmatter format

### Task 5: Create PR Template

**Files:**
- Create: `.github/PULL_REQUEST_TEMPLATE.md`

**Steps:**
1. Include:
   - Summary of changes
   - Related issue
   - Checklist (tests, docs, breaking changes)

**Acceptance:**
- [ ] PR template works

---

## Execution Order

Task 1 → Task 2 → Task 3 → Task 4 → Task 5 (all independent, can parallel)

---

## Definition of Done

### Functional
- [ ] All files created
- [ ] GitHub recognizes community files
- [ ] Templates work correctly

### Technical
- [ ] Valid markdown
- [ ] Proper frontmatter in templates

---

## Autopilot Log

**2026-01-25:** All files created:
- LICENSE (already existed)
- CONTRIBUTING.md (already existed)
- CODE_OF_CONDUCT.md
- .github/ISSUE_TEMPLATE/bug_report.md
- .github/ISSUE_TEMPLATE/feature_request.md
- .github/ISSUE_TEMPLATE/question.md
- .github/ISSUE_TEMPLATE/config.yml
- .github/PULL_REQUEST_TEMPLATE.md
- .github/SECURITY.md (bonus)
- .github/FUNDING.yml (bonus)
