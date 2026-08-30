# Feature: [ARCH-219] Identity работы — в git, а не в тексте коммита (epic)

**Priority:** P0 | **Date:** 2026-08-30
**Children:** TECH-220 (гейт по предку ветки), TECH-221 (продолжение salvage-ветки, AFTER TECH-220)

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Оркестратор узнаёт, что спека реализована, по **тексту** заголовка коммита. Всё, что за этим
последовало, — цепочка подпорок под одно решение: 12 принимаемых форм в `match_subject`, четыре
волны «ещё одну форму» (BUG-192, BUG-338..347, TECH-177, TECH-210), шаблон коммита в промпте девяти
проектов, и наконец предложение хука, который заставит модель писать текст правильно. Founder,
30.08: «очередной костыль? сколько можно?».

Аудит 16–30.08 (`docs/2026-08-30-orchestrator-failure-audit.md`): 38 % прогонов падают, из 61
вердикта гейта честных `done` — 11; 31 — ложный `no_merged_implementation`; 13 прогонов убиты
таймаутом с работой на salvage-ветках, которых гейт не видит, а повторный диспатч уничтожает.

## Решение

В DLD нет человека, который мержит в develop. Мержит только Claude по `finishing.md`: зелёный
`./test ci` → `--ff-only` из ветки `<type>/<ID>`. Значит **факт «ветка влита» и есть доказательство
прохождения протокола** — git хранит его без регекса и без участия модели.

| Ребёнок | Что делает | Закрывает |
|---|---|---|
| **TECH-220** | `gate_logic.find_implementation`: primary — `merge-base --is-ancestor origin/<type>/<ID> origin/develop` + пересечение диффа с allowlist без bookkeeping; subject-регекс — deprecated-фолбэк с метрикой `gate_via`; одна функция во всех четырёх точках вызова; карта префиксов ветки одной функцией (GROWTH → `growth/`) | причина №1 аудита (`{scope}`-слепота), без правки даунстримов |
| **TECH-221** | `branch_state` + вердикт `branch_pushed_not_merged:<N>`; PHASE 0 sweep не трогает такую ветку; шаг 5 переиспользует ветку и делает rebase; диспатч передаёт флаг продолжения; обе копии промптов | причина №2 аудита (потеря работы после таймаута) |

**Дата смерти регекса:** когда `gate_via=subject` не срабатывает 30 дней подряд — отдельная TECH
удаляет `match_subject`, `find_implementation_commit` и 36 их тестов.

## Что epic НЕ делает

- Не поднимает `TIMEOUT_SECONDS` и не трогает Bash-таймаут — причина таймаутов разобрана и
  закрыта отдельно (`2497f61`: `BASH_DEFAULT_TIMEOUT_MS`, crafty, slot-admin).
- Не добавляет хук на subject коммита.
- Не меняет Rule 7 (done терминален) и «origin/develop-only».

## Scope

**In scope:** только координация детей; сам epic кода не несёт.
**Out of scope:** всё, что перечислено в детях.

---

## Impact Tree Analysis

Полный анализ — в детях. Здесь: `grep -rn "find_implementation_commit" scripts/vps/*.py` → 4 точки
вызова (TECH-220); `grep -n "git worktree add" .claude/skills/autopilot/*.md template/.claude/skills/autopilot/*.md`
→ 4 места (TECH-221).

### Step 4: CHECKLIST
- [x] `tests/**` — в детях
- [x] `template/` — TECH-221 правит обе копии промптов; `scripts/vps/` в template отсутствует

### Verification
- [x] Каждый файл детей — в их Allowed Files

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `docs/orchestrator/README.md` — абзац «как гейт узнаёт о реализации» после закрытия детей (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — fail-closed
**Data model:** без изменений

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

Gate 7 auto-pass (no lessons bank). См. детей.

---

## Approaches

См. TECH-220 §Approaches (три подхода, выбран ancestry-primary) и TECH-221 §Approaches (продолжение
ветки против salvage-merge на зелёном).

### Selected: ancestry-primary + продолжение ветки
**Rationale:** единственная комбинация, где identity работы уходит из текста модели в git, а работа
после таймаута не сгорает.

---

## Design

Порядок: TECH-220 → TECH-221 → абзац в `docs/orchestrator/README.md` (этот epic).

---

## Implementation Plan

### Task 1: закрыть детей
**Type:** code
**Acceptance:** TECH-220 и TECH-221 — `done` в lifecycle

### Task 2: README оркестратора
**Type:** docs
**Files:**
  - modify: `docs/orchestrator/README.md`
**Acceptance:** абзац «Гейт: ancestry primary, subject deprecated» со ссылкой на метрику `gate_via`

### Execution Order
1 → 2

---

## Flow Coverage Matrix

| # | Шаг | Covered by | Status |
|---|---|---|---|
| 1 | Гейт по предку ветки | TECH-220 | ✓ |
| 2 | Продолжение ветки после таймаута | TECH-221 | ✓ |
| 3 | Документация | Task 2 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Дети закрыты | `ai/lifecycle/TECH-220.yaml`, `TECH-221.yaml` | `status: done` | deterministic | — | P0 |
| EC-2 | README | `grep -n "gate_via" docs/orchestrator/README.md` | ≥1 | deterministic | — | P1 |
| EC-3 | Метрика через 30 дней | `callback-audit.jsonl` | доля `gate_via=subject` → 0 | deterministic | — | P1 |

### Coverage Summary
Deterministic: 3 | Integration: 0 | LLM-Judge: 0 | Total: 3 (min 3 ✓)

### TDD Order
1. EC-1 → EC-2 → EC-3 (наблюдение)

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Дети done | `grep -h "^status" ai/lifecycle/TECH-220.yaml ai/lifecycle/TECH-221.yaml` | `done` ×2 | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Живой гейт на VPS | две недели после деплоя | `grep -c '"gate_via": "ancestry"' callback-audit.jsonl` | > 0, доля растёт |

### Verify Command

```bash
grep -h "^status" ai/lifecycle/TECH-220.yaml ai/lifecycle/TECH-221.yaml
grep -n "gate_via" docs/orchestrator/README.md
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] TECH-220, TECH-221 done
- [ ] README обновлён

### Tests
- [ ] EC-1, EC-2

### Acceptance Verification
- [ ] AV-S1; AV-F1 — наблюдение

### Technical
- [ ] Rule 7 и «origin/develop-only» не тронуты

---

## Autopilot Log
