# Feature: [TECH-156] Silence Intermediate Telegram Notifications During Cycle
**Status:** queued | **Priority:** P1 | **Date:** 2026-03-18

## Why
DLD-бот отправляет Telegram уведомления за каждый шаг цикла: spark, autopilot, QA. Это засоряет чат. OpenClaw читает `ai/openclaw/pending-events/` и сам формирует финальный отчёт. Промежуточные уведомления от DLD-бота — шум.

## Context
- `pueue-callback.sh` уже имеет SKIP_NOTIFY для reflect (line 241-243)
- `inbox-processor.sh` шлёт "🚀 Starting..." перед каждым dispatch (lines 183-191)
- Pending-events (Step 6.8) записываются НЕЗАВИСИМО от SKIP_NOTIFY — их не трогаем
- Night-reviewer уже пропускается по group check (line 75-79)

---

## Scope
**In scope:**
- Заглушить уведомления для spark, autopilot, qa в pueue-callback.sh (только success)
- Заглушить pre-dispatch уведомления в inbox-processor.sh для тех же skills
- Сохранить уведомления об ошибках (failed tasks)

**Out of scope:**
- pending-events файлы — не трогать
- Логика dispatch QA + Reflect — не менять
- Уведомления об ошибках — обсудить отдельно (пока оставить)
- Night-reviewer — уже заглушен

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `pueue-callback.sh` — вызывается Pueue daemon при завершении любой задачи
- `inbox-processor.sh` — вызывается orchestrator.sh для каждого inbox файла

### Step 2: DOWN — what depends on?
- `notify.py` — отправитель Telegram сообщений (НЕ модифицируем)
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (НЕ модифицируем)

### Step 3: BY TERM — grep entire project
- `SKIP_NOTIFY` встречается только в `pueue-callback.sh` — нет внешних зависимостей

### Step 4: CHECKLIST — mandatory folders
- [ ] `tests/**` — нет тестов для shell scripts (ручная верификация)
- [ ] `db/migrations/**` — не требуется

### Verification
- [ ] Все файлы добавлены в Allowed Files
- [ ] grep SKIP_NOTIFY = только в pueue-callback.sh

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `scripts/vps/pueue-callback.sh` — добавить SKIP_NOTIFY для spark, autopilot, qa
2. `scripts/vps/inbox-processor.sh` — пропустить pre-dispatch уведомления для тех же skills

**New files allowed:**
- нет

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps/)
**Cross-cutting:** Telegram notifications
**Data model:** нет изменений

---

## Approaches

### Approach 1: Skill Allowlist in Callback (based on codebase scout)
**Source:** Existing pattern in pueue-callback.sh line 241-243 (reflect skip)
**Summary:** Добавить spark, autopilot, qa в существующий SKIP_NOTIFY блок. В inbox-processor.sh пропустить notify для тех же skills.
**Pros:** Минимальный diff (~15 LOC), следует существующему паттерну, trivially rollbackable
**Cons:** Hardcoded список (но reflect тоже hardcoded)

### Approach 2: Environment Variable SILENT_SKILLS (based on external scout)
**Source:** CI/CD best practices (GitHub Actions conditional notifications)
**Summary:** Определить SILENT_SKILLS="spark,autopilot,qa,reflect" в .env, парсить в обоих скриптах
**Pros:** Конфигурируемость без изменения кода
**Cons:** Bash string parsing хрупкий, лишняя зависимость от .env, ~25 LOC

### Selected: 1
**Rationale:** Следует существующему паттерну. Список skills стабилен. Env-var конфигурируемость не оправдана — менять набор skills = менять архитектуру, а не переменную.

---

## Design

### Architecture

```
pueue-callback.sh:
  SKIP_NOTIFY block (existing):
    - reflect → already silenced
  + spark (success only) → SKIP_NOTIFY=true
  + autopilot (success only) → SKIP_NOTIFY=true
  + qa (success only) → SKIP_NOTIFY=true

inbox-processor.sh:
  Pre-dispatch notification block (existing):
    - sends "🚀 Starting..." for ALL skills
  + skip notification for spark, autopilot, qa
```

### CRITICAL: Preserve Failure Notifications

Devil scout выявил: SKIP_NOTIFY для spark/autopilot/qa должен применяться ТОЛЬКО при STATUS="done". Failed tasks ДОЛЖНЫ уведомлять.

Текущая структура кода позволяет это: SKIP_NOTIFY блок (Step 6) находится ПОСЛЕ определения STATUS (line 69-72). Нужно добавить проверку `$STATUS == "done"` в условия.

---

## Implementation Plan

### Task 1: Silence success notifications in pueue-callback.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/pueue-callback.sh`
**Acceptance:**
- spark/autopilot/qa success → no Telegram notification
- spark/autopilot/qa failure → Telegram notification IS sent
- reflect → still silenced (unchanged)
- pending-events → still written (unchanged)

**Details:**
After line 243 (reflect skip), add:
```bash
# Don't notify about intermediate cycle steps (spark, autopilot, qa)
# OpenClaw reads pending-events and reports results itself.
# Only suppress SUCCESS — failures must still notify for debugging.
if [[ "$STATUS" == "done" && ("$SKILL" == "spark" || "$SKILL" == "autopilot" || "$SKILL" == "qa") ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: ${SKILL} success (OpenClaw handles reporting)"
fi
```

