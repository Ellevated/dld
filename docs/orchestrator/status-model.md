# Status Model — Lifecycle SoT & Callback Contract

> Это «сердце» оркестратора. Здесь живут все правила, нарушение которых = **сломанный статус**.
> Модель действует с 16.05 (ARCH-186 / ADR-023). **Старую markdown-editing модель (ADR-018)
> считать снесённой.**

---

## 1. Где живёт статус (SoT)

**Истина статуса спеки — `ai/lifecycle/{spec_id}.yaml` в git-объектах HEAD.** Не markdown тела
спеки, не `ai/backlog.md`, не working tree.

- Все читатели читают **HEAD**, не WT: `lifecycle.read_lifecycle` → `git show HEAD:ai/lifecycle/{spec}.yaml`
  (`lifecycle.py::create_initial`); `list_by_status` → `git ls-tree HEAD:ai/lifecycle` (`lifecycle.py::list_by_status`).
- Markdown — **read-only render**: `ai/backlog.md` синхронизируется только по ячейке `Status`
  (см. §6); тело спеки `**Status:**` никем не пишется автоматически.
- **Следствие:** ручная правка `ai/lifecycle/*.yaml` в рабочем дереве **невидима** оркестратору
  (он читает HEAD). Чинить статус руками — только через `spec_operator.py` (см. [runbook.md](runbook.md)).

`LIFECYCLE_DIR = "ai/lifecycle"` (`lifecycle_const.py::LIFECYCLE_DIR`).

---

## 2. Как пишется статус (атомарный CAS git-plumbing)

`write_lifecycle(repo_dir, spec_id, status, *, reason=None, by="callback", pueue_id=None, allowed_files_hash=None)`
— `lifecycle.py::write_lifecycle`. **Никогда не трогает working tree** — пишет прямо в git-объекты и двигает ref.

Один CAS-attempt (`lifecycle_cas.py::_atomic_write`):

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
дефолтном `.git/index` staged-удаление (porcelain-статус `D` в index-колонке), что ломало
`assert_clean_lifecycle_tree` при рестарте.
`checkout HEAD --` атомарно обновляет И index, И WT. Best-effort: fail → WARNING, backstop —
`assert_clean_lifecycle_tree`.

---

## 3. Кто может писать (identity gate)

```python
_ALLOWED_WRITERS              = {callback, orchestrator, operator, qa, audit, migration}   # lifecycle_const.py
_ALLOWED_WRITERS_FOR_CREATE  = {spark} | _ALLOWED_WRITERS                                  # lifecycle_const.py
```

- `write_lifecycle` гейтит `by`: вне `_ALLOWED_WRITERS` → `ValueError` (`:576`).
- **`autopilot` и `spark` — НЕ writers** (ADR-025). autopilot сигналит статус через JSON
  `task_status` (callback его исполняет); spark клеймит ID, но статус не мутирует.
- **`orchestrator` пишет статус в трёх местах:** `reconcile_orphans` (демоут `in_progress` без живого
  pueue_id), **reconciliation gate** в `scan_queued` (если queued-спека уже реализована на
  origin/develop → `done`, `reason=already_implemented_on_develop:<sha>`, без сессии), и **диспатч**
  в `scan_queued` — после успешного `pueue add` пишет `in_progress` с `pueue_id` (BUG-218). Отказ этой
  записи логируется и НЕ отменяет диспатч: задача уже в очереди pueue. Это единственная запись
  `in_progress` во всей системе — она включает `started_at` (`lifecycle.py::write_lifecycle`) и делает
  `reconcile_orphans` работоспособным. Все три — легитимны, `orchestrator ∈ _ALLOWED_WRITERS`.
  Reconciliation использует ту же `gate_logic`-проверку, что guard.
- `spark` может **только `create_initial`** (claim ID через CAS), не `write_lifecycle` —
  Rule 7 (§4) всё равно держит.

### create_initial — spec-first ID claim (ADR-027)

`create_initial(repo_dir, spec_id, priority, kind, status="queued", *, by="orchestrator")` —
`lifecycle.py::create_initial`. Spark клеймит ID, пытаясь создать yaml через тот же CAS (Kafka-паттерн): две
машины зовут одновременно → CAS-проигравший получает `LifecycleWriteRaceError`, spark ретраит
(до 5 раз, retry на стороне spark). Priority нормализуется к lower-case, невалид → `p1` (TECH-200,
`:626-634`).

**`by="spark"` → только `status="queued"`** (2026-07-02): council/architect-решения происходят в
Spark Phase 4 ДО существования спеки, поэтому spark-born `blocked` («council_required»
pre-implementation gate) — процессная ошибка; `create_initial` бросает `ValueError`. Инцидент:
dowry FTR-1333 — spark написал спеку и заблокировал её «до /council» вместо созыва консилиума
внутри Phase 4. `status`-override (например `done` для DONE-архива при бутстрапе, ADR-026)
остаётся доступен только `by="orchestrator"`.

