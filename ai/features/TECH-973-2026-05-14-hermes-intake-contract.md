# Feature: [TECH-973] Hermes intake contract — full status lifecycle + supervisory docs
<!-- DLD-CALLBACK-MARKER-START v1 -->
**Status:** queued | **Priority:** P1 | **Date:** 2026-05-14
<!-- DLD-CALLBACK-MARKER-END -->

<!-- DLD-CALLBACK-MARKER-START v1 -->
<!-- **Blocked Reason:** populated by callback.py when guard demotes to blocked -->
<!-- DLD-CALLBACK-MARKER-END -->

## Why

TECH-181 закрыл hard gate: orchestrator `scan_inbox()` диспатчит только `Status: queued`. Но это лишь нижняя половина контракта — внутренняя стенка между inbox и Spark.

Верхняя половина (Hermes-side) до сих пор не задокументирована в репозитории:
- нет SSOT по статусам `draft`/`clarifying`/`stale`/`rejected`/`queued`/`processing`/`done` — каждый источник (Telegram-бридж, QA, reflect, autopilot post-mortem) может писать в `ai/inbox/` что угодно;
- доки и агенты всё ещё ссылаются на **OpenClaw** (reflect/SKILL.md, audit/night-mode.md, bughunt/completion.md, rules/dependencies.md), хотя OpenClaw заменён на Hermes;
- нет `ai/inbox/README.md` — новички (и сам Hermes как LLM-агент) не имеют куда посмотреть, чтобы понять lifecycle файла intake.

Бизнес-следствие: Hermes как conversational supervisor работает на честном слове founder'а, любой регресс источника снова приведёт к тому, что Spark получит сырую мысль из Telegram и потратит автопилотный слот.

## Context

- TECH-181 (done) — orchestrator-side status gate.
- TECH-157 (done) — OpenClaw immediate-wake интеграция; заменена Hermes.
- Reflect и QA skills уже **не пишут** в inbox напрямую (см. `reflect/SKILL.md` step 5) — они кладут артефакты в `ai/reflect/` и QA-отчёты, что Hermes потом просматривает. Эта инвариант нужна документировать как контракт, а не как «случайно так получилось».
- Файлы со ссылками на OpenClaw нужно переименовать в Hermes (или нейтрально «supervisor») без изменения поведения.

---

## Scope

**In scope:**
- Создать `ai/inbox/README.md` с SSOT по статусам intake-файла, eligibility-таблицей и обязанностями Hermes.
- Обновить `.claude/rules/architecture.md` — добавить ADR-022 «Hermes intake supervisor; QA/reflect не self-loop в inbox=queued».
- Заменить упоминания OpenClaw на Hermes в:
  - `.claude/skills/reflect/SKILL.md`
  - `.claude/skills/audit/night-mode.md`
  - `.claude/skills/bughunt/completion.md`
  - `.claude/rules/dependencies.md`
- Зафиксировать pattern «post-autopilot QA/reflect выходы не пишут `queued` в inbox» как тест/линт в существующем `scripts/vps/tests/test_orchestrator.py` (regression: scan_inbox + сценарий, что reflect-артефакт в `ai/reflect/` не подбирается scan_inbox).
- Status lifecycle в README.md должен ровно совпадать со списком `_VALID_STATUSES` (`scripts/vps/callback.py:417`) и regex в `scan_inbox` (`scripts/vps/orchestrator.py:326`) — если расхождение, документ источник правды для inbox-файлов, не путать с backlog-статусами specs.

**Out of scope:**
- Реализация самого Hermes-бота (живёт вне репо).
- Реинтродукция OpenClaw.
- Логика автоматического промоушена `draft → queued` (по дизайну делает Hermes с участием Олега).
- Изменения orchestrator.py — TECH-181 уже сделал hard gate.

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `OpenClaw` упоминается в 4 файлах (см. Scope). Все — документация/инструкции для агентов, кода не задевает.
- `ai/inbox/README.md` — новый файл, ни на кого не ссылается.

### Step 2: DOWN — what depends on?
- README.md → читают: founder, Hermes (LLM-агент через context), любой новый contributor.
- ADR-022 → читают агенты при context-load.

### Step 3: BY TERM — grep
- `grep -rn "OpenClaw" .claude/ ai/` → 4 файла (см. ниже).
- `grep -n "ai/inbox" scripts/vps/orchestrator.py` → один call `scan_inbox()` (не трогаем).

