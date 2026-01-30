# TECH: [TECH-024] Pre-Launch Fixes (Umbrella)

**Status:** done | **Priority:** P0 | **Date:** 2026-01-26

## Problem

Pre-launch review found 14 issues that will hurt first impressions and cause 404s on the landing page.

## Solution

Fix all issues before public launch. This is an umbrella spec — each sub-task can be done independently.

---

## Sub-Tasks

### 🔴 CRITICAL (P0) — Must fix before launch

#### TECH-024.1: Create CHANGELOG.md
**Problem:** README.md badge links to non-existent CHANGELOG.md
**Location:** `/README.md:7`
```markdown
[![Version](https://img.shields.io/badge/version-3.3-green.svg)](CHANGELOG.md)
```
**Fix:** Create CHANGELOG.md with version history (3.0 → 3.3)
**Allowed files:** `CHANGELOG.md` (create)

---

#### TECH-024.2: Fix or remove ADR links
**Problem:** docs/19-living-architecture.md links to non-existent ADR files
**Location:** `/docs/19-living-architecture.md:147-169`
```markdown
| 001 | Supabase instead of raw Postgres | [→](./decisions/001-supabase.md) |
| 002 | Separate billing domain | [→](./decisions/002-billing-domain.md) |
| 003 | LLM agent for seller | [→](./decisions/003-llm-agent.md) |
```
**Options:**
- A) Create `docs/decisions/` with example ADRs
- B) Remove links, keep as template example without clickable links
**Allowed files:** `docs/19-living-architecture.md` (modify), `docs/decisions/*.md` (create if option A)

---

#### TECH-024.3: Fix or remove ARCHITECTURE-CHANGELOG link
**Problem:** Link to non-existent changelog
**Location:** `/docs/19-living-architecture.md:182`
```markdown
[Full changelog →](./changelog/ARCHITECTURE-CHANGELOG.md)
```
**Fix:** Remove link or create file
**Allowed files:** `docs/19-living-architecture.md` (modify)

---

#### TECH-024.4: Replace [your-repo] placeholder
**Problem:** Copy-paste commands don't work
**Location:** `/README.md:26,37`
```bash
git clone https://github.com/[your-repo]/dld
```
**Fix:** Replace with actual repo URL (need to know the org/repo name)
**Allowed files:** `README.md` (modify)

---

#### TECH-024.5: Translate template/ai/*.md to English
**Problem:** Russian text in English-only project
**Files:**
- `template/ai/backlog.md` — fully Russian
- `template/ai/diary/index.md` — fully Russian

**Current content (backlog.md):**
```markdown
## Очередь
| ID | Задача | Status | Priority | Feature.md |
## Статусы
| draft | Спека в процессе |
| queued | Готово для autopilot |
```

**Fix:** Translate to English
**Allowed files:** `template/ai/backlog.md`, `template/ai/diary/index.md` (modify)

---

#### TECH-024.6: Fix broken links in backlog template
**Problem:** Links to non-existent files
**Location:** `template/ai/backlog.md:25,29`
```markdown
[archive.md](archive.md)  ← DOES NOT EXIST
[ideas.md](ideas.md)      ← DOES NOT EXIST
```
**Options:**
- A) Create empty archive.md and ideas.md templates
- B) Remove links
**Allowed files:** `template/ai/backlog.md` (modify), `template/ai/archive.md`, `template/ai/ideas.md` (create if option A)

---

### 🟠 MEDIUM (P1) — Should fix before launch

#### TECH-024.7: Unify versions across docs
**Problem:** Three different versions mentioned (3.0, 3.3, 3.4)
**Files with wrong versions:**
- `template/README.md` → says 3.0
- `template/.claude/skills/autopilot/SKILL.md` → says 3.0
- `template/CLAUDE.md` → says 3.4 (Context System)

**Fix:** Decide on version (3.3 or 3.4) and update all files
**Allowed files:** Multiple template files (modify)

