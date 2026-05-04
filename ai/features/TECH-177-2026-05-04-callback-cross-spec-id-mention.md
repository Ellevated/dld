# TECH-177 — Callback: cross-spec ID mention causes false-positive done

**Status:** queued
**Priority:** P1
**Risk:** R1
**Created:** 2026-05-04

---

## Problem

`callback.py::_spec_has_merged_implementation` помечает спеку как уже-смерженную (и через цепочку в `verify_status_sync` — auto-close в `done`), когда коммит **соседней** спеки случайно упоминает её ID в commit message.

**Симптом (awardybot, 2026-05-04):**
- Коммит, реализующий FTR-923, содержал упоминание `FTR-925` в теле сообщения (cross-reference).
- `_spec_has_merged_implementation(spec_id="FTR-925", allowed=<FTR-925 files>)` нашёл этот коммит, потому что:
  - `git log --grep FTR-925` матчит body коммита
  - `-- <allowed>` матчит, если файлы FTR-925 пересекаются с тем, что коммит реально трогал (типичная ситуация для смежных задач в одном модуле)
- Callback пометил FTR-925 как `done`.
- Operator восстановил `queued` вручную (awardybot commit `d469e069`).

## Root Cause

`git log --grep <ID>` слишком лоозный matcher: ловит любое упоминание ID в любой части сообщения, включая "see also FTR-XXX", "supersedes FTR-XXX", `Co-authored-by: ... FTR-XXX`, ссылки в footer и т.д.

Path-фильтр `-- <allowed>` не спасает, если Allowed Files соседних спек пересекаются (один модуль, общие файлы).

## Fix Direction

Ужесточить matcher в `_spec_has_merged_implementation` — коммит «реализует» спеку только если **subject** (первая строка) явно указывает на этот ID в одном из канонических форматов:

- `feat(FTR-925): ...`
- `fix(FTR-925): ...`
- `<type>(FTR-925)[!]: ...` для всех Conventional Commits типов
- `merge FTR-925` (для merge-коммитов из autopilot)
- `FTR-925: ...` (legacy bare)

Тело коммита (body, footer, trailers) — **не учитывается**.

Реализация:
1. Заменить `--grep` на post-filter: `git log --all --pretty='%h%x00%s' -- <allowed>` → парсить subject → regex проверка.
2. Regex: `^(?:[a-z]+(?:\([^)]*\))?!?:\s*.*\b{ID}\b|merge\s+{ID}\b|{ID}:\s)` — но строже: ID только в `(...)` или в начале subject, не в произвольном месте.
3. Аналогично пересмотреть `is_merged_to_develop` (та же дыра, но используется только для диагностики — низкий приоритет).

## Allowed Files

<!-- callback-allowlist v1 -->
- `scripts/vps/callback.py`
- `scripts/vps/tests/test_callback.py`
<!-- callback-allowlist END -->

## Tests

1. **Unit: cross-mention в body не матчит.** Коммит `feat(FTR-923): impl X\n\nsee also FTR-925` + allowed=[`a.py`] (touched) → `_spec_has_merged_implementation("FTR-925", ["a.py"])` returns `(False, [])`.
2. **Unit: subject в формате `feat(SPEC): ...` матчит.** Коммит `feat(FTR-925): impl Y` touching `a.py` → `_spec_has_merged_implementation("FTR-925", ["a.py"])` returns `(True, [<sha>])`.
3. **Unit: legacy `FTR-925: ...` subject матчит.** Коммит `FTR-925: impl` touching `a.py` → `(True, [<sha>])`.
4. **Unit: `merge FTR-925` матчит.** Коммит subject `merge FTR-925: ...` → `(True, [...])`.
5. **Unit: ID в footer/trailer не матчит.** `feat(X): ...\n\nRefs: FTR-925` → `(False, [])`.
6. **Regression:** существующие зелёные тесты на `_spec_has_merged_implementation` остаются зелёными.

## Acceptance

- [ ] Cross-mention coccurence в body не вызывает auto-close
- [ ] Корректные autopilot/merge коммиты по-прежнему обнаруживаются
- [ ] Audit log (`callback-audit.jsonl`) содержит причину match для трассировки
- [ ] Regression-фикстуры из awardybot 2026-05-04 incident включены в test_callback.py

## Out of Scope

- Изменение формата commit messages (это требование к autopilot, отдельный TECH).
- Tightening `is_merged_to_develop` (диагностический, не блокирует).

## Related

- TECH-166: implementation guard (исходный гард)
- TECH-170: `--all` flag для feature-branch видимости
- TECH-176: merged-before-started_at (аналогичная по природе дыра)
