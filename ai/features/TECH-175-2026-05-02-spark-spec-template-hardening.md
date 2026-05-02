---
id: TECH-175
type: TECH
status: queued
priority: P2
risk: R2
created: 2026-05-02
---

# TECH-175 — Spark spec template hardening (DO-NOT-REMOVE markers)

**Status:** queued
**Priority:** P2
**Risk:** R2

---

## Problem

Даже после TECH-167 (canonical format + emit-time linter), потенциальные источники format drift'а:

1. Оператор/LLM при манипуляциях со спекой случайно удаляет маркер `<!-- callback-allowlist v1 -->`.
2. Reflect / planner / другой агент перезаписывает секцию своим форматом.
3. Spark v3 в будущем выпустит spec формата v2, не совместимого с v1.

---

## Goal

1. **DO-NOT-REMOVE markers** в спеке:
   ```markdown
   <!-- DLD-CALLBACK-MARKER-START v1 -->
   <!-- callback-allowlist v1: backticked paths only, one per row.
        DO NOT EDIT THIS SECTION manually after autopilot starts.
        Format is parsed by scripts/vps/callback.py — see TECH-167. -->
   ## Allowed Files

   - `path1`
   - `path2`
   <!-- DLD-CALLBACK-MARKER-END -->
   ```

2. **Schema versioning**: маркер несёт версию (`v1`, `v2`...). Callback parser выбирает routine по версии. Несовместимость → degrade-closed.

3. **Pre-commit hook (DLD repo)** для editing спек в `ai/features/`: `git diff` показывает изменения внутри marker — fail with warning "are you sure you want to edit allowlist after spec is queued?"

4. **Spark template — full spec skeleton** с маркерами на всех "владеемых callback'ом" секциях:
   - `<!-- DLD-CALLBACK-MARKER-START v1 -->` `## Allowed Files` `<!-- END -->`
   - `<!-- DLD-CALLBACK-MARKER-START v1 -->` `**Status:**` `<!-- END -->`
   - `<!-- DLD-CALLBACK-MARKER-START v1 -->` `**Blocked Reason:**` `<!-- END -->`

5. **Spec linter** — `scripts/vps/spec_lint.py <spec_path>` проверяет:
   - Маркеры присутствуют и парные.
   - Версии совпадают.
   - Содержимое внутри markers соответствует schema.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `.claude/skills/spark/feature-mode.md`
- `.claude/skills/spark/completion.md`
- `.claude/agents/spark/facilitator.md`
- `template/.claude/skills/spark/feature-mode.md`
- `template/.claude/skills/spark/completion.md`
- `template/.claude/agents/spark/facilitator.md`
- `scripts/vps/callback.py`
- `scripts/vps/spec_lint.py`
- `.git-hooks/pre-commit`
- `tests/unit/test_spec_lint.py`

---

## Tasks

1. **Template update** — Spark feature-mode.md выпускает спеки с marker'ами.
2. **Callback parser** — recognize markers, парсить **внутри** них; отсутствие markers → fallback на TECH-167 v1 без markers (legacy).
3. **`spec_lint.py`** — standalone CLI.
4. **Pre-commit hook** в DLD repo — non-blocking warning, потому что иногда правки внутри markers легитимны (operator override).
5. **Documentation** в TECH-173 (orchestrator docs) — отдельный раздел про markers schema.
6. **Tests**: парсер на спеке с markers / без / с broken markers.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Spec с правильными markers — parsed correctly |
| EC-2 | deterministic | Spec без markers (legacy) — fallback на TECH-167 logic |
| EC-3 | deterministic | Spec с unmatched markers — degrade-closed |
| EC-4 | deterministic | Spec с unknown version (v9) — degrade-closed + warning |
| EC-5 | integration | Pre-commit hook предупреждает на правке внутри markers |
| EC-6 | integration | Spark выпускает spec с правильными markers |
