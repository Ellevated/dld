# Tech: [TECH-076] Structural Smoke Test for create-dld

**Status:** done | **Priority:** P0 (Launch Blocker) | **Date:** 2026-02-02

## Why

Без smoke-теста мы не знаем, что `npx create-dld` создаёт рабочую структуру. Один битый файл — и пользователь получает нерабочий DLD.

**Что НЕ тестируем:** Claude API, реальную работу skills — это проверяется dogfooding'ом на реальных проектах.

## Context

- `create-dld` копирует template/ в новый проект
- Нужно проверить: все файлы на месте + валидный синтаксис
- Запуск: локально (`npm test`) + CI (на каждый PR в template/)

---

## Scope

**In scope:**
- Bash-скрипт smoke-теста
- Проверка структуры файлов
- Валидация JSON/YAML синтаксиса
- CI workflow
- Cleanup после теста

**Out of scope:**
- Claude API вызовы
- Проверка логики skills
- Performance тесты

---

## Impact Tree Analysis

### Step 1: UP — кто использует create-dld?
- Пользователи через `npx create-dld`
- CI при публикации пакета

### Step 2: DOWN — что тестируем?
- `template/` — источник всех файлов
- `bin/create-dld.js` — CLI entry point

### Step 3: Затронутые файлы
Тест НЕ меняет существующие файлы — только создаёт новые.

---

## Allowed Files

**ONLY these files may be created:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `scripts/smoke-test.sh` | create | Main test script |
| 2 | `.github/workflows/smoke-test.yml` | create | CI workflow |

**FORBIDDEN:** Изменение любых других файлов.

---

## Environment

```yaml
nodejs: true    # npm pack, npx
docker: false
database: false
```

---

## Design

### Test Flow

```
1. cp -r template/ test-proj/   → copy template to temp
2. Verify structure
3. Validate syntax
4. Cleanup (rm -rf test-proj)
```

**Note:** We test template/ directly, not via create-dld CLI. This is faster, doesn't require network, and tests what matters: template content integrity.

### Checklist (что проверяем)

#### Structure (файлы существуют)
```
test-proj/
├── CLAUDE.md                          ✓
├── .claude/
│   ├── settings.json                  ✓
│   ├── hooks/
│   │   ├── README.md                  ✓
│   │   ├── pre_bash.py                ✓
│   │   ├── pre_edit.py                ✓
│   │   ├── post_edit.py               ✓
│   │   ├── prompt_guard.py            ✓
│   │   └── utils.py                   ✓
│   ├── rules/
│   │   ├── architecture.md            ✓
│   │   └── dependencies.md            ✓
│   ├── agents/
│   │   ├── planner.md                 ✓
│   │   ├── coder.md                   ✓
│   │   ├── tester.md                  ✓
│   │   ├── review.md                  ✓
│   │   └── scout.md                   ✓
│   └── skills/
│       ├── spark/SKILL.md             ✓
│       ├── autopilot/SKILL.md         ✓
│       ├── council/SKILL.md           ✓
│       ├── planner/SKILL.md           ✓
│       ├── coder/SKILL.md             ✓
│       ├── tester/SKILL.md            ✓
│       ├── review/SKILL.md            ✓
│       ├── scout/SKILL.md             ✓
│       ├── audit/SKILL.md             ✓
│       ├── reflect/SKILL.md           ✓
│       ├── skill-writer/SKILL.md      ✓
│       └── bootstrap/SKILL.md         ✓
└── ai/
    ├── backlog.md                     ✓
    ├── ideas.md                       ✓
    ├── archive.md                     ✓
    └── diary/index.md                 ✓
```

**Note:** `ai/features/` directory is intentionally NOT in template - it's created by spark when specs are generated.

#### Syntax validation
- `.claude/settings.json` — valid JSON
- All `.md` files — not empty

---

## Detailed Implementation Plan

### Drift Analysis

**CRITICAL ISSUES FOUND during plan validation:**

1. **`ai/features/` directory does NOT exist in template** - The original spec checked for this directory, but it's intentionally absent (created by spark when specs are generated).

2. **create-dld uses git sparse-checkout, not npm pack** - The original approach of `npm pack template/` is wrong. create-dld is in `packages/create-dld/` and downloads template from GitHub at runtime.

3. **Correct approach: Test template directory directly** - Copy template/ to temp dir and verify structure. This is:
   - Faster (no network)
   - More reliable for CI
   - Tests what matters: template content integrity

---

### Task 1: Create smoke-test.sh

**Files:**
- Create: `scripts/smoke-test.sh`

**Context:**
This script tests template directory structure and syntax directly. It simulates what a user gets after `npx create-dld` by copying the template folder and verifying all expected files exist.

**Step 1: Create the script**

