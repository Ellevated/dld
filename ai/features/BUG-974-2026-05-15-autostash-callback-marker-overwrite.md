# Bug Fix: [BUG-974] Autostash silently overwrites fresh callback Status commits

<!-- DLD-CALLBACK-MARKER-START v1 -->
**Status:** done | **Priority:** P1 | **Date:** 2026-05-15
<!-- DLD-CALLBACK-MARKER-END -->

<!-- DLD-CALLBACK-MARKER-START v1 -->
<!-- **Blocked Reason:** populated by callback.py when guard demotes to blocked -->
<!-- DLD-CALLBACK-MARKER-END -->

## Symptom

После того как `callback.verify_status_sync` коммитит `Status: done` (или `blocked`) в spec/backlog и пушит в `origin/develop`, оркестратор на следующем 5-минутном цикле:

1. Видит грязное рабочее дерево проекта (любые M/D/?? — QA-отчёты, diary, мусор от прошлых ренеймов).
2. Делает `git stash push` (autostash; `orchestrator.py:251`).
3. `git pull --ff-only origin develop` — подтягивает свежий callback-коммит со `Status: done`.
4. `git stash pop` — **без конфликта** перезаписывает callback-коммит старой версией Status-блока.

Через 5 минут `scan_backlog` видит в working tree `Status: queued` → диспатчит уже выполненную задачу.

## Reproduction Steps (incident 2026-05-15)

1. dowry на develop, FTR-429 в `Status: done` (HEAD), working tree чистый.
2. Какой-либо процесс (QA, reflect, ручной edit) делает untracked-изменения в `ai/qa/*.md` и не коммитит.
3. Orchestrator-цикл 17:56: scan видит spec ещё queued (race с предыдущим pueue таском), диспатчит autopilot. Autopilot быстро выходит, callback пишет `Status: done` коммитом и пушит.
4. Orchestrator-цикл 18:02: working tree грязный (M `ai/backlog.md` где старый `queued` локально + ?? `ai/qa/`). `stash push` укладывает оба варианта; `pull` забирает done; `pop` без конфликта возвращает stash → backlog снова `queued`.
5. scan_backlog 18:02 видит `queued` → дёргает autopilot снова.
6. **Повторилось 6 раз: pueue 2691, 2694, 2697, 2700, 2704, 2708** — каждый по 11 turns, $0.58, итого ~$4 + qa/reflect overhead.

**Got:** Re-dispatch loop, autopilot 6 раз откатывает revert.
**Expected:** Один цикл, callback-коммит уважается, orchestrator не передиспатчивает done-спеки.

## Root Cause (5 Whys)

1. **Why** orchestrator re-dispatch done-спеки? → working tree содержит `Status: queued` поверх HEAD `Status: done`.
2. **Why** working tree содержит stale Status? → `git stash pop` после `pull` восстановил предыдущую версию.
3. **Why** pop тихо перезаписал свежий callback-коммит? → stash содержал старую версию того же файла; pop без конфликта применил её на новый HEAD (git merge без диагностики на смысловые секции).
4. **Why** `dfa026b` ("safe autostash", TECH-182) это не покрыл? → он защищает только **конфликтный** путь (stash остаётся на полке + лог оператору). Бесконфликтный pop остался по умолчанию.
5. **Why** callback-marker блоки уязвимы? → ADR-018/TECH-172 объявил callback единственным writer'ом этих секций, но orchestrator не знает про этот контракт и обращается с ними как с обычным текстом.

**ROOT CAUSE:** Бесконфликтный `git stash pop` после `pull` молча возвращает старую версию DLD-CALLBACK-MARKER блоков, нарушая ADR-018 (callback = sole writer).

## Fix Approach

После успешного `git stash pop` пройтись по всем файлам, затронутым этим pop'ом, и для каждой пары `DLD-CALLBACK-MARKER-START/END` секции сравнить working tree против HEAD. Если содержимое секции различается — **восстановить HEAD-вариант** (callback — единственный валидный источник).

Алгоритм (в `orchestrator.py:git_pull`, после `log.info("autostash popped cleanly: ...")`):

