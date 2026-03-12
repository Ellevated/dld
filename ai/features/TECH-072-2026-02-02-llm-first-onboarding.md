# Feature: [TECH-072] LLM-First Onboarding with Diff Preview

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

В 2026 году продвинутые пользователи Claude Code устанавливают пакеты через самого Claude. Текущий `npx create-dld` — это legacy path для "адептов старых технологий".

**User Journey:**
1. Человек видит ссылку на DLD (Reddit, форум, чат)
2. Открывает GitHub README
3. Видит инструкцию: "Скажи Claude: ..."
4. Claude сканирует проект, показывает diff, устанавливает

**Проблема:** Текущий `installation-guide.md` не описывает diff-preview flow.

## Context

- TECH-066 создал `template/ai/installation-guide.md` — LLM-readable manifest
- Но он описывает только "что установить", не "как сравнить с текущим"
- Нужен протокол для Claude: scan → diff → confirm → install

---

## Scope

**In scope:**
- Протокол LLM-First Onboarding в `installation-guide.md`
- Diff-preview алгоритм (что сканировать, как показывать)
- Инструкция в README для Claude-first пользователей
- Пример prompt который юзер копирует

**Out of scope:**
- Изменения в `npx create-dld` (остаётся как есть)
- GUI/web installer
- Auto-update существующих DLD установок

---

## Design

### User Prompt (что говорит пользователь Claude)

**Вариант для README:**
```markdown
## Quick Start (Claude-First)

Say to Claude:

> Install DLD from https://github.com/Ellevated/dld — scan my project first and show what will change.
```

Или на русском:
```
> Установи DLD из https://github.com/Ellevated/dld — сначала просканируй мой проект и покажи что изменится.
```

### Claude Scan Protocol

Claude должен просканировать:

```yaml
scan_targets:
  - path: .claude/skills/
    type: directory
    action: list existing skills

  - path: .claude/agents/
    type: directory
    action: list existing agents

  - path: .claude/hooks/
    type: directory
    action: list existing hooks

  - path: .claude/rules/
    type: directory
    action: list existing rules

  - path: CLAUDE.md
    type: file
    action: check if exists, extract tier if present

  - command: claude mcp list
    type: shell
    action: list configured MCP servers
```

### Diff Preview Format

Claude показывает табличку:

```markdown
## DLD Installation Preview

### Your Current Setup
| Component | Status |
|-----------|--------|
| Skills | spark, commit (2) |
| Agents | none |
| MCP | context7 |
| Hooks | none |
| CLAUDE.md | exists (no tier) |

### What Will Be Added (Standard Tier)
| Component | Action | Files |
|-----------|--------|-------|
| Skills | +3 new | scout, audit, review |
| Agents | +5 new | planner, coder, tester, reviewer, debugger |
| MCP | +1 new | exa |
| Hooks | +2 new | pre-commit, post-commit |
| Rules | +3 new | architecture, dependencies, testing |
| CLAUDE.md | update | add DLD tier section |

### Conflicts (if any)
| File | Issue | Resolution |
|------|-------|------------|
| .claude/skills/spark/SKILL.md | exists | will be overwritten (backup created) |

### Summary
- New files: 15
- Updated files: 2
- Backups: 1

**Proceed with installation?** (yes/no)
```

### Installation Protocol

После подтверждения:

1. **Backup conflicts** — если файл существует, копировать в `.claude/backup/`
2. **Clone template** — `git clone --depth 1 https://github.com/Ellevated/dld.git /tmp/dld`
3. **Copy by tier** — копировать только компоненты выбранного tier
4. **Setup MCP** — `claude mcp add` для недостающих серверов
5. **Update CLAUDE.md** — добавить tier section если нет
6. **Cleanup** — `rm -rf /tmp/dld`
7. **Verify** — показать что установлено

### README Section

Добавить в README.md после текущего Quick Start:

```markdown
## Installation

### Option A: Claude-First (Recommended)

Say to Claude in your project directory:

> Install DLD from https://github.com/Ellevated/dld — scan my project and show what will change.

Claude will:
1. Scan your existing setup (skills, MCP, hooks)
2. Show a diff preview of what will be added
3. Ask for confirmation
4. Install only what's needed

### Option B: CLI (Classic)

\`\`\`bash
npx create-dld my-project
\`\`\`
```

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/ai/installation-guide.md` — add LLM scan/diff protocol
2. `README.md` — add Claude-First installation section

**New files:** none

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Update installation-guide.md with scan/diff protocol
**Type:** docs
**Files:** modify `template/ai/installation-guide.md`
**Acceptance:**
- Add "## LLM Scan Protocol" section
- Add "## Diff Preview Format" section
- Add "## Installation Protocol" section
- Claude can follow protocol to scan → diff → install

### Task 2: Update README with Claude-First option
**Type:** docs
**Files:** modify `README.md`
**Acceptance:**
- Add "Claude-First (Recommended)" as Option A
- Move CLI to Option B
- Include example prompt user copies
- Works in English (primary) and mentions Russian alternative

### Execution Order
1 → 2

---

## Definition of Done

### Functional
- [ ] Claude can read installation-guide.md and understand scan protocol
- [ ] Claude shows diff preview before installing
- [ ] Claude waits for user confirmation
- [ ] Claude creates backups for conflicts
- [ ] Installation completes successfully

### Documentation
- [ ] README has Claude-First as primary option
- [ ] Example prompt is copy-pasteable
- [ ] Protocol is clear and unambiguous

### User Experience
- [ ] User copies one line from README
- [ ] Pastes to Claude
- [ ] Sees clear diff of changes
- [ ] Confirms and gets DLD installed

---

## Dependencies

- **TECH-066** (Tiered User Experience) — done, provides installation-guide.md base

---

## Autopilot Log

<!-- Autopilot will fill this section -->
