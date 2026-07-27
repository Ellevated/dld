# DLD Orchestrator — Runbook

> Операционные сценарии под **текущую lifecycle-SoT модель** (ADR-023+). Каждый: симптом →
> диагностика → fix → verify.
>
> 🚫 **ГЛАВНОЕ ПРАВИЛО.** Статус живёт в `ai/lifecycle/*.yaml` (git HEAD), не в markdown. **НИКОГДА**
> не «чини статус» правкой `**Status:**` в спеке или ячейки в `ai/backlog.md` и `git add`'ом — это
> ничего не меняет (читается HEAD-yaml) и блокируется pre-commit хуком (`git add ai/lifecycle` запрещён
> без `LIFECYCLE_WRITE_AUTHORIZED=1`). Единственный путь правки статуса руками — `spec_operator.py`.
> (Старый runbook советовал именно markdown-правку — он снесён.)

---

## Проверка перед запуском (pre-launch checklist)

```bash
cd /home/dld/projects/dld

# 1. Чистое ai/lifecycle/ во ВСЕХ проектах (иначе startup abort)
python3 scripts/vps/lifecycle_audit.py --category=wt_lifecycle_dirty
#   findings → cleanup-lifecycle-drift.sh (см. ниже)

# 2. Общий дрейф (14 категорий) — что разъехалось пока демон стоял
python3 scripts/vps/lifecycle_audit.py            # rc=0 чисто, rc=1 есть findings

# 3. Транспорт алертов жив? (event_writer → Hermes; см. components.md — silent-fail blind spot)
which hermes || ls ~/.local/bin/hermes            # нет бинаря → алерты молча не дойдут

# 4. Circuit-breaker не залип в OPEN с прошлого раза
pueue status --group claude-runner                # "paused" = circuit OPEN, сбросить:
#   python3 scripts/vps/callback.py --reset-circuit   (DB_PATH=prod!)

# 5. Нет осиротевших слотов / зависших pueue-задач
pueue status

# 6. Старт
systemctl --user start dld-orchestrator.service
journalctl --user -u dld-orchestrator.service -f
```

> Локальные прогоны callback/orchestrator/audit для теста — **всегда `DB_PATH=/tmp/...`**, иначе
> тронешь prod-БД и можешь открыть circuit-breaker в проде.

---

## Drift-инструменты (operator toolkit)

| Инструмент | Когда | Что делает |
|-----------|-------|-----------|
| `lifecycle_audit.py` | регулярно / перед запуском | READ-ONLY детектор дрейфа, 14 категорий. `--json`, `--quiet` (CI), `--category=<name>`, `--project=<id>` |
| `cleanup-lifecycle-drift.sh` | dirty `ai/lifecycle/` | HEAD canonical: `restore --staged` + `checkout HEAD --`. Untracked НЕ трогает (убрать руками) |
| `recover_bootstrap_as_done.py` | спека `done` без работы | Демоут bootstrap-as-done в `queued` (4-criteria). Dry-run по умолчанию, `--confirm` для записи |
| `spec_operator.py` | ручная правка статуса | `demote` / `force-done` / `reset-circuit` — через plumbing, WT не трогает |
| `callback.py --reset-circuit` | circuit OPEN | `clear_decisions(30)` + `pueue start` |

**14 категорий `lifecycle_audit`:** `orphan_spec_md`, `orphan_yaml`, `missing_from_backlog`,
`bootstrap_as_done`, `markdown_status_mismatch`, `backlog_status_mismatch`, `backlog_format_unparsed`,
`wt_lifecycle_dirty`, `wt_features_dirty`, `unauthorized_writer`, `git_divergence`,
`push_failures_counter`, `bootstrap_anomaly`, `bootstrap_unparsable`.

---

## Сценарий 1: Несколько спек внезапно ушли в blocked (mass-demote)

**Симптом:** после деплоя callback несколько спек в разных проектах → `blocked`, хотя код написан.

**Диагностика:**
```bash
# Circuit-breaker сработал?
pueue status --group claude-runner        # paused = OPEN
sqlite3 scripts/vps/orchestrator.db \
  "SELECT spec_id,verdict,reason,ts FROM callback_decisions WHERE demoted=1 ORDER BY ts DESC LIMIT 20"
# Последний коммит в callback/guard
git log --oneline -10 -- scripts/vps/callback.py scripts/vps/lifecycle.py
```

**Fix:**
1. Если circuit OPEN — он защитил тебя от лавины. Сначала найди корень (regex/guard regression),
   только потом reset: `python3 scripts/vps/callback.py --reset-circuit`.
2. Регрессия guard → `git revert <commit>` в callback/lifecycle, redeploy.
3. Вернуть ложно-blocked в `queued` (НЕ правкой markdown):
   ```bash
   python3 scripts/vps/spec_operator.py demote /home/dld/projects/<proj> <SPEC_ID> \
     "false-positive callback demote" --by=operator
   ```
   `demote` ведёт в `queued` — оркестратор передиспатчит на следующем цикле.

---

## Сценарий 2: Спека застряла in_progress, pueue пуст

**Симптом:** lifecycle/backlog показывают `in_progress`, но задачи в pueue нет, новый цикл не подхватывает.