```bash
#!/bin/bash
set -euo pipefail

echo "=== DLD Template Smoke Test ==="

# Setup
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$ROOT_DIR/template"
TEMP_DIR=$(mktemp -d)
PROJECT="$TEMP_DIR/smoke-test-proj"

cleanup() {
    rm -rf "$TEMP_DIR"
    echo "Cleaned up $TEMP_DIR"
}
trap cleanup EXIT

# Step 1: Copy template (simulates create-dld)
echo "→ Copying template..."
cp -r "$TEMPLATE_DIR" "$PROJECT"
cd "$PROJECT"

# Step 2: Verify structure
echo "→ Verifying structure..."

check_file() {
    if [ ! -f "$1" ]; then
        echo "FAIL: Missing file: $1"
        exit 1
    fi
    echo "  ✓ $1"
}

check_not_empty() {
    if [ ! -s "$1" ]; then
        echo "FAIL: File is empty: $1"
        exit 1
    fi
}

# Core files
echo ""
echo "Core files:"
check_file "CLAUDE.md"
check_file ".claude/settings.json"
check_file ".claude/hooks/README.md"
check_file ".claude/hooks/pre_bash.py"
check_file ".claude/hooks/pre_edit.py"
check_file ".claude/hooks/post_edit.py"
check_file ".claude/hooks/prompt_guard.py"
check_file ".claude/hooks/utils.py"

# Skills (all 12)
echo ""
echo "Skills:"
SKILLS="spark autopilot council planner coder tester review scout audit reflect skill-writer bootstrap"
for skill in $SKILLS; do
    check_file ".claude/skills/$skill/SKILL.md"
done

# Agents
echo ""
echo "Agents:"
check_file ".claude/agents/planner.md"
check_file ".claude/agents/coder.md"
check_file ".claude/agents/tester.md"
check_file ".claude/agents/review.md"
check_file ".claude/agents/scout.md"

# Rules
echo ""
echo "Rules:"
check_file ".claude/rules/architecture.md"
check_file ".claude/rules/dependencies.md"

# AI folder (no features/ - it's created by spark)
echo ""
echo "AI folder:"
check_file "ai/backlog.md"
check_file "ai/ideas.md"
check_file "ai/archive.md"
check_file "ai/diary/index.md"

# Step 3: Validate syntax
echo ""
echo "→ Validating syntax..."

# JSON valid
if ! node -e "JSON.parse(require('fs').readFileSync('.claude/settings.json'))"; then
    echo "FAIL: Invalid JSON in .claude/settings.json"
    exit 1
fi
echo "  ✓ .claude/settings.json is valid JSON"

# CLAUDE.md not empty
check_not_empty "CLAUDE.md"
echo "  ✓ CLAUDE.md is not empty"

# Check all SKILL.md files are not empty
for skill in $SKILLS; do
    check_not_empty ".claude/skills/$skill/SKILL.md"
done
echo "  ✓ All SKILL.md files are not empty"

echo ""
echo "=== All checks passed ==="
```

**Step 2: Verify test passes**

```bash
chmod +x scripts/smoke-test.sh
./scripts/smoke-test.sh
```

Expected output:
```
=== DLD Template Smoke Test ===
→ Copying template...
→ Verifying structure...

Core files:
  ✓ CLAUDE.md
  ✓ .claude/settings.json
  ...

Skills:
  ✓ .claude/skills/spark/SKILL.md
  ...

=== All checks passed ===
```

**Acceptance Criteria:**
- [ ] Script exits 0 when all files present
- [ ] Script exits 1 with clear message when file missing
- [ ] All 12 skills verified
- [ ] JSON syntax validated
- [ ] No network required

---

### Task 2: Create CI workflow

**Files:**
- Create: `.github/workflows/smoke-test.yml`

**Context:**
CI workflow runs on every push/PR that touches template/ to catch broken template before merge.

**Step 1: Create the workflow**

```yaml
name: Smoke Test

on:
  push:
    branches: [develop, main]
    paths:
      - 'template/**'
      - 'scripts/smoke-test.sh'
  pull_request:
    branches: [develop, main]
    paths:
      - 'template/**'
      - 'scripts/smoke-test.sh'

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Run smoke test
        run: ./scripts/smoke-test.sh
```

**Step 2: Verify workflow syntax**

```bash
# Check YAML is valid
node -e "require('js-yaml').load(require('fs').readFileSync('.github/workflows/smoke-test.yml'))"
```

Note: If js-yaml not available, just commit and GitHub will validate.

**Acceptance Criteria:**
- [ ] Workflow triggers on template/ changes
- [ ] Workflow triggers on smoke-test.sh changes
- [ ] Uses Node.js 20 (matches create-dld requirements)
- [ ] Single job, fast execution

---

### Task 3: Test locally and commit

**Files:**
- None (verification only)

**Context:**
Final verification that everything works before PR.

**Step 1: Run smoke test**

```bash
./scripts/smoke-test.sh
```

**Step 2: Commit changes**

```bash
git add scripts/smoke-test.sh .github/workflows/smoke-test.yml
git commit -m "feat(ci): add template smoke test (TECH-076)"
```

**Acceptance Criteria:**
- [ ] Script runs without errors locally
- [ ] All 12 skills pass verification
- [ ] Commit created with proper message

---

### Execution Order

```
Task 1 → Task 3 → Task 2
(Create script → test locally → add CI)
```

Task 3 depends on Task 1 (needs script to test).
Task 2 can technically be done in parallel with Task 3.

---

### Dependencies

- Task 1: None
- Task 2: None (but should be committed together with Task 1)
- Task 3: Depends on Task 1

---

### Research Sources

- Analyzed `packages/create-dld/index.js` (lines 140-155) - uses git sparse-checkout
- Verified template structure via Grep on `template/` directory
- Confirmed 12 skills exist in `template/.claude/skills/`

---

## Flow Coverage Matrix

| # | Step | Covered by Task | Status |
|---|------|-----------------|--------|
| 1 | Pack template | Task 1 | ✓ |
| 2 | Create project | Task 1 | ✓ |
| 3 | Verify files exist | Task 1 | ✓ |
| 4 | Validate JSON | Task 1 | ✓ |
| 5 | Cleanup | Task 1 | ✓ |
| 6 | CI integration | Task 2 | ✓ |

---

## Definition of Done

### Functional
- [ ] `./scripts/smoke-test.sh` проходит локально
- [ ] CI workflow проходит на PR

### Technical
- [ ] Script идемпотентен (cleanup работает)
- [ ] Понятные error messages при failure

---

## Autopilot Log

*(Filled by Autopilot during execution)*