```python
def _restore_callback_markers_from_head(project_id, _git):
    """After successful stash pop, force HEAD content for any
    DLD-CALLBACK-MARKER-START/END block that diverges from HEAD.
    ADR-018: callback is the only valid writer of these sections.
    """
    diff = _git("diff", "--name-only", "HEAD", timeout=10)
    if diff.returncode != 0:
        return
    for rel_path in diff.stdout.splitlines():
        if not rel_path.strip():
            continue
        # Read HEAD blob + working tree
        head = _git("show", f"HEAD:{rel_path}", timeout=10)
        if head.returncode != 0:
            continue  # new file, skip
        head_text = head.stdout
        try:
            wt_text = Path(_git.cwd, rel_path).read_text()
        except OSError:
            continue
        merged = _merge_callback_markers(head_text, wt_text)
        if merged != wt_text:
            Path(_git.cwd, rel_path).write_text(merged)
            log.warning(
                "AUTOSTASH_CALLBACK_RESTORE: %s — DLD-CALLBACK-MARKER "
                "block restored from HEAD (stash pop tried to revert callback write)",
                rel_path,
            )

def _merge_callback_markers(head_text: str, wt_text: str) -> str:
    """Replace DLD-CALLBACK-MARKER-START/END blocks in wt_text with
    the corresponding blocks from head_text. Block count and order
    must match; on mismatch return wt_text unchanged (degrade-open)."""
    head_blocks = _extract_marker_blocks(head_text)
    wt_blocks = _extract_marker_blocks(wt_text)
    if len(head_blocks) != len(wt_blocks):
        return wt_text  # structure differs — bail out, log
    out = wt_text
    for (hs, _he, hbody), (ws, we, _wbody) in zip(head_blocks, wt_blocks):
        # replace by line-range (ws..we) with hbody
        ...
    return out
```

Регулярка `DLD-CALLBACK-MARKER-START v1` + `DLD-CALLBACK-MARKER-END` уже описана в `callback.py:592-593` (`_DLD_MARKER_START_RE`, `_DLD_MARKER_END_RE`). Можно перенести их в shared-модуль `scripts/vps/marker_utils.py` и заимпортить с обеих сторон.

**Поведение при degrade:**
- Файл не существует в HEAD → skip.
- Counts блоков различаются → log.warning + skip (не разрушаем структуру).
- Нет markers вообще → skip (обычный текстовый файл).

## Impact Tree Analysis

### Step 1: UP — кто вызывает изменения

- [x] `git_pull` в `orchestrator.py:215` — единственная точка autostash.
- [x] Вызывается из `_main_loop` (`orchestrator.py:536`) каждые 300с на каждый проект.

### Step 2: DOWN — от чего зависит

- [x] `_git` helper (orchestrator.py, локальный) — `subprocess` обёртка над git.
- [x] `_DLD_MARKER_START_RE` / `_DLD_MARKER_END_RE` — в callback.py:592-593.
- [x] Стандартная библиотека: `pathlib.Path`, `re`.

