# Tech: [TECH-078] Dependabot Security Scanning

**Status:** done | **Priority:** P3 | **Date:** 2026-02-02

## Why

Open source проект без security scanning — красный флаг для enterprise adoption. Dependabot бесплатен, автоматически создаёт PR при уязвимостях и обновлениях.

## Context

Текущее состояние:
- Нет `.github/dependabot.yml`
- Нет `SECURITY.md`
- `template/package.json` имеет npm зависимости
- GitHub Actions в `.github/workflows/` используют external actions

Зависимости для мониторинга:
- `template/package.json` (npm) — create-dld CLI
- `.github/workflows/*.yml` (github-actions) — CI/CD actions

---

## Scope

**In scope:**
- `dependabot.yml` для npm и GitHub Actions
- `SECURITY.md` с vulnerability reporting policy
- Группировка зависимостей для минимизации PR volume

**Out of scope:**
- CodeQL analysis (overkill для template-проекта)
- SAST/DAST scanning
- pip ecosystem (нет requirements.txt в template)
- Multi-ecosystem grouping (overkill, только 2 ecosystem)

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [ ] Dependabot создаёт PR → maintainers review
- [ ] SECURITY.md читают security researchers

### Step 2: DOWN — what depends on?
- [ ] dependabot.yml читает package.json paths
- [ ] Нужно знать директории с зависимостями

### Step 3: BY TERM — grep entire project
- [ ] `grep -rn "dependabot" .` → 0 results
- [ ] `grep -rn "SECURITY" .` → 0 results

### Step 4: CHECKLIST — mandatory folders
- [x] `.github/` — dependabot.yml goes here
- [x] Root — SECURITY.md goes here

### Verification
- [ ] Dependabot активен в GitHub Security tab
- [ ] SECURITY.md виден в repo root

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `.github/dependabot.yml` — dependabot configuration (create)
2. `SECURITY.md` — security policy (create)

**New files allowed:**
- `.github/dependabot.yml`
- `SECURITY.md`

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Grouped updates with weekly schedule (SELECTED)

**Source:** https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/optimizing-pr-creation-version-updates
**Summary:** Group minor/patch updates together, keep major separate for review
**Pros:**
- Reduces PR volume (1 PR for all minor updates)
- Major updates get individual attention
- Clear separation of risk levels
**Cons:**
- Grouped PRs harder to bisect if tests fail
**When:** Projects with moderate dependency count

### Approach 2: Security-updates-only mode

**Source:** GitHub docs
**Summary:** Only create PRs for security vulnerabilities, ignore version updates
**Pros:** Zero noise, focus on security
**Cons:** Miss improvements, manual updates needed
**When:** Legacy projects in maintenance mode

### Selected: 1

**Rationale:** DLD активно развивается, нужны и security и version updates. Группировка снизит PR volume.

---

## Design

### Dependabot Configuration

```yaml
version: 2
updates:
  # NPM dependencies (create-dld CLI)
  - package-ecosystem: "npm"
    directory: "/template"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "npm"
    groups:
      # Group all minor/patch updates together
      minor-and-patch:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"

  # GitHub Actions versions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    labels:
      - "dependencies"
      - "github-actions"
    groups:
      actions:
        patterns:
          - "*"
```

### Security Policy

Standard SECURITY.md with:
- Supported versions table
- Vulnerability reporting process
- Response timeline expectations

---

## Implementation Plan

### Research Sources
- [Dependabot Configuration Options](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file) — full syntax reference
- [Optimizing PR Creation](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/optimizing-pr-creation-version-updates) — grouping strategies

### Task 1: Create dependabot.yml

**Type:** code
**Files:**
  - create: `.github/dependabot.yml`
**Pattern:** YAML config per GitHub docs
**Acceptance:** File exists, valid YAML syntax

### Task 2: Create SECURITY.md

**Type:** code
**Files:**
  - create: `SECURITY.md`
**Pattern:** Standard security policy template
**Acceptance:** File exists in repo root, visible in GitHub Security tab

### Execution Order
1 → 2 (parallel OK)

---

## Flow Coverage Matrix

| # | Step | Covered by Task | Status |
|---|------|-----------------|--------|
| 1 | Configure dependabot | Task 1 | pending |
| 2 | Add security policy | Task 2 | pending |

---

## Definition of Done

### Functional
- [ ] `.github/dependabot.yml` создан с npm + github-actions
- [ ] `SECURITY.md` создан в корне репозитория
- [ ] Dependabot виден в GitHub Security tab

### Technical
- [ ] YAML валиден (yamllint passes)
- [ ] Markdown валиден (markdownlint passes)
- [ ] CI проходит

### Manual Verification (после merge)
- [ ] GitHub Settings → Security → Dependabot alerts = enabled
- [ ] GitHub Settings → Security → Dependabot security updates = enabled
- [ ] Dependabot начинает создавать PR (проверить через неделю)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