**Причина:** callback не сработал (crash pueue / рестарт демона) — слот не освобождён, статус не дописан.

**Диагностика:**
```bash
pueue status | grep <proj>
sqlite3 scripts/vps/orchestrator.db \
  "SELECT project_id,phase,current_task FROM project_state"
python3 scripts/vps/lifecycle_audit.py --project=<proj>   # покажет divergence/orphans
```

**Fix:** оркестратор лечит это сам на старте — `reconcile_orphans` демоутит `in_progress` без живого
pueue_id. Если демон работает и не лечит:
```bash
# освободить осиротевший слот
sqlite3 scripts/vps/orchestrator.db \
  "UPDATE compute_slots SET project_id=NULL,pueue_id=NULL,acquired_at=NULL WHERE project_id='<proj>'"
python3 scripts/vps/db.py update-phase <proj> idle
# вернуть спеку в очередь (через plumbing, не markdown)
python3 scripts/vps/spec_operator.py demote /home/dld/projects/<proj> <SPEC_ID> \
  "stuck in_progress, callback missed" --by=operator
```

---

## Сценарий 3: Guard не видит реализацию (спека blocked, а код есть)

**Симптом:** `blocked` с reason `missing_allowed_files` / `empty_allowed_files`, либо guard не нашёл
коммит, хотя реализация смёржена.

**Причина** (текущий guard `_is_done_on_develop` — origin/develop gate):
- Нет секции `## Allowed Files` (legacy spec) → `missing_allowed_files`.
- v1-маркер есть, буллетов нет → `empty_allowed_files` (degrade-closed).
- Коммит реализации не на `origin/develop` (застрял на feature-ветке, не смёржен).
- Subject коммита не объявляет spec_id (упоминание в body/footer не считается, TECH-177).

**Диагностика:**
```bash
sed -n '/^## Allowed Files/,/^## /p' ai/features/<SPEC_ID>*.md
git -C /home/dld/projects/<proj> log origin/develop --oneline | grep -i <SPEC_ID>
```

**Fix:** поправить секцию `## Allowed Files` (канон `` - `path.ext` `` под маркером
`<!-- callback-allowlist v1 -->`) и передиспатчить (`demote` → queued), ИЛИ, если верифицировал руками
что работа реально сделана:
```bash
python3 scripts/vps/spec_operator.py force-done /home/dld/projects/<proj> <SPEC_ID> \
  "manual verification passed" --by=operator
```
(см. [verification.md](verification.md) — верифицируй ПЕРЕД force-done.)

---

## Сценарий 4: Спека помечена done, но работа не сделана (bootstrap-as-done)

**Симптом:** `lifecycle_audit` показывает `bootstrap_as_done` — спека `done`, но без истории
(`transitions=[]`, `pueue_id=None`, `finished_at=None`). Никогда не выполнялась, и Rule 7 не даёт
оператору её демоутить обычным путём.

**Fix (narrow Rule 7 escape):**
```bash
# dry-run — посмотреть кандидатов
python3 scripts/vps/recover_bootstrap_as_done.py --project=<proj>
# применить
python3 scripts/vps/recover_bootstrap_as_done.py --project=<proj> --confirm
```
Демоутит ТОЛЬКО точную 4-criteria подпись (легитимный `done` с историей не тронет —
`NotBootstrapArtifactError`).

---

## Сценарий 5: Push-race — статус закоммичен локально, но вечно «queued» у читателей

**Симптом:** callback записал `done` локально, но push reject (non-ff), develop разошёлся с origin;
другие узлы (через `git pull`) видят старый статус. `lifecycle_audit` → `git_divergence` и/или
`push_failures_counter > 0` (`ai/.lifecycle-push-failures`).

**Причина/лечение:** `_push_best_effort` сам рибейзит lifecycle-only ahead-коммиты на origin
(`de4f434`). Если счётчик растёт — авто-rebase отказывает (ahead-коммиты не lifecycle-only, или WT
грязный). Проверь:
```bash
git -C /home/dld/projects/<proj> status
git -C /home/dld/projects/<proj> log origin/develop..develop --oneline    # что ahead
```
Разрулить расхождение вручную (rebase develop на origin/develop), убедившись, что не теряешь код-коммиты,
затем обнулить счётчик после push.

---

## Сценарий 6: Добавить новый проект

```bash
# 1. projects.json
#    {"project_id":"myproj","path":"/home/dld/projects/myproj","provider":"claude","auto_approve_timeout":30}
# 2. В проекте должен быть ai/backlog.md. Хуки — один установщик на весь флот:
bash scripts/vps/install-lifecycle-guard.sh          # или --verify, чтобы только посмотреть
# 3. Оркестратор auto-обнаружит при следующем цикле (mtime projects.json). Форсировать:
touch scripts/vps/.run-now-myproj
# 4. Verify
sqlite3 scripts/vps/orchestrator.db "SELECT * FROM project_state WHERE project_id='myproj'"
```

---

## Остановка

```bash
systemctl --user stop dld-orchestrator.service
# Идущие autopilot-сессии в pueue продолжатся до завершения (callback отработает).
# Чтобы не принимать новые задачи но дать текущим доработать — достаточно stop демона.
# Жёстко погасить раннеры: pueue pause --group claude-runner  (потом start)
```
