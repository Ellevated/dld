# Feature: [TECH-066] Tiered User Experience (Quick/Standard/Power)

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

DLD имеет один путь для всех пользователей. Это создаёт барьер:
- Новичок перегружен информацией
- Power user не видит advanced опции сразу
- Нет понимания времени на setup

**Ключевой инсайт:** Будущее — LLM-First Installation. Claude сам решает что установить, анализируя проект.

## Context

- TECH-065 добавляет MCP tiers — это база
- TECH-066 расширяет до full experience tiers
- Нужен hybrid: human tiers в README + LLM manifest для Claude-агентов

---

## Scope

**In scope:**
- Three tiers: Quick (2 min) / Standard (5 min) / Power (15 min)
- `ai/installation-guide.md` — LLM-readable manifest
- README "Choose Your Path" с badges
- CLI флаги: `--quick`, `--standard`, `--power`
- Tier indicator в CLAUDE.md template
- Upgrade paths documentation

**Out of scope:**
- Auto-detection of optimal tier (future)
- `/tier` command for runtime switching
- GUI installer

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- [x] `grep -r "create-dld" .` → 4 files
- [x] `grep -r "getting-started" .` → 0 files (new)

### Step 2: DOWN — what depends on?
- [x] TECH-065 (MCP tiers) — must complete first
- [x] `create-dld/index.js` — already has prompts from TECH-065

### Step 3: BY TERM — grep entire project
- [x] `grep -rn "installation-guide" .` → 0 results (new file)
- [x] `grep -rn "preset" .` → 0 results (new folder)
- [x] `grep -rn "tier" .` → 2 files (CHANGELOG, template/CLAUDE.md)

| File | Line | Status | Action |
|------|------|--------|--------|
| template/CLAUDE.md | — | exists | add Tier indicator |
| README.md | — | exists | add "Choose Your Path" |
| packages/create-dld/index.js | — | exists | add tier flags |

### Step 4: CHECKLIST — mandatory folders
- [x] `docs/**` — need new getting-started/ folder
- [x] `ai/**` — need installation-guide.md
- [x] No migrations needed

### Verification
- [x] All found files added to Allowed Files
- [x] No old terms to cleanup

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `ai/installation-guide.md` — new: LLM-readable installation manifest
2. `docs/getting-started/quick-start.md` — new: 2-min path
3. `docs/getting-started/standard-setup.md` — new: 5-min path (default)
4. `docs/getting-started/power-setup.md` — new: 15-min path
5. `docs/getting-started/upgrade-paths.md` — new: tier transitions
6. `packages/create-dld/index.js` — add tier flags
7. `README.md` — add "Choose Your Path" section with badges
8. `template/CLAUDE.md` — add Tier indicator

**New files allowed:**
- `ai/installation-guide.md`
- `docs/getting-started/*.md` (4 files)

**FORBIDDEN:** All other files.

---

## Environment

nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: Hybrid Human + LLM (Selected)

**Source:** [Progressive Disclosure UX](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)

**Summary:** Human-readable tiers in README + machine-readable manifest in `ai/installation-guide.md`.

**Pros:**
- Works for both humans and Claude agents
- LLM can cherry-pick components based on project analysis
- Future-proof for agentic workflows

**Cons:**
- Two places to maintain (README + manifest)

### Approach 2: Human-Only Tiers

**Summary:** Just README tiers, no LLM manifest.

**Cons:**
- Misses LLM-First Installation opportunity
- Claude would parse unstructured README

### Selected: Approach 1

**Rationale:** LLM-First Installation is the future. User said: "Claude принимает решение, что ему надо, исходя из того, какой проект."

---

## Design

### Tier Definitions

| Tier | Time | What's Included | When to Use |
|------|------|-----------------|-------------|
| 🏃 Quick | 2 min | Zero config, spark only | Try DLD, small scripts |
| ⭐ Standard | 5 min | MCP + core skills + safety hooks | Active development |
| ⚡ Power | 15 min | All MCP + all skills + council + diary | Teams, complex projects |

### LLM Installation Manifest Structure

```markdown
# ai/installation-guide.md

## For Claude: Project Analysis

Before installing, assess:
1. Tech stack (Python/Node/etc)
2. Project size (files count)
3. Existing .claude/ folder?
4. Team or solo?

## Components (cherry-pick)

### Core (always install)
- files: [list]
- when: always

### Recommended
- files: [list]
- mcp: [servers]
- when: [conditions]

### Power
- files: [list]
- when: [conditions]

## Installation Commands
[Exact copy-paste commands for each component]
```

### CLI Flags