| File | Line | Status | Action |
|------|------|--------|--------|
| `.claude/skills/reflect/SKILL.md` | 110, 182 | OpenClaw mention | rename to Hermes |
| `.claude/skills/audit/night-mode.md` | grep hit | OpenClaw mention | rename to Hermes |
| `.claude/skills/bughunt/completion.md` | grep hit | OpenClaw mention | rename to Hermes |
| `.claude/rules/dependencies.md` | grep hit | OpenClaw mention | rename to Hermes |

### Step 4: CHECKLIST
- [x] `tests/**` → добавляем regression в `scripts/vps/tests/test_orchestrator.py`.
- [x] `db/migrations/**` → N/A.
- [x] `ai/glossary/**` → N/A (не money).

### Verification
- [ ] `grep -rn "OpenClaw" .claude/ ai/` = 0 (или явное «бывший OpenClaw, ныне Hermes» в одной строке-сноске).
- [ ] `ai/inbox/README.md` ссылается на `_VALID_STATUSES` и `scan_inbox` regex как SSOT.

---

<!-- DLD-CALLBACK-MARKER-START v1 -->
## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `ai/inbox/README.md` — new SSOT for intake status lifecycle (NEW)
- `.claude/rules/architecture.md` — add ADR-022 Hermes supervisor (modify)
- `.claude/skills/reflect/SKILL.md` — rename OpenClaw → Hermes (modify)
- `.claude/skills/audit/night-mode.md` — rename OpenClaw → Hermes (modify)
- `.claude/skills/bughunt/completion.md` — rename OpenClaw → Hermes (modify)
- `.claude/rules/dependencies.md` — rename OpenClaw → Hermes (modify)
- `scripts/vps/tests/test_orchestrator.py` — regression for scan_inbox status gate (modify)
- `ai/backlog.md` — add this task entry (modify)
- `ai/features/TECH-973-2026-05-14-hermes-intake-contract.md` — this spec (NEW)

<!-- DLD-CALLBACK-MARKER-END -->

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator / intake
**Cross-cutting:** process governance (Hermes ↔ Spark separation of concerns)
**Data model:** N/A (documentation + regression test only)

---

## Historical Risks

<!-- lessons-binding v1 -->

none — `ai/lessons/` для домена intake пока не заполнен.

---

## Approaches

### Approach 1: README + ADR + rename (selected)
**Summary:** Минимальный документационный слой поверх уже работающего TECH-181 hard gate. SSOT — `ai/inbox/README.md`, ADR-022 для каноничности, OpenClaw → Hermes rename.
**Pros:** дёшево, ничего не ломает, фиксирует инвариант текстом и одним regression-тестом.
**Cons:** опирается на Hermes-агента вне репо — если Hermes сломается, gate всё равно держит.

### Approach 2: Hard-enforce status в callback при записи в inbox
**Summary:** Завести валидатор, отклоняющий запись в `ai/inbox/` со `Status: queued` от любого процесса, кроме Hermes.
**Pros:** defense-in-depth.
**Cons:** требует ACL/identity, переусложнение. YAGNI: scan_inbox-gate уже не дёрнет Spark, даже если кто-то напишет `queued` — потому что Hermes контролирует issue источник.

### Selected: 1
**Rationale:** TECH-181 уже закрыл machine-enforcement. Не хватает SSOT-документации и единого языка. Approach 2 — over-engineering для текущей стадии.

---

## Design

### Status lifecycle (SSOT, попадает в README.md)

| Status | Кто пишет | Eligible for `scan_inbox` dispatch? | Описание |
|--------|-----------|--------------------------------------|----------|
| `draft` | author / source-bridge / Telegram | ❌ | Сырая мысль, артефакт QA/reflect, raw idea. |
| `clarifying` | Hermes | ❌ | Hermes задал вопрос Олегу, ждёт ответа. |
| `stale` | Hermes | ❌ | Утратило актуальность, кандидат на архив. |
| `rejected` | Hermes | ❌ | Закрыто Олегом, не обрабатывать. |
| `queued` | **только Hermes** | ✅ | Business-complete brief, готов к Spark. |
| `processing` | orchestrator (`scan_inbox`) | — | Уже отдано в Spark/autopilot. |
| `done` | autopilot / callback | — | Item конвертирован в spec или закрыт. |

### ADR-022

> Hermes — единственный writer статуса `queued` в `ai/inbox/`. Все остальные источники (QA-отчёты, reflect findings, post-autopilot события, Telegram-бридж) пишут intake-файлы со `Status: draft`. Orchestrator `scan_inbox()` дёргает Spark только на `queued` (см. TECH-181). QA/reflect артефакты живут в `ai/reflect/`, `ai/qa/` или внутри уже существующих spec, а не в inbox.

### Regression test