### Task 2: Silence pre-dispatch notifications in inbox-processor.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/inbox-processor.sh`
**Acceptance:**
- inbox dispatch for spark/autopilot/qa → no "🚀 Starting..." notification
- inbox dispatch for other skills (architect, council, bughunt) → still notifies

**Details:**
Before notification block (line 183), add skill check:
```bash
# Skip pre-dispatch notification for cycle skills — OpenClaw handles reporting
SILENT_SKILLS="spark autopilot qa reflect"
if [[ " $SILENT_SKILLS " =~ " $SKILL " ]]; then
    echo "[inbox] Skipping pre-dispatch notification: ${SKILL} (OpenClaw handles)"
else
    # ... existing notification code ...
fi
```

### Execution Order
1 → 2 (independent, can be parallel)

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User sends message to Telegram | - | existing |
| 2 | OpenClaw creates inbox file | - | existing |
| 3 | Orchestrator picks up inbox file | - | existing |
| 4 | inbox-processor.sh dispatches spark | Task 2 | suppress notification |
| 5 | Spark completes, callback fires | Task 1 | suppress notification |
| 6 | Callback dispatches autopilot | - | existing |
| 7 | Autopilot completes, callback fires | Task 1 | suppress notification |
| 8 | Callback dispatches QA + Reflect | - | existing |
| 9 | QA completes, callback fires | Task 1 | suppress notification |
| 10 | Pending-events written | - | existing (untouched) |
| 11 | OpenClaw reads events, reports | - | existing |

**GAPS:** None. All cycle steps covered.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Spark completes successfully | SKILL=spark STATUS=done | SKIP_NOTIFY=true, no notify.py call | deterministic | devil | P0 |
| EC-2 | Autopilot completes successfully | SKILL=autopilot STATUS=done | SKIP_NOTIFY=true, pending-event still written | deterministic | devil | P0 |
| EC-3 | Autopilot FAILS | SKILL=autopilot STATUS=failed | SKIP_NOTIFY=false, notify.py IS called | deterministic | devil | P0 |
| EC-4 | QA completes successfully | SKILL=qa STATUS=done | SKIP_NOTIFY=true | deterministic | devil | P0 |
| EC-5 | inbox-processor dispatches spark | SKILL=spark | No "🚀" notification sent | deterministic | devil | P1 |
| EC-6 | inbox-processor dispatches architect | SKILL=architect | "🚀" notification IS sent | deterministic | codebase | P1 |
| EC-7 | Reflect still silenced | SKILL=reflect | SKIP_NOTIFY=true (existing behavior) | deterministic | codebase | P1 |

### Coverage Summary
- Deterministic: 7 | Integration: 0 | LLM-Judge: 0 | Total: 7 (min 3 ✓)

### TDD Order
1. EC-3 first (failure notification preserved — most critical)
2. EC-1, EC-2, EC-4 (success suppression)
3. EC-5, EC-6, EC-7 (inbox + regression)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | pueue-callback.sh syntax valid | `bash -n scripts/vps/pueue-callback.sh` | exit 0 | 5s |
| AV-S2 | inbox-processor.sh syntax valid | `bash -n scripts/vps/inbox-processor.sh` | exit 0 | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Callback silences spark success | Set SKILL=spark STATUS=done | Source callback logic | SKIP_NOTIFY=true in log |
| AV-F2 | Callback preserves autopilot failure | Set SKILL=autopilot STATUS=failed | Source callback logic | SKIP_NOTIFY=false |
| AV-F3 | Events still written | Complete autopilot task | Check pending-events/ | JSON event file exists |

### Verify Command (copy-paste ready)

```bash
# Smoke
bash -n scripts/vps/pueue-callback.sh && echo "callback: OK"
bash -n scripts/vps/inbox-processor.sh && echo "inbox: OK"

# Functional — grep for new SKIP_NOTIFY conditions
grep -n "SKIP_NOTIFY=true" scripts/vps/pueue-callback.sh
# Expected: 4 lines (reflect + spark + autopilot + qa)

grep -n "SILENT_SKILLS\|Skipping pre-dispatch" scripts/vps/inbox-processor.sh
# Expected: skill check block present
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Spark/autopilot/qa success → no Telegram notification
- [ ] Spark/autopilot/qa failure → Telegram notification sent
- [ ] Reflect → still silenced (regression check)
- [ ] Pending-events → still written for all skills
- [ ] inbox pre-dispatch → silenced for spark/autopilot/qa

### Tests
- [ ] All eval criteria pass (EC-1 through EC-7)
- [ ] bash -n syntax check passes for both files

### Acceptance Verification
- [ ] All Smoke checks (AV-S1, AV-S2) pass
- [ ] All Functional checks (AV-F1, AV-F2, AV-F3) pass
- [ ] Verify Command runs without errors

### Technical
- [ ] No regressions in existing notification logic
- [ ] Callback log shows skip reasons for debugging

---

## Autopilot Log
[Auto-populated by autopilot during execution]
