# Status Model — Lifecycle SoT & Callback Contract

> Это «сердце» оркестратора. Здесь живут все правила, нарушение которых = **сломанный статус**.
> Модель действует с 16.05 (ARCH-186 / ADR-023). **Старую markdown-editing модель (ADR-018)
> считать снесённой.**

---

## 1. Где живёт статус (SoT)

**Истина статуса спеки — `ai/lifecycle/{spec_id}.yaml` в git-объектах HEAD.** Не markdown тела
спеки, не `ai/backlog.md`, не working tree.

- Все читатели читают **HEAD**, не WT: `lifecycle.read_lifecycle` → `git show HEAD:ai/lifecycle/{spec}.yaml`
  (`lifecycle.py:155-162, 549-556`); `list_by_status` → `git ls-tree HEAD:ai/lifecycle` (`:660-694`).
- Markdown — **read-only render**: `ai/backlog.md` синхронизируется только по ячейке `Status`
  (см. §6); тело спеки `**Status:**` никем не пишется автоматически.
- **Следствие:** ручная правка `ai/lifecycle/*.yaml` в рабочем дереве **невидима** оркестратору
  (он читает HEAD). Чинить статус руками — только через `spec_operator.py` (см. [runbook.md](runbook.md)).

`LIFECYCLE_DIR = "ai/lifecycle"` (`lifecycle.py:46`).

---

## 2. Как пишется статус (атомарный CAS git-plumbing)

`write_lifecycle(repo_dir, spec_id, status, *, reason=None, by="callback", pueue_id=None, allowed_files_hash=None)`
— `lifecycle.py:559`. **Никогда не трогает working tree** — пишет прямо в git-объекты и двигает ref.

Один CAS-attempt (`_atomic_write`, `lifecycle.py:228-362`):

1. Приватный индекс: `tempfile` в `.git/` → `GIT_INDEX_FILE=idx_path` (`:232-236`) — изоляция от
   дефолтного `.git/index`.
2. **Pin HEAD один раз** (TOCTOU-фикс, `fd9455f`): `git rev-parse HEAD` → `head_sha`; tree-snapshot,
   parent коммита и CAS ссылаются на ОДИН `head_sha` (`:244-247`).
3. `git read-tree {head_sha}` (`:249`) → `hash-object -w --stdin` (yaml) → `blob_sha` (`:252-257`) →
   `update-index --add --cacheinfo 100644,{blob_sha},ai/lifecycle/{spec}.yaml` (`:260-274`).
4. (status-only backlog sync, §6) → `git write-tree` → `tree_sha` (`:313-316`).
5. `git commit-tree {tree_sha} -p {head_sha}` → `new_commit` (`:318-325`).
6. **CAS:** `git update-ref refs/heads/{branch} {new_commit} {head_sha}` — если HEAD сдвинулся
   между шагом 2 и сейчас, `update-ref` фейлится (returncode≠0) → attempt проваливается (`:327-330`).

`_cas_loop` (`:515-541`): in-process `threading.Lock` сериализует записи в процессе; `MAX_CAS_RETRIES=3`
с jitter 0–50мс; успех → `_push_best_effort` (§5); исчерпание → `LifecycleWriteRaceError`.
`subprocess.TimeoutExpired` (timeout=30) трактуется как CAS-fail.

**Почему так (TOCTOU-инвариант, `fd9455f`):** раньше HEAD читался дважды (`read-tree HEAD` … позже
`rev-parse HEAD`). Конкурентный push между ними → дерево снимало СТАРЫЙ HEAD, parent — НОВЫЙ; CAS
сторожит только `parent==branch` → коммитилось устаревшее дерево, **молча откатывая чужие коммиты**.
Pin-once закрывает окно.

**WT-sync постфактум (TECH-194 Layer D):** после CAS — `git checkout HEAD -- ai/lifecycle/{spec}.yaml`
(`:340-343`), не старый `checkout-index --force`. Старый вариант писал только WT-файл, но оставлял в
дефолтном `.git/index` staged-удаление (`D  `), что ломало `assert_clean_lifecycle_tree` при рестарте.
`checkout HEAD --` атомарно обновляет И index, И WT. Best-effort: fail → WARNING, backstop —
`assert_clean_lifecycle_tree`.