В `scripts/vps/tests/test_orchestrator.py` добавить:
1. `test_scan_inbox_ignores_draft` — `Status: draft` не дёргает pueue.
2. `test_scan_inbox_ignores_clarifying_stale_rejected` — три статуса не дёргают pueue.
3. `test_scan_inbox_dispatches_queued_only` — happy path (если ещё нет — extend).

---

## UI Event Completeness

N/A — не UI feature.

---

## Implementation Plan

### Research Sources
- TECH-181 spec (`ai/features/TECH-181-...md`) — оригинальный status gate.
- `scripts/vps/orchestrator.py:315-340` — `scan_inbox` reference.
- `scripts/vps/callback.py:417` — `_VALID_STATUSES` SSOT.

### Task 1: Create `ai/inbox/README.md`
**Type:** doc
**Files:** create `ai/inbox/README.md`
**Pattern:** TECH-181 status table (re-use wording, expand to 7 statuses).
**Acceptance:** README существует, содержит таблицу из Design, ссылается на TECH-181 и `scan_inbox` regex.

### Task 2: Add ADR-022 to architecture.md
**Type:** doc
**Files:** modify `.claude/rules/architecture.md`
**Acceptance:** ADR-022 row добавлен в ADR-таблицу с датой 2026-05.

### Task 3: Rename OpenClaw → Hermes in 4 files
**Type:** doc
**Files:** modify reflect/SKILL.md, audit/night-mode.md, bughunt/completion.md, rules/dependencies.md
**Acceptance:** `grep -rn "OpenClaw" .claude/` = 0 (или одна строка-сноска «бывший OpenClaw»).

### Task 4: Regression tests for scan_inbox
**Type:** test
**Files:** modify `scripts/vps/tests/test_orchestrator.py`
**Acceptance:** 3 теста зелёные локально и в CI.

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Hermes читает draft из inbox | - | existing (вне репо) |
| 2 | Hermes сверяется с status lifecycle | Task 1 | ✓ |
| 3 | Hermes промоутит → queued | - | existing (вне репо) |
| 4 | Orchestrator scan_inbox подбирает только queued | - | existing (TECH-181) |
| 5 | QA/reflect не self-loop'ятся в queued | Task 2, Task 4 | ✓ |
| 6 | Доки используют «Hermes» вместо «OpenClaw» | Task 3 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | scan_inbox игнорирует draft | inbox-файл `Status: draft` | pueue add НЕ вызван | deterministic | TECH-181 + regression | P0 |
| EC-2 | scan_inbox игнорирует clarifying/stale/rejected | три файла со статусами | pueue add НЕ вызван | deterministic | devil | P0 |
| EC-3 | scan_inbox диспатчит queued | inbox-файл `Status: queued` | pueue add вызван, Status → processing | deterministic | happy path | P0 |
| EC-4 | grep OpenClaw в .claude/ | `grep -rn "OpenClaw" .claude/` | 0 hits (или одна явная сноска) | deterministic | task acceptance | P1 |
| EC-5 | inbox/README.md существует и содержит таблицу | file exists + grep `\| queued \|` | hit ≥1 | deterministic | task acceptance | P1 |

### Coverage Summary
- Deterministic: 5 | Integration: 0 | LLM-Judge: 0 | Total: 5

### TDD Order
1. EC-1 → fail → impl Task 4 → pass
2. EC-2 → same
3. EC-3 → same
4. EC-4/EC-5 — после Task 1/3.

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command | Expected | Timeout |
|----|-------|---------|----------|---------|
| AV-S1 | README exists | `test -f ai/inbox/README.md` | exit 0 | 1s |
| AV-S2 | tests collect | `pytest scripts/vps/tests/test_orchestrator.py --collect-only` | exit 0 | 10s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Regression suite green | - | `pytest scripts/vps/tests/test_orchestrator.py -k scan_inbox` | all pass |
| AV-F2 | OpenClaw rename done | - | `grep -rn "OpenClaw" .claude/ \|\| true` | 0 hits |

### Verify Command

```bash
test -f ai/inbox/README.md
pytest scripts/vps/tests/test_orchestrator.py -k scan_inbox -q
! grep -rn "OpenClaw" .claude/ ai/inbox/README.md
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `ai/inbox/README.md` создан с полной таблицей статусов.
- [ ] ADR-022 добавлен в `.claude/rules/architecture.md`.
- [ ] OpenClaw → Hermes rename выполнен в 4 файлах.

### Tests
- [ ] 3 regression-теста для `scan_inbox` зелёные.
- [ ] Coverage не упал.

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 проходят локально.

### Technical
- [ ] `./test fast` зелёный.
- [ ] No regressions.

---

## Autopilot Log
[Auto-populated by autopilot during execution]
