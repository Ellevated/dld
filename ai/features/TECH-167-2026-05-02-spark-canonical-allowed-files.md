---
id: TECH-167
type: TECH
status: queued
priority: P0
risk: R1
created: 2026-05-02
---

# TECH-167 — Spark canonical `## Allowed Files` section + emit-time linter

**Status:** queued
**Priority:** P0
**Risk:** R1 (cross-cutting — затрагивает все будущие спеки во всех проектах)

---

## Problem

Парсер callback'а (TECH-166) ловит **80%** спек, остальные 20% демоутятся в `blocked` ложно из-за format drift:

| Вариант | Где встречается | Парсер ловит |
|---|---|---|
| `## Allowed Files` | большинство | ✓ |
| `## Allowed Files (whitelist|canonical|STRICT|...)` | awardybot, gipotenuza | ✓ (после TECH-166 hotfix) |
| `## Updated Allowed Files` | gipotenuza | ✓ |
| `## Files Allowed to Modify` | dowry, plpilot | ✓ |
| `## Files` | FTR-846 awardybot | ✗ |
| `## Affected Files` | TECH-840 awardybot | ✗ |
| `### Allowed Files (whitelist)` (H3) | FTR-851 awardybot | ✗ |
| Секции нет вообще | ~170 спек legacy | ✗ |
| Paths внутри ` ``` ` fenced без backticks | FTR-882 awardybot | ✗ (regex теряет paths) |

Решать regex-погоней — анти-паттерн, новые формы появятся завтра. **Корень: Spark не имеет жёсткого контракта на формат allowlist'а.**

---

## Goal

1. **Canonical format** — один-единственный шаблон секции, обязательный для всех новых спек:

   ```markdown
   ## Allowed Files

   <!-- callback-allowlist v1: backticked paths only, one per row -->

   - `path/to/file1.py`
   - `path/to/file2.sql`
   - `tests/path/to/test.py`
   ```

   Маркер `callback-allowlist v1` нужен для версионирования формата (v2 если когда-то поменяем).

2. **Spark emit-time linter** — pre-write hook в spark facilitator:
   - Section heading exactly `## Allowed Files` (case-sensitive, single H2, no suffix).
   - Marker `<!-- callback-allowlist v1 -->` присутствует.
   - Минимум 1 backticked path в bullet list внутри секции.
   - Каждая bullet строка — формат `` - `path` `` (опц. комментарий после).
   - При нарушении — **fail Spark output**, не пишем спеку, escalate в Telegram.

3. **Callback парсер v2** — переключаемся на маркер `<!-- callback-allowlist v1 -->`. Если маркера нет → degrade-closed (как сейчас). Если маркер есть → парсим строго: bullet + backtick. Никаких heading-вариантов больше.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `.claude/skills/spark/SKILL.md`
- `.claude/skills/spark/feature-mode.md`
- `.claude/skills/spark/completion.md`
- `.claude/agents/spark/facilitator.md`
- `template/.claude/skills/spark/SKILL.md`
- `template/.claude/skills/spark/feature-mode.md`
- `template/.claude/skills/spark/completion.md`
- `scripts/vps/callback.py`
- `tests/unit/test_callback_allowlist_v1.py`

---

## Tasks

1. **Spec template update**: в `feature-mode.md` (и template-mirror) — раздел Output Format добавить canonical block с маркером и пример.
2. **Spark facilitator pre-write check**: regex-валидатор в facilitator.md, fail с понятным сообщением.
3. **Spark `completion.md`**: явное правило "не писать spec файл если linter не прошёл — escalate в Telegram".
4. **Callback parser v2**: новые `_ALLOWED_FILES_V1_MARKER_RE`, `_ALLOWED_FILES_BULLET_RE`. Старые heading-вариантные regex остаются как fallback для legacy специй (degrade-open для них) — НО для спек с маркером v1 — strict mode, no fallback.
5. **Tests**: парсинг canonical + invalid форматов + legacy без маркера.
6. **Документация в CLAUDE.md** (DLD root + template): краткая выжимка формата для людей.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Parser v2 извлекает paths из канонической секции с маркером |
| EC-2 | deterministic | Parser v2 для legacy спеки без маркера → fallback на старую логику |
| EC-3 | deterministic | Parser v2 для спеки с маркером но broken bullets → degrade-closed |
| EC-4 | integration | Spark facilitator валит output без маркера/секции |
| EC-5 | integration | Spark facilitator валит output с пустой секцией |
| EC-6 | integration | Spark facilitator пропускает корректную секцию |
| EC-7 | deterministic | Existing спеки awardybot/dowry/etc. парсятся v2 как и раньше (regression) |