---

## 4. Write-once-done (Rule 7) — терминальность `done`

`done` — **терминальный** статус. Любая попытка `done → !done` бросает `LifecycleAlreadyDoneError`
(`lifecycle_const.py::_ALLOWED_WRITERS`). Проверка **структурно в примитиве** (`lifecycle.py::write_lifecycle` и
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

`_push_best_effort(repo_dir, branch)` — `lifecycle_push.py::_push_best_effort`. После успешного CAS пушит статус-коммит.

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
`callback_sync.py::verify_status_sync`. **Не редактирует markdown.** Решение — чистая функция от (origin/develop после
fetch, allowed_files, существующий lifecycle); pueue exit-code и activity-окна НЕ влияют. Запись —
только через `lifecycle.write_lifecycle(by="callback")`.

`task_status` перебивает pueue Success: `blocked`/`needs_review` → `target="blocked"`; `""`/`"complete"`
→ `target="done"` (`:1509-1519`). При гонке Rule 7 (`LifecycleAlreadyDoneError`) — noop `rule_7_saved` +
notify «investigate who wrote done» (`:1290-1320`).

### <a name="guard"></a>Implementation guard (`gate_ancestry.find_implementation`)

**Текущий гейт (Rule 1, TECH-220):** `done` ⟺ ветка `<type>/<ID>` — предок `origin/develop`
И принесла ≥1 не-bookkeeping allowed-файл. Одна функция, `gate_ancestry.find_implementation`,
во всех четырёх точках вызова: `callback_sync._decide_status`, `callback_dispatch._merge_confirmed`,
`orchestrator_queue.reconcile_if_implemented`, `gate-daemon._evaluate_project`. **Нет
activity-окна, нет `--all`, нет auto-close.** Fail-closed: любая ошибка git → `None` → `blocked`,
никогда не `done`.

> ⚠️ Это **редизайн поверх TECH-170 (`--all`) / TECH-176 (auto-close)** — те механики жили в старом
> `_spec_has_merged_implementation` и в текущем коде **заменены** сначала origin/develop subject-gate
> (2026-05-21), затем ancestry-gate (TECH-220, 2026-08-30). ADR-таблица в `.claude/rules/architecture.md`
> ещё описывает TECH-170/176 как актуальные — это дрейф, верь коду.

- **Ступень 1 — ancestry (primary, `gate_ancestry.find_merged_branch`).**
  `git merge-base --is-ancestor refs/remotes/origin/<type>/<ID> origin/develop`. Мержит в develop
  только автопилот, только из ветки `<type>/<ID>`, только `--ff-only` после зелёного прогона
  (`.claude/skills/autopilot/finishing.md:51-61`) — значит предок = протокол завершения прошёл.
  Карта префиксов (`gate_ancestry._BRANCH_PREFIX` — единственная машинная копия): FTR→`feature/`,
  BUG→`fix/`, TECH→`tech/`, ARCH→`arch/`, GROWTH→`growth/`. Две прозаические копии живут в
  `.claude/skills/autopilot/worktree-setup.md` и `autopilot-git.md` и между собой расходятся
  (ни одна не знает GROWTH, bash-копия падает в `task/`) — свести их отдельной TECH. Имя ref
  точное, без glob: `ARCH-176` никогда не матчит `ARCH-176a`.
- **Диапазон и bookkeeping-фильтр (`gate_ancestry._base_for_diff`).** После `--ff-only` мержа
  `merge-base(ref, origin/develop) == ref` — обычного диффа не существует, поэтому нижняя граница
  диапазона в этом случае не merge-base, а birth-коммит спеки (первый коммит, добавивший
  `ai/features/<ID>-*.md`, `--diff-filter=A --reverse`); при no-ff мерже нижняя граница — обычный
  `merge-base`. Файлы, которые branch принесла в этом диапазоне, пересекаются с
  `gate_logic.strip_bookkeeping_paths(allowed)`; пусто → не evidence, значит branch, тронувшая
  только lifecycle/backlog-бухгалтерию, `done` не даёт.
- **Ступень 2 — subject (`gate_logic.match_subject` / `find_implementation_commit`,
  DEPRECATED).** Старый гейт без изменений, второй проход после ancestry: засчитывает ТОЛЬКО
  первую строку (subject) коммита на `origin/develop`, не body/footer. Формы: Conventional scope
  `feat(FTR-925):` (case-insensitive, multi-scope, `!`); merge `merge[:] [branch]
  ['][prefix/]SPEC-ID` (покрывает `merge: feature/SPEC-ID — ...` и git-дефолтный `Merge branch
  'fix/SPEC-ID-slug'`); trailing `(SPEC-ID)` в конце subject (каждый элемент в скобках обязан быть
  spec-id-shaped — `(see SPEC-ID)` отвергается); legacy-префикс `SPEC-ID:` с пробелом. Два прохода
  `git log` (обычный path-filtered + `--first-parent`, TREESAME-фикс plpilot BUG-338). Покрывает
  squash-мерж и ветку, удалённую с origin — оба случая, где ancestry-проверке ref смотреть не на
  что. Отдельная TECH удалит эту ступень + regex, когда наступит день ниже.
- **Метрика и дата смерти.** Каждый вердикт (все четыре точки вызова) пишет `gate_via` = `ancestry`
  | `subject` | `none` — в `callback-audit.jsonl` (`_Audit.gate_via`, default `"none"`, поле есть в
  КАЖДОЙ строке через `_Audit.emit`, даже когда self-block переопределяет позитивный вердикт) и в
  shadow-JSONL `gate-daemon.py`. Когда `gate_via=subject` не срабатывает 30 дней подряд —
  `match_subject`/`find_implementation_commit` и вся ступень 2 удаляются отдельной TECH.
- **`_parse_allowed_files`** (`:529-565`, TECH-167): v1 strict (маркер
  `<!-- callback-allowlist v1 -->` + heading `## Allowed Files`, только канон-буллеты
  `` - `path.ext` ``) → list (может быть `[]`);
  иначе legacy (heading-варианты + любые backtick-пути); секции нет → `None`.
- **degrade-closed → blocked:** нет секции → reason `missing_allowed_files`; пустой allowlist (`[]`)
  → `empty_allowed_files` (`:1192-1196`). Никогда не `done` без позитивного совпадения (ancestry
  ИЛИ subject).
- **`branch_pushed_not_merged:<N>` (TECH-221) — не путать с `no_merged_implementation`.** После
  grace-retry, если ни ancestry, ни subject не нашли мёрж, `_decide_status` дополнительно читает
  `gate_ancestry.branch_state(project_path, spec_id)` (read-only, без fetch — Rule 4 уже
  зафетчила выше). `state.exists ∧ state.ahead > 0` → сессия умерла ДО мержа, но ПОСЛЕ того, как
  salvage успел запушить `origin/<type>/<ID>` (обычно таймаут) — работа жива, ничего не потеряно.
  Reason: `branch_pushed_not_merged:{ahead} ahead — origin/{ref} carries the work; re-dispatch
  continues that branch`. **Force-done здесь — неверный совет** (в отличие от plain
  `no_merged_implementation`): правильное действие — обычный `demote` в `queued`. Следующий
  диспатч проходит через `orchestrator_queue.reconcile()`, который читает тот же `branch_state()`
  и возвращает `"continue"` вместо `"fresh"`; `reconcile_if_implemented` (facade) выставляет
  `CLAUDE_CONTINUE_BRANCH=1` в `os.environ` для этого диспатча (сигнал/телеметрия на будущее —
  не gate). Независимо от флага, оба дерева autopilot-промптов (`worktree-setup.md` /
  `autopilot-git.md`) сами проверяют `git ls-remote --heads origin <type>/<ID>` при PHASE 0
  (worktree setup) и, если ветка на origin существует, строят worktree ИЗ неё (`-b <branch>
  origin/<branch>`, rebase на develop, `push --force-with-lease` re-sync) вместо чистого
  `develop` — сессия продолжает уже сделанные коммиты, не начинает заново. См.
  [runbook.md](runbook.md), Сценарий 4.
- **Self-block outranks any positive verdict.** Если автопилот сам сигналил `blocked`/`needs_review`
  (`autopilot_signaled=True`, `target="blocked"`), а гейт (любой ступенью) нашёл `done` —
  побеждает self-block: `callback_sync.verify_status_sync` перезаписывает вердикт в `blocked`,
  `reason="autopilot_signaled_blocked"`, `gate_via` из позитивного прохода сохраняется в audit-строке
  как трейс того, что гейт всё-таки нашёл. Автопилот видит то, чего гейт вывести не может (тесты
  красные, нужен human) — ancestry-мерж не отменяет это решение.

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
   вердикте `gate_ancestry.find_implementation` на origin/develop: ancestry (branch `<type>/<ID>`
   — предок develop и принесла allowed-файл, primary) либо subject (deprecated fallback, реализует
   spec ∧ трогает allowed-файл). См. §7 [Implementation guard](#guard).
7. **Push-divergence self-heal без потери чужой работы.** Non-ff rebase ТОЛЬКО если ahead-коммиты —
   lifecycle/backlog-only и WT чист; иначе bail + инкремент `.lifecycle-push-failures`.
8. **Mass-demote circuit-breaker.** >3 демоутов/10 мин → пауза `claude-runner`, отказ от мутаций статуса
   до reset.