```bash
npx create-dld my-project              # Interactive (default)
npx create-dld my-project --quick      # Tier 1, no prompts
npx create-dld my-project --standard   # Tier 2, no prompts
npx create-dld my-project --power      # Tier 3, no prompts
```

### README "Choose Your Path"

```markdown
## Getting Started

| I want to... | Path | Time |
|--------------|------|------|
| 🏃 Try DLD quickly | [Quick Start](docs/getting-started/quick-start.md) | 2 min |
| ⭐ Build a real project | [Standard Setup](docs/getting-started/standard-setup.md) | 5 min |
| ⚡ Maximum productivity | [Power Setup](docs/getting-started/power-setup.md) | 15 min |
```

### CLAUDE.md Tier Indicator

```markdown
**Tier:** ⭐ Standard
**Upgrade:** Run `./scripts/setup-mcp.sh --power` for full capabilities
```

---

## Implementation Plan

### Research Sources
- [create-next-app CLI patterns](https://nextjs.org/docs/app/api-reference/cli/create-next-app)
- [Progressive Disclosure UX](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)
- [SaaS Activation: time-to-value < 15 min](https://www.saasfactor.co/blogs/saas-user-activation-proven-onboarding-strategies-to-increase-retention-and-mrr)

### Task 1: Create `ai/installation-guide.md`
**Type:** docs
**Files:** create `ai/installation-guide.md`
**Acceptance:**
- LLM-readable structure with YAML blocks
- Project assessment checklist
- All components with conditions
- Cherry-pick installation commands
- Claude can parse and act on it

### Task 2: Create `docs/getting-started/` guides
**Type:** docs
**Files:** create 4 files in `docs/getting-started/`
**Acceptance:**
- `quick-start.md` — 2 min path, zero config
- `standard-setup.md` — 5 min, MCP + core skills
- `power-setup.md` — 15 min, everything
- `upgrade-paths.md` — how to go Tier 1→2→3
- Each has clear time estimate
- Each has "What you get" section

### Task 3: Update README with "Choose Your Path"
**Type:** docs
**Files:** modify `README.md`
**Acceptance:**
- Badges: 🏃 Quick / ⭐ Standard / ⚡ Power
- Table with paths, links, times
- Replaces or enhances current Quick Start section
- Links to getting-started/ docs

### Task 4: Add CLI tier flags to create-dld
**Type:** code
**Files:** modify `packages/create-dld/index.js`
**Acceptance:**
- `--quick` flag → Tier 1, skip all prompts
- `--standard` flag → Tier 2, skip prompts
- `--power` flag → Tier 3, skip prompts
- No flag → interactive (existing behavior from TECH-065)
- Flags documented in `--help`

### Task 5: Update template/CLAUDE.md with Tier indicator
**Type:** docs
**Files:** modify `template/CLAUDE.md`
**Acceptance:**
- Shows current tier with badge
- Shows upgrade command
- Placeholder that create-dld fills based on selection

### Execution Order
1 → 2 → 3 → 4 → 5

**Dependency:** TECH-065 must be completed first (MCP prompts in create-dld).

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User sees README | Task 3 | ✓ |
| 2 | Chooses tier path | Task 3 | ✓ |
| 3 | Reads tier-specific guide | Task 2 | ✓ |
| 4 | Runs create-dld with flag | Task 4 | ✓ |
| 5 | Gets tier-appropriate setup | Task 4 | ✓ |
| 6 | Sees tier in CLAUDE.md | Task 5 | ✓ |
| 7 | Wants to upgrade | Task 2 (upgrade-paths.md) | ✓ |
| 8 | Claude analyzes for install | Task 1 | ✓ |

---

## Definition of Done

### Functional
- [ ] `npx create-dld --quick` creates Tier 1 project
- [ ] `npx create-dld --standard` creates Tier 2 project
- [ ] `npx create-dld --power` creates Tier 3 project
- [ ] Interactive mode still works (no flag)
- [ ] CLAUDE.md shows correct tier after creation
- [ ] Upgrade paths documented and work

### LLM-First
- [ ] `ai/installation-guide.md` exists and is structured
- [ ] Claude can parse manifest and understand components
- [ ] Cherry-pick installation commands work

### Documentation
- [ ] README has "Choose Your Path" with badges
- [ ] All 4 getting-started guides exist
- [ ] Each guide has accurate time estimate

### Technical
- [ ] CLI flags work without prompts library
- [ ] No breaking changes to existing `npx create-dld` flow

---

## Dependencies

- **TECH-065** (Enhanced MCP Integration) — must complete first
  - Provides MCP tier selection in create-dld
  - TECH-066 extends with full experience tiers

---

## Autopilot Log

<!-- Autopilot will fill this section -->