---

## 3. Кто может писать (identity gate)

```python
_ALLOWED_WRITERS              = {callback, orchestrator, operator, qa, audit, migration}   # lifecycle.py:59
_ALLOWED_WRITERS_FOR_CREATE  = {spark} | _ALLOWED_WRITERS                                  # lifecycle.py:66
```

- `write_lifecycle` гейтит `by`: вне `_ALLOWED_WRITERS` → `ValueError` (`:576`).
- **`autopilot` и `spark` — НЕ writers** (ADR-025). autopilot сигналит статус через JSON
  `task_status` (callback его исполняет); spark клеймит ID, но статус не мутирует.
- `spark` может **только `create_initial`** (claim ID через CAS), не `write_lifecycle` —
  Rule 7 (§4) всё равно держит.

### create_initial — spec-first ID claim (ADR-027)

`create_initial(repo_dir, spec_id, priority, kind, status="queued", *, by="orchestrator")` —
`lifecycle.py:603`. Spark клеймит ID, пытаясь создать yaml через тот же CAS (Kafka-паттерн): две
машины зовут одновременно → CAS-проигравший получает `LifecycleWriteRaceError`, spark ретраит
(до 5 раз, retry на стороне spark). Priority нормализуется к lower-case, невалид → `p1` (TECH-200,
`:626-634`).

---

## 4. Write-once-done (Rule 7) — терминальность `done`

`done` — **терминальный** статус. Любая попытка `done → !done` бросает `LifecycleAlreadyDoneError`
(`lifecycle.py:86-100`). Проверка **структурно в примитиве** (`write_lifecycle:581-584` и
`create_initial:638-642`) → защищает ВСЕХ writers (callback, operator, qa, audit, migration, spark-claim).

**Единственный escape — `recover_bootstrap_artifact`** (`:852-940`, TECH-195): демоутит
«bootstrap-as-done» в `queued`, обходя Rule 7 ТОЛЬКО при ВСЕХ 4 признаках одновременно:

```
status == "done"  ∧  transitions == []  ∧  pueue_id is None  ∧  finished_at is None
```