---

#### TECH-024.8: Fix ai/principles/ path in template/README.md
**Problem:** Instructions reference non-existent path
**Location:** `template/README.md:12-13`
```bash
cp -r /path/to/ai/principles/_template/* .
```
**Fix:** Update to correct path or rewrite instructions
**Allowed files:** `template/README.md` (modify)

---

#### TECH-024.9: Clarify DLD definition
**Problem:** Conflicting definitions
- FAQ.md: "DLD (Domain-Level Design)"
- README.md: "DLD: LLM-First Architecture"

**Fix:** Pick one canonical definition, update both files
**Allowed files:** `FAQ.md`, `README.md` (modify)

---

#### TECH-024.10: Fix absolute paths in examples/
**Problem:** Links work only from repo root, not from example folder
**Files:**
- `examples/ai-autonomous-company/README.md`
- `examples/content-factory/README.md`
- `examples/marketplace-launch/README.md`

**Current:** `[Migration Guide](/docs/13-migration.md)`
**Fix:** `[Migration Guide](../../docs/13-migration.md)`
**Allowed files:** All README.md in examples/ (modify)

---

#### TECH-024.11: Remove Russian from hooks README
**Problem:** Inconsistent language support
**Location:** `template/.claude/hooks/README.md:92`
```markdown
Russian equivalents: "создай фичу", "добавь api"
```
**Fix:** Remove Russian examples or add comment explaining it's optional localization
**Allowed files:** `template/.claude/hooks/README.md` (modify)

---

### 🟡 LOW (P2) — Nice to fix

#### TECH-024.12: Clean up URL placeholders in agents
**Problem:** `[Pattern](url)` placeholders may confuse users
**Files:** Multiple agents in `template/.claude/agents/`
**Fix:** Replace with realistic example URLs or add comment
**Allowed files:** `template/.claude/agents/*.md` (modify)

---

#### TECH-024.13: Clarify TODO in migration doc
**Problem:** Unclear if example or real task
**Location:** `docs/13-migration.md:39`
```python
"src/services/order_service.py",  # TODO: migrate by 2026-02-01
```
**Fix:** Mark clearly as example
**Allowed files:** `docs/13-migration.md` (modify)

---

#### TECH-024.14: Fix plan/ vs planner/ in template/README
**Problem:** References non-existent folder
**Location:** `template/README.md:30`
```markdown
├── plan/               # plan subagent
```
**Fix:** Change to `planner/` or remove (it's internal subagent)
**Allowed files:** `template/README.md` (modify)

---

## Execution Order

Recommended order (can be parallelized within priority):

```
P0 (CRITICAL):
  024.4 → need repo URL first (blocking)
  024.1, 024.5, 024.6 → independent
  024.2, 024.3 → related (same file)

P1 (MEDIUM):
  024.7 → version decision needed
  024.8, 024.9, 024.10, 024.11 → independent

P2 (LOW):
  024.12, 024.13, 024.14 → independent
```

---

## Definition of Done

- [ ] All links in README.md work (no 404)
- [ ] All links in docs/ work (no 404)
- [ ] No Russian text in template/ (except comments explaining localization)
- [ ] Consistent version number across all files
- [ ] Example paths in examples/ work from their folders

---

## Questions for Human

1. **Repo URL:** What is the actual GitHub org/repo? (for TECH-024.4)
2. **ADR strategy:** Create example ADRs or remove links? (for TECH-024.2)
3. **Version:** Is current version 3.3 or 3.4? (for TECH-024.7)
4. **DLD definition:** "Domain-Level Design" or "LLM-First Architecture"? (for TECH-024.9)

---

## Autopilot Log

- **2026-01-26**: Created umbrella spec from pre-launch review
  - 6 critical issues (P0)
  - 5 medium issues (P1)
  - 3 low issues (P2)
  - Total: 14 issues
