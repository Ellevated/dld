# Feature: [TECH-183] Spark Verified References — grep-evidence gate for concrete refs in specs
**Status:** queued | **Priority:** P1 | **Date:** 2026-05-14

> Draft passed from AwardyBot reflect session 2026-05-14 (Finding #1). Formalize via `/spark` in the DLD repo before implementation.

## Why

Spark пишет в спеку конкретные ссылки — file paths, API endpoints, schema-поля, FSM/state-ключи, module paths, migration filenames — **не верифицируя их**. Расхождение ловится только в runtime автопилота (planner) или code-quality reviewer'ом, уже после того как спека ушла как готовая.

Три независимых случая за 3 дня (AwardyBot, 2026-05-12…14):

| Spec | Что было неверно в спеке | Реальность |
|------|--------------------------|------------|
| BUG-988 | CLI module path `src.cli.commands.flow_cost_guard`; файл описан как "extend" | `src.cli.flow_cost_guard` (без `commands/`); файла не существовало → create-from-scratch; пропущена stale строка 92 |
| FTR-999 | acceptance criterion с state-ключом `profile_demographics={}` | orphan-ключ; реальный FSM читает `_KEY_GENDER` / `_KEY_AGE` |
| FTR-997 | queryFn `GET /api/v2/buyer/earnings`, поле `data?.balance` | `GET /api/v2/buyer/earnings/balance`, схема `BalanceView { available_kopecks }` — reviewer назвал это "lying surface": компонент молча фолбэчил в empty state из-за 404 |

Прямая цитата сигнала BUG-988: *"Spark did not grep actual CLI module paths before writing the spec."*

**Внешнее подтверждение.** ctxt.dev *"Your AI Spec Is Already Stale"* (2026-03): агент трактует спеку как ground truth и «references a ghost API» — *"a wrong spec is a wrong input to every agent session"*, drift размножается «confirmation bias at machine speed». Contract-first практика (APITect, M. Hossain): контракт валидируется **до** генерации кода, не после.

## Context

`spark-codebase` агент (`template/.claude/agents/spark/codebase.md`) — один из 4 параллельных скаутов Phase 2. У него уже есть:
- Rule #1 «Grep first — no assumptions about "probably exists"»
- Output-таблицы с колонками `File:line`

Проблема: правило **декларативно, но не enforced**. Скаут пишет путь/endpoint/ключ без сопровождающей grep-команды и её результата, никто это не проверяет, и Phase 6 (6 validation gates) тоже не проверяет — gates валидируют структуру спеки, не достоверность её ссылок.

Решение — закрыть петлю в двух местах:
1. **codebase.md** — обязательная секция `## Verified References` в `research-codebase.md`: каждая конкретная ссылка, которую скаут отдаёт в спеку, сопровождается grep/find-командой и её фактическим результатом (`file:line` или «not found»).
2. **feature-mode.md** — новый **Gate 8: Verified References** в Phase 6: каждая конкретная ссылка в написанной спеке (пути в `## Allowed Files`, endpoints в `## Implementation Plan`, schema-поля, state-ключи) должна трассироваться в `research-codebase.md → ## Verified References`. Untraced reference → reject, возврат в Phase 3.

---

## Scope

**In scope:**
- Новая mandatory output-секция `## Verified References` в `template/.claude/agents/spark/codebase.md` (формат + правила + пример)
- Усиление Rule #1 в codebase.md: «grep-evidence required» — запрет писать path/endpoint/key без verifying-команды и её результата
- Новый **Gate 8: Verified References** в Phase 6 `template/.claude/skills/spark/feature-mode.md`
- Обновление HARD-GATE счётчика Phase 6: «7 validation gates» → «8»
- Обновление Phase 2 exit-criteria (HARD-GATE на строке ~216): `research-codebase.md` обязан содержать секцию `## Verified References`
- Template-sync: `template/.claude/` → корневой `.claude/` (оба файла)
- Negative-probe в тесты Spark (если есть test corpus для spec-валидации) — спека с untraced reference падает Gate 8

**Out of scope:**
- AST-based deterministic linter, резолвящий каждый `file:line` в реальный файл (кандидат на follow-up TECH — Gate 8 пока LLM-проверка трассируемости, не файловый резолвинг)
- Изменение остальных 3 скаутов (external / patterns / devil) — у них нет codebase-references
- Верификация ссылок на внешние URL (Research Sources) — отдельная зона ответственности external-скаута
- Ретро-аудит уже существующих спеков в `ai/features/`

---

## Impact Tree Analysis

### Step 1: UP — who uses?

| File | Used by | Function |
|------|---------|----------|
| `template/.claude/agents/spark/codebase.md` | Spark Phase 2 (Research) | один из 4 параллельных скаутов → `research-codebase.md` |
| `template/.claude/skills/spark/feature-mode.md` | Spark Phase 3/5/6, autopilot | SSOT шаблона спеки + validation gates |
| `.claude/agents/spark/codebase.md`, `.claude/skills/spark/feature-mode.md` | рабочие копии (sync target) | DLD использует их для собственной разработки |

### Step 2: DOWN — what depends on?

- `codebase.md` — зависит от инструментов: `Grep`, `Glob`, `Read`, `Bash`. Новых зависимостей нет.
- `feature-mode.md` — Gate 8 читает `research-codebase.md` (уже в SESSION_DIR Phase 2) + написанную спеку. Новых зависимостей нет.

### Step 3: BY TERM

```bash
grep -rn "Verified References\|Gate 8\|grep-evidence" . --include="*.md"
# Expected before impl: 0 results
```

### Step 4: CHECKLIST — mandatory folders

- [x] `template/.claude/agents/spark/` — codebase.md
- [x] `template/.claude/skills/spark/` — feature-mode.md
- [x] `.claude/agents/spark/`, `.claude/skills/spark/` — sync targets
- [x] `tests/` — проверить наличие spark spec-validation corpus для negative-probe
- [ ] `ai/glossary/` — N/A (нет доменного глоссария для Spark internals)

### Step 5: DUAL SYSTEM check

N/A — не меняем источник данных. Меняем поведение скаута и добавляем gate; `research-codebase.md` остаётся единственным артефактом Phase 2 codebase-скаута.

### Verification

- После реализации: `grep -c "Verified References" template/.claude/agents/spark/codebase.md` → ≥1
- После реализации: `grep -c "Gate 8" template/.claude/skills/spark/feature-mode.md` → ≥1
- После sync: `diff template/.claude/agents/spark/codebase.md .claude/agents/spark/codebase.md` → identical
- После sync: `diff template/.claude/skills/spark/feature-mode.md .claude/skills/spark/feature-mode.md` → identical
- HARD-GATE Phase 6 говорит «8 validation gates», не «7»

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row -->

ONLY the files listed below may be modified during implementation.

- `template/.claude/agents/spark/codebase.md`
- `template/.claude/skills/spark/feature-mode.md`
- `.claude/agents/spark/codebase.md`
- `.claude/skills/spark/feature-mode.md`
- `ai/backlog.md`

(Если test corpus для spec-валидации существует — добавить соответствующий тест-файл при формализации через `/spark`.)

---

## Design (draft sketch — refine in /spark Phase 5)

### `## Verified References` section format (output of codebase.md)

Дописывается в `research-codebase.md` после `## Affected Files`, перед `## Risks`:

```markdown
## Verified References

Каждая конкретная ссылка, попадающая в спеку, верифицирована командой ниже.
"not found" — тоже валидный результат (значит файл/endpoint надо создавать).

| Reference | Kind | Verify command | Result |
|-----------|------|----------------|--------|
| `src/cli/flow_cost_guard.py` | module path | `find src -name flow_cost_guard.py` | `src/cli/flow_cost_guard.py` ✓ |
| `GET /api/v2/buyer/earnings/balance` | endpoint | `grep -rn "earnings/balance" src/api/v2/buyer/` | `earnings.py:41` ✓ |
| `_KEY_GENDER` | FSM state key | `grep -rn "_KEY_GENDER" src/domains/buyer/` | `creator_verify_profile.py:58` ✓ |
| `BalanceView.available_kopecks` | schema field | `grep -rn "available_kopecks" src/api/v2/buyer/schemas.py` | `schemas.py:150` ✓ |

**Kinds tracked:** module/file path · API endpoint · schema/model field · FSM/state key · migration filename · function/class name cited as reuse target.
```

### Rule #1 rewrite (codebase.md)

> **1. Grep-evidence required** — никакой path / endpoint / schema-field / state-key не попадает в output без verifying-команды и её фактического результата в `## Verified References`. "Probably exists" запрещено. "not found" — валидный результат (сигнал create-from-scratch для спеки).

### Gate 8 (feature-mode.md Phase 6)

```
### Gate 8: Verified References
□ research-codebase.md содержит секцию ## Verified References?
□ Каждый concrete reference в спеке (Allowed Files paths, Implementation Plan
  endpoints, schema fields, state keys) трассируется в Verified References?
□ Нет reference со статусом "assumed" / без verify-команды?

Soft sub-rule: если Phase 2 codebase-скаут провалился (degraded mode) →
Gate 8 auto-pass с пометкой "Gate 8: auto-pass (no codebase research)".
```

HARD-GATE Phase 6: «DO NOT proceed to Phase 7 until all **8** validation gates pass».

---

## Eval Criteria (draft — expand in /spark)

| ID | Scenario | Expected | Type | Priority |
|----|----------|----------|------|----------|
| EC-1 | codebase.md содержит секцию `## Verified References` с форматом-таблицей и примером | grep находит секцию + ≥1 пример-строку | deterministic | P0 |
| EC-2 | Rule #1 в codebase.md переписан на «grep-evidence required» | старый текст «Grep first — no assumptions» отсутствует, новый присутствует | deterministic | P0 |
| EC-3 | feature-mode.md Phase 6 содержит `### Gate 8: Verified References` | grep находит Gate 8 | deterministic | P0 |
| EC-4 | HARD-GATE Phase 6 обновлён на «8 validation gates» | нет вхождения «7 validation gates» в Phase 6 HARD-GATE | deterministic | P0 |
| EC-5 | Phase 2 exit HARD-GATE требует `## Verified References` в research-codebase.md | grep находит требование | deterministic | P1 |
| EC-6 | template/ и .claude/ копии обоих файлов идентичны после sync | `diff` → 0 | deterministic | P0 |
| EC-7 | (если test corpus есть) спека с untraced reference падает Gate 8, спека с полной трассировкой проходит | negative-probe red, positive green | integration | P1 |

---

## Definition of Done

- [ ] `## Verified References` секция добавлена в codebase.md (формат + правила + пример)
- [ ] Rule #1 codebase.md переписан на grep-evidence-required
- [ ] Gate 8 добавлен в feature-mode.md Phase 6
- [ ] HARD-GATE Phase 6 счётчик: 7 → 8
- [ ] Phase 2 exit-criteria требует `## Verified References`
- [ ] template/ → .claude/ sync выполнен, `diff` обоих файлов = 0
- [ ] EC-1…EC-6 pass (EC-7 если corpus существует)
- [ ] backlog.md: TECH-183 строка обновлена на статус по итогу