### Step 3: BY TERM — grep по проекту

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/orchestrator.py` | 215-289 | M | добавить вызов `_restore_callback_markers_from_head` после успешного pop |
| `scripts/vps/callback.py` | 591-625 | (export) | вынести `_DLD_MARKER_START_RE`/`_DLD_MARKER_END_RE` + extractor в shared utility |
| `scripts/vps/marker_utils.py` | new | C | shared regex + extractor для обоих модулей |
| `scripts/vps/tests/test_orchestrator.py` | new test | C | regression: autostash + callback Status drift scenario |

### Step 4: Mandatory folders checklist

- [x] `scripts/vps/tests/` — regression test обязателен.
- [x] `.claude/rules/dependencies.md` — обновить запись orchestrator.py с `marker_utils`.

### Step 5: Dual System

- Не применимо (нет миграции данных). Контракт ADR-018 не меняется, только усиливается.

### Verification

- [x] Все затронутые файлы в Allowed Files ниже.

## Research Sources

- ADR-018 (`.claude/rules/architecture.md`) — callback как единственный writer Status.
- TECH-166/172/182 — история эволюции guard'а и autostash'а.
- `dfa026b` — safe autostash, защита от потерь при конфликте.
- callback.py:592-625 — существующая логика парсинга DLD-CALLBACK-MARKER блоков.

## Allowed Files

<!-- callback-allowlist v1 -->
<!-- DLD-CALLBACK-MARKER-START v1 -->
- `scripts/vps/orchestrator.py` — добавить пост-pop callback-marker recovery
- `scripts/vps/callback.py` — экспортировать marker regex/extractor
- `scripts/vps/marker_utils.py` — shared util (новый файл)
- `scripts/vps/tests/test_orchestrator.py` — regression тест на autostash drift
- `scripts/vps/tests/test_marker_utils.py` — unit-тесты на extractor + merge (новый файл)
- `.claude/rules/dependencies.md` — обновить orchestrator → marker_utils
<!-- DLD-CALLBACK-MARKER-END -->

## Tests

### Test 1 (unit, marker_utils): extractor возвращает корректные ranges
```python
def test_extract_marker_blocks_two_blocks():
    text = "...\n<!-- DLD-CALLBACK-MARKER-START v1 -->\n**Status:** done\n<!-- DLD-CALLBACK-MARKER-END -->\n\n<!-- DLD-CALLBACK-MARKER-START v1 -->\n- file.py\n<!-- DLD-CALLBACK-MARKER-END -->\n"
    blocks = extract_marker_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].body == "**Status:** done"
    assert blocks[1].body == "- file.py"
```

### Test 2 (unit, marker_utils): merge заменяет блоки целиком
```python
def test_merge_replaces_block_bodies():
    head = "...<!-- DLD-CALLBACK-MARKER-START v1 -->\n**Status:** done\n<!-- DLD-CALLBACK-MARKER-END -->..."
    wt = head.replace("done", "queued")
    merged = merge_callback_markers(head, wt)
    assert "**Status:** done" in merged
    assert "**Status:** queued" not in merged
```

### Test 3 (unit, marker_utils): counts mismatch → degrade-open
```python
def test_merge_mismatched_counts_returns_wt_unchanged():
    head = "no markers"
    wt = "<!-- DLD-CALLBACK-MARKER-START v1 -->\n**Status:** queued\n<!-- DLD-CALLBACK-MARKER-END -->"
    assert merge_callback_markers(head, wt) == wt
```

### Test 4 (integration, orchestrator): autostash pop drift restored
```python
def test_git_pull_restores_callback_marker_after_pop(tmp_git_repo):
    # 1. Initial commit: spec.md со Status: queued
    # 2. Создать stash с локальным Status: queued
    # 3. Сделать "remote" коммит со Status: done и git fetch
    # 4. Вызвать git_pull
    # 5. Проверить: working tree содержит Status: done (восстановлено из HEAD)
    # 6. Проверить: log.warning AUTOSTASH_CALLBACK_RESTORE написан
```

### Test 5 (regression, orchestrator): отсутствие markers — no-op
```python
def test_git_pull_skips_files_without_markers(tmp_git_repo):
    # Файл без DLD-CALLBACK-MARKER не трогается даже если есть diff vs HEAD.
```

## Definition of Done

- [ ] Root cause устранён: pop больше не может вернуть stale Status поверх HEAD.
- [ ] Все 5 тестов проходят (`./test fast`).
- [ ] Regression: на dev-репо с двумя коммитами (queued → done в remote + stash queued локально) `git_pull` оставляет Status=done.
- [ ] `dependencies.md` обновлён.
- [ ] Аудит-лог: при сработке восстановления — `log.warning("AUTOSTASH_CALLBACK_RESTORE: ...")` с rel_path.
- [ ] Нет регрессий в `scripts/vps/tests/test_orchestrator.py`.
- [ ] Inbox-заметка `ai/inbox/20260515-autostash-status-overwrite.md` помечена done и перемещена в `ai/inbox/done/`.