Иначе `NotBootstrapArtifactError` — легитимный `done` (с историей переходов) защищён. Это сигнатура
«спека создана сразу как done бутстрапом, никогда не выполнялась». См.
[runbook.md](runbook.md#восстановление-bootstrap-as-done).

**Оператор:** `spec_operator.py force-done` на уже-`done` спеку → **rc=5** («done is terminal»). Rule 7
держит даже оператора, кроме narrow escape выше.

---

## 5. Push-divergence self-heal (`_push_best_effort`)

`_push_best_effort(repo_dir, branch)` — `lifecycle.py:365-398`. После успешного CAS пушит статус-коммит.

**Failure mode (push-race divergence, чинено `de4f434`):** пока агент работает, оркестратор пропускает
`git pull`; callback коммитит статус на устаревший локальный `develop`; код-коммиты агента уже на
origin → push reject (non-ff) → ветки расходятся → `merge --ff-only` оркестратора не лечит → done-коммит
заперт, статус «вечно queued» (наблюдалось 9 ручных rebase/день на awardybot 21.06).

**Self-heal:** при non-ff reject — до 3 раундов `_rebase_onto_origin` + retry push. С двумя guard'ами:

- **`_local_ahead_is_lifecycle_only`** (`:418-447`): авто-rebase ТОЛЬКО если каждый ahead-коммит
  трогает исключительно `ai/lifecycle/` или `ai/backlog.md` (callback — их единственный writer →
  конфликт-free by construction). Иначе bail — **никогда не рибейзит код-коммиты**.
- WT clean (Guard 1) + lifecycle-only (Guard 2) перед самим rebase; конфликт → `rebase --abort`.

Исчерпание → инкремент `ai/.lifecycle-push-failures` (drift-сигнал для `lifecycle_audit`).

---

## 6. Status-only backlog.md sync (`5bddf16`)

`backlog.md` обновляется **в том же атомарном коммите**, что и yaml (`_atomic_write:283-311`), и только
по ячейке `Status` существующих строк (`render_backlog.sync_status`, регекс `_BACKLOG_ROW_RE`). Каждый
прочий байт (founder-описания, секции, маркеры) сохраняется.

**Отличие от снесённого:** старый full-table render отключён 16.05 (ломал структуру), re-enabled как
status-only. `backlog.md` — read-only render статуса, не SoT. Full `render_backlog()` оставлен только
как operator emergency.

---

## 7. Контракт callback

`callback.py` вызывается pueue по завершении любой задачи: `callback.py <pueue_id> <group> <result>`
(`:15`). **INVARIANT: всегда `exit 0`** (`finally: sys.exit(0)`, `:1534-1535`) — падение callback не
должно ломать pueue. Группа `night-reviewer` — ранний `sys.exit(0)` без обработки.

**7 шагов `main()`** (`:1387-1535`):

| Шаг | Действие |
|-----|----------|
| 1 | `release_slot(pueue_id)` — всегда |
| 2 | `finish_task` — обновить task_log |
| 3 | `update_project_phase` |
| 4 | `extract_agent_output` → skill / preview / `task_status` (регекс `"task_status"\s*:\s*"([a-z_]+)"` ловит токен в markdown-fence) |
| 5 | `event_writer.notify` → Hermes |
| 6 | dispatch QA + reflect — **только если `task_status == "complete"`** (TECH-194 Layer E, allowlist не blocklist) |
| 7 | `verify_status_sync` → запись статуса |

### verify_status_sync (текущий, ужат с 2026-05-21)

`verify_status_sync(project_path, spec_id, target="done", pueue_id=None, autopilot_signaled=False)` —
`callback.py:1067-1357`. **Не редактирует markdown.** Решение — чистая функция от (origin/develop после
fetch, allowed_files, существующий lifecycle); pueue exit-code и activity-окна НЕ влияют. Запись —
только через `lifecycle.write_lifecycle(by="callback")`.

`task_status` перебивает pueue Success: `blocked`/`needs_review` → `target="blocked"`; `""`/`"complete"`
→ `target="done"` (`:1509-1519`). При гонке Rule 7 (`LifecycleAlreadyDoneError`) — noop `rule_7_saved` +
notify «investigate who wrote done» (`:1290-1320`).

### <a name="guard"></a>Implementation guard (`_is_done_on_develop`)

**Текущий гейт (Rule 1, `:797-838`):** `done` ⟺ на `origin/develop` есть коммит, чей **subject**
реализует spec_id И трогает ≥1 allowed-файл. **Нет activity-окна, нет `--all`, нет auto-close.**
Fail-closed: ambiguity → `blocked`.

> ⚠️ Это **редизайн поверх TECH-170 (`--all`) / TECH-176 (auto-close)** — те механики жили в старом
> `_spec_has_merged_implementation` и в текущем коде **заменены** на origin/develop-gate. ADR-таблица в
> `.claude/rules/architecture.md` ещё описывает их как актуальные — это дрейф, верь коду.

- **`_subject_implements`** (`:734-774`, TECH-177): засчитывает ТОЛЬКО первую строку (subject), не
  body/footer. Формы: Conventional scope `feat(FTR-925):` (case-insensitive, multi-scope, `!`);
  merge `merge [branch/]SPEC-ID`; legacy `SPEC-ID: `.
- **`_parse_allowed_files`** (`:529-565`, TECH-167): v1 strict (маркер `<!-- callback-allowlist v1 -->`
  + heading `## Allowed Files`, только канон-буллеты `` - `path.ext` ``) → list (может быть `[]`);
  иначе legacy (heading-варианты + любые backtick-пути); секции нет → `None`.
- **degrade-closed → blocked:** нет секции → reason `missing_allowed_files`; пустой allowlist (`[]`)
  → `empty_allowed_files` (`:1192-1196`). Никогда не `done` без позитивного совпадения.

### Circuit-breaker (TECH-169)

Пороги: `CIRCUIT_THRESHOLD=3`, `CIRCUIT_WINDOW_MIN=10`, `CIRCUIT_HEAL_MIN=30` (`:844-852`). >3 демоутов
за 10 мин → OPEN: `db.record_decision("circuit_open")` + `notify_circuit_event("open")` +
`pueue pause --group claude-runner` (`:936-967`). Лечится сам если 0 демоутов за 30 мин, либо
`callback.py --reset-circuit` (= `db.clear_decisions(30)` + `pueue start` + notify). Пока OPEN —
verify_status_sync noop (не мутирует статус).

### TECH-197 hardening

- **push-local-before-gate:** при `target="blocked"` и не-signaled → `git push origin develop` (flush
  merge, прерванного таймаутом между merge и push) перед вердиктом.
- **grace-retry:** guard не нашёл impl и не signaled → до 3× `sleep(5)+fetch+recheck`, иначе blocked с
  operator-hint `spec_operator.py force-done`.
- **out-of-scope detection (BUG-199):** `_detect_out_of_scope_files` — detection-only WARNING в audit,
  не enforcement.

---

## 8. Operator escape — spec_operator.py

| Команда | Действие | rc |
|---------|----------|----|
| `demote <project> <SPEC> <reason> [--blocked] --by=` | → `queued` (или `blocked`) | 0 ok / 5 если уже done |
| `force-done <project> <SPEC> <reason> --by=` | → `done` (обходит guard) | 0 ok / **5 на уже-done (Rule 7)** |
| `reset-circuit` | сброс circuit-breaker | 0 |

`--by` choices = `{operator, qa, audit}` (`:138, 150`). **`autopilot`/`spark` removed** (ADR-025) —
argparse отвергнет. Прочие rc: 2 usage/invalid identity, 3 spec/yaml не найден, 4 CAS race exhausted.
Все мутации идут через `lifecycle.write_lifecycle` (plumbing, WT не трогается).

---

## <a name="инварианты-статуса"></a>9. Инварианты статуса (нарушение = сломанный статус)

1. **Single-writer.** Статус пишет только `callback` (нормальный поток) через
   `write_lifecycle(by="callback")`. `by` вне `_ALLOWED_WRITERS` → `ValueError`. `autopilot`/`spark`
   не writers.
2. **SoT = yaml @ HEAD.** Читатели читают HEAD, не WT. Markdown — render. Ручная правка WT-yaml невидима.
3. **Write-once-done (Rule 7).** `done → !done` запрещён всем (`LifecycleAlreadyDoneError`); escape —
   только 4-criteria `recover_bootstrap_artifact`. Operator force-done на done → rc=5.
4. **CAS-атомарность.** Приватный index + pin-HEAD-once + `update-ref <new> <head_sha>`. HEAD сдвинулся
   → attempt фейлится и ретраится. Никогда не коммитится дерево со старого HEAD (TOCTOU, `fd9455f`).
5. **WT не участвует в записи.** Запись в объекты+ref, WT синхронизируется постфактум
   `git checkout HEAD --`. `assert_clean_lifecycle_tree` валит старт при dirty `ai/lifecycle/`.
6. **Degrade-closed guard.** Нет/пустой allowlist → `blocked`. `done` — только при позитивном
   совпадении на origin/develop (subject реализует spec ∧ трогает allowed-файл).
7. **Push-divergence self-heal без потери чужой работы.** Non-ff rebase ТОЛЬКО если ahead-коммиты —
   lifecycle/backlog-only и WT чист; иначе bail + инкремент `.lifecycle-push-failures`.
8. **Mass-demote circuit-breaker.** >3 демоутов/10 мин → пауза `claude-runner`, отказ от мутаций статуса
   до reset.
