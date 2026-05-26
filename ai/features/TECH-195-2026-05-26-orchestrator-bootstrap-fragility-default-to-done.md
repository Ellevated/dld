# TECH-195 — Orchestrator bootstrap fragility: backlog format hard-coded + default-to-done fallback

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-26 | **Type:** TECH

> **Amends:** ARCH-186 (lifecycle SoT) · ARCH-193 (Rule 7) · TECH-194 (worktree+WT+callback layers).
> Closes a fourth class of lifecycle integrity failure left unaddressed by the chain above.

---

## Problem (one line)

`orchestrator.bootstrap_new_specs` парсит `ai/backlog.md` хрупким позиционным регексом и при любой неудаче парса **молча** ставит lifecycle status = `done`. Spec'и, формат строки которых отличается от template на одну колонку, попадают в HEAD как «historical artifact» и **никогда не диспатчатся**.

---

## Symptoms (живые кейсы 2026-05-26)

### S1 — TECH-1082 (awardybot, P2)

- spec.md создан operator'ом 26.05 утром
- backlog row: `| TECH-1082 | queued | tech | 2026-05-26 | [spec](...) |`
- `bootstrap_new_specs` regex не нашёл `queued` в **3-й** колонке (там `tech`) → `active_status.get(spec_id, "done")` → fallback
- HEAD yaml: `status=done`, `transitions=[]`, `pueue_id=null`, `finished_at=null`, `updated_by=orchestrator` (08:56 EEST)
- Pueue: **0 запусков**
- Operator увидел проблему → пересоздал yaml в WT вручную → ADR-025 hook бы заблокировал, но файл просто болтается как `?? ai/lifecycle/TECH-1082.yaml`

### S2 — BUG-1074 (awardybot, P1)

- sub-spec BUG-1070 group A (dowry-mc skip-graceful), создан Spark'ом 25.05 12:00 UTC
- backlog row такой же формы: `| BUG-1074 | queued | bug | 2026-05-25 | [spec] |`
- Та же история: bootstrap не подхватил, **0 запусков весь день**
- К утру 26.05 yaml был руками доведён до done через имитацию callback'а (видимо, оператор счёл что фикс не нужен) — но **сам факт того что Spark'ова спека никогда не запустилась** — это рабочая потеря

### S3 — масштаб

Awardybot и dowry **полностью** используют короткий формат `| ID | status | kind | date | spec |`. Template — длинный `| ID | description | status | priority | spec |`. **Все** новые специ в awardybot/dowry проходят через ту же воронку: либо счастливо bootstrap'нутся как `done` (если в backlog статус случайно совпал по позиции с regex), либо тихо умрут.

Quick scan по awardybot HEAD:
```bash
git -C /home/dld/projects/awardybot ls-tree --name-only HEAD ai/lifecycle/ \
  | while read f; do
      y=$(git show HEAD:$f)
      if echo "$y" | grep -q '^status: done' && echo "$y" | grep -q '^transitions: \[\]'; then
        echo "$f — bootstrap_as_done candidate"
      fi
    done
```
(точное число оставим Task 3 проверить программно — гипотеза «не единичный случай»)

---

## Root Cause Analysis

### Layer A — позиционный regex в `bootstrap_new_specs`

`scripts/vps/orchestrator.py:304-309`:
```python
active_re = re.compile(
    r"^\|\s*(?P<id>(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*)\s*\|"
    r"[^|]+\|\s*(?P<status>queued|in_progress|blocked|done|resumed|draft)\s*\|",
    re.MULTILINE,
)
```

Регекс ждёт `| ID | (anything) | status |` — status в **3-й** pipe-колонке. Это форма из `template/.claude/contexts/_template.md`:

```
| ID | description | status | priority | spec |
```

Но `awardybot/ai/backlog.md`, `dowry/ai/backlog.md` (и видимо ещё `dld/ai/backlog.md`) используют другую:

```
| ID | status | kind | date | spec |
```

Здесь status в **2-й** колонке. Regex не match'ится. **Никакой ошибки нет** — просто `active_status[spec_id]` пустой.

### Layer B — `default-to-done` в bootstrap

`scripts/vps/orchestrator.py:330`:
```python
status = active_status.get(spec_id, "done")
```

И комментарий выше (328-329):
```python
# Determine bootstrap status:
#   - parseable active row → use its status (typically 'queued' for new Spark)
#   - in backlog but archive/malformed → 'done' (historical, never dispatch)
status = active_status.get(spec_id, "done")
```

Логика «если строка в backlog malformed → значит спека archive» — **смертельно опасное** допущение. Malformed строка от reformat'а backlog'а ≠ archived спека. Default должен быть `queued` (безопасный fail-into-queue, оператор сразу увидит лишний диспатч) или **отказ создавать yaml** с anomaly counter + log warning.

### Layer C — markdown Status и yaml Status разъезжаются молча

Поскольку Layer A+B порождают `yaml=done` без транзиций, а spec.md обычно имеет в шапке `**Status:** queued`, markdown и yaml расходятся **с момента bootstrap'а**. Никто это не детектит. После ADR-023 markdown — read-only render, но render_backlog не использует spec.md frontmatter, поэтому drift не виден до тех пор, пока оператор не откроет spec.md глазами.

### Layer D — нет инструмента увидеть это

Сегодня выявление таких случаев требует:
- руками открыть spec.md и yaml,
- сравнить статусы,
- проверить pueue history,
- проверить transitions.

Multi-project детектор drift'а отсутствует.

---

## Связь с предыдущими спеками

| Уровень | Спека | Что чинит | Этот баг |
|---|---|---|---|
| Rule 7 (write-once-done) | ARCH-193 | Demote из `done` запрещён structurally | Не помогает — это **создание** в `done` |
| Worktree hook / WT sync / callback parser | TECH-194 | Layer C/D/E | Не покрывает bootstrap fallback |
| Lifecycle SoT | ARCH-186 / ADR-023 | yaml = SSOT | Bug в **процессе создания** SSOT |
| **Bootstrap fragility** | **TECH-195** (this) | Layer A/B/C/D | **THIS** |

---

## Tasks

### Task 1 — Backlog parser refactor + safe default (Layer A + B)

**File:** `scripts/vps/orchestrator.py` (bootstrap_new_specs + `_parse_priority_kind` если нужно)

**Изменения:**

1. Заменить позиционный regex на **column-aware** парсер:
   - Распознать header row (line с `---|---|`) → построить mapping `{column_name → column_index}` через ASCII `|`-split
   - Использовать mapping для извлечения `status` колонки по имени (case-insensitive: `status`, `Status`, `STATUS`)
   - Если header не найден или колонки `status` нет → fallback: попробовать все колонки 1..N через valid-values словарь `{queued, in_progress, blocked, done, resumed, draft, stale}` (один из них = status)
   - Если ни одна колонка не валидна → `status = None` (не «done»)

2. **Заменить fallback `"done"` на `"queued"`**:
   ```python
   status = active_status.get(spec_id)
   if status is None:
       log.warning(
           "BOOTSTRAP: backlog status unparsable for %s in %s — "
           "defaulting to 'queued' (operator: verify backlog format)",
           spec_id, project_dir,
       )
       status = "queued"
   ```

3. Инкремент `.bootstrap-unparsable-count` (новый counter рядом с `.bootstrap-anomaly-count`) при каждом fallback'е — для алёртинга.

**Rationale fail-into-queue:**
- `queued` — безопасный default. Спека войдёт в обычный поток, autopilot её увидит, оператор поймёт что что-то не так из-за лишнего диспатча или warning'а в логах.
- `done` — терминальное состояние (ADR-025 Rule 7), спека потеряна без шанса восстановления автоматикой.

### Task 2 — Recovery script для уже-pojakanных specs

**File:** `scripts/vps/recover_bootstrap_as_done.py` (NEW)

**Что делает:**
- Сканирует все проекты из `projects.json`
- Для каждого: ищет в HEAD yaml где `status=done` + `transitions=[]` + `pueue_id=null` + `finished_at=null` (классический bootstrap-as-done)
- Для каждой найденной спеки: вызывает `spec_operator.py demote --by=operator --to=queued <project> <spec_id>` (демотация уже разрешена ADR-025 для `by=operator`)
- Опциональный `--dry-run` — только показывает список без операций
- Печатает summary: per-project counts + total

**Безопасность:**
- НЕ трогает спеки с непустыми transitions (это легитимные dones)
- НЕ трогает спеки с `pueue_id != null` (запускались)
- Требует `--confirm` для реального запуска (default: dry-run)

### Task 3 — `lifecycle_audit.py` multi-project drift детектор

**File:** `scripts/vps/lifecycle_audit.py` (NEW), READ-ONLY

**Категории детекции:**
- `orphan_spec_md` (md есть, yaml в HEAD нет)
- `orphan_yaml` (yaml есть, md нет)
- `missing_from_backlog` (yaml есть, в backlog нет строки)
- `bootstrap_as_done` (yaml=done без transitions/pueue_id/finished_at)
- `markdown_status_mismatch` (md `**Status:**` != yaml status)
- `backlog_status_mismatch` (backlog status != yaml status)
- `backlog_format_unparsed` (строка есть, но парсер не распознал status)
- `wt_lifecycle_dirty` (uncommitted в `ai/lifecycle/`)
- `wt_features_dirty` (uncommitted в `ai/features/`)
- `unauthorized_writer` (transitions содержат `by=spark|autopilot` — нарушение ADR-025)
- `git_divergence` (local develop ahead/behind origin/develop)
- `push_failures_counter` (`.lifecycle-push-failures` > 0)
- `bootstrap_anomaly` (`.bootstrap-anomaly-count` > 0)
- `bootstrap_unparsable` (`.bootstrap-unparsable-count` > 0 — новый из Task 1)

**CLI:**
- `python3 scripts/vps/lifecycle_audit.py` — table on all projects
- `--project=<id>` — single project
- `--json` — machine-readable
- `--category=<cat>` — фильтр detail'а
- `--quiet` — только counts
- exit code: 0 if clean, 1 if findings

**Использование в DoD:**
- После Task 1+2: `lifecycle_audit.py --category=bootstrap_as_done` → 0 findings в awardybot/dowry
- После Task 1: `lifecycle_audit.py --category=backlog_format_unparsed` → 0 findings (regex теперь parses both formats)

### Task 4 — Tests

**File:** `tests/test_orchestrator_bootstrap.py` (NEW или extend существующий)

**Unit (Task 1):**
- `test_parse_backlog_template_format` — `| ID | desc | status | priority | spec |` → status=`queued`
- `test_parse_backlog_short_format` — `| ID | status | kind | date | spec |` → status=`queued`
- `test_parse_backlog_no_header` — табличка без `---|---|` → fallback на valid-values match
- `test_parse_backlog_unparsable` — мусорная строка → `status=None`
- `test_bootstrap_default_queued_not_done` — unparsable row → yaml пишется со status=queued, counter инкрементнут, warning логирован

**Integration (real-git, tmp_path):**
- `test_bootstrap_short_format_awardybot_style` — реальный repo с awardybot-style backlog → bootstrap создаёт yaml status=queued
- `test_recovery_script_dry_run` — поднимает фейковую "историческую" bootstrap-as-done спеку → recovery script её детектит
- `test_recovery_script_demotes_with_confirm` — после `--confirm` lifecycle yaml становится queued

**Regression:**
- `test_bootstrap_does_not_change_already_existing_yaml` — если yaml уже есть в HEAD, bootstrap не трогает (`continue` на line 324 после refactor)

### Task 5 — ADR-026 + docs

**Files:**
- `.claude/rules/architecture.md` — добавить ADR-026 row
- `.claude/rules/dependencies.md` — добавить новые модули (`lifecycle_audit.py`, `recover_bootstrap_as_done.py`)
- `template/.claude/rules/architecture.md` — sync ADR-026 (если применимо, т.к. orchestrator — DLD-only)

**ADR-026 формулировка:**
> **Bootstrap parser safety contract.**
> orchestrator.bootstrap_new_specs (1) использует column-aware backlog parser, (2) при невозможности извлечь status fail'ится в `queued` (не `done`), (3) логирует WARNING + инкрементит `.bootstrap-unparsable-count`. Терминальные состояния (`done`, `blocked`) создаются ТОЛЬКО через callback/operator, никогда — bootstrap fallback'ом. Closes lifecycle integrity gap left by ARCH-186/193 + TECH-194.

---

## Allowed Files

<!-- callback-allowlist v1 -->
- `scripts/vps/orchestrator.py`
- `scripts/vps/lifecycle.py`
- `scripts/vps/lifecycle_audit.py`
- `scripts/vps/recover_bootstrap_as_done.py`
- `scripts/vps/tests/test_orchestrator_bootstrap.py`
- `.claude/rules/architecture.md`
- `.claude/rules/dependencies.md`

---

## Eval Criteria

### Deterministic

| ID | Check | Pass if |
|---|---|---|
| D1 | После Task 1: `python3 -c "from scripts.vps.orchestrator import _parse_backlog; ..."` на awardybot-format строке | возвращает `status='queued'`, не None |
| D2 | После Task 1: unit тест `test_bootstrap_default_queued_not_done` | yaml пишется с `status=queued`, не `done` |
| D3 | После Task 1: `.bootstrap-unparsable-count` инкрементируется при unparsable row | `int(read) == prev+1` |
| D4 | После Task 2 `--dry-run`: на awardybot находит ≥1 candidate (TECH-1082 или похожие) | non-empty output |
| D5 | После Task 3: `lifecycle_audit.py --category=bootstrap_as_done --json` | возвращает валидный JSON; exit 0 если 0 findings, 1 иначе |

### Integration

| ID | Check | Pass if |
|---|---|---|
| I1 | Real-git тест с awardybot-style backlog + новый spec.md | После bootstrap: yaml в HEAD со `status=queued`, не done |
| I2 | После Task 2 `--confirm` на тестовом repo с bootstrap-as-done specs | yaml status переходит в `queued`, lifecycle.write_lifecycle вызывается с by=operator |
| I3 | После Task 1+2+3: `lifecycle_audit.py --quiet` на awardybot | `bootstrap_as_done=0` |

### Regression

| ID | Check | Pass if |
|---|---|---|
| R1 | TECH-194 цикл (autopilot → callback → done) на тестовой спеке | yaml status=done с непустыми transitions (новый код не ломает существующий flow) |
| R2 | Spark с template-format backlog | bootstrap создаёт yaml=queued (как раньше) |
| R3 | bootstrap НЕ перезаписывает уже существующий yaml | `read_lifecycle != None → continue` сохранён |

---

## DoD

- [ ] Task 1 mergED: column-aware parser, safe default=queued, warning+counter
- [ ] Task 2 mergED: recovery script доступен, `--dry-run` работает, требует `--confirm` для реального запуска
- [ ] Task 3 mergED: `lifecycle_audit.py` работает на всех 10 проектах из projects.json, exit code корректный
- [ ] Task 4 mergED: все тесты в `tests/test_orchestrator_bootstrap.py` green, в CI pytest -k bootstrap проходит
- [ ] Task 5 mergED: ADR-026 в architecture.md (root + template если sync), dependencies.md обновлён
- [ ] **Post-merge validation на VPS:**
  - `python3 scripts/vps/lifecycle_audit.py --category=bootstrap_as_done` → 0 в awardybot после recovery
  - `python3 scripts/vps/lifecycle_audit.py --category=backlog_format_unparsed` → 0 во всех проектах
  - Heartbeat жив, оркестратор не паникует
- [ ] TECH-1082 и BUG-1074 разморожены, в lifecycle yaml `status=queued`, orchestrator подхватывает на следующем scan_queued
- [ ] CHANGELOG.md обновлён через `/release` post-merge

---

## Notes for autopilot

- **Не запускай recovery script на проде из спеки** — это Task 2 deliverable, оператор сам решит когда запустить
- **Не используй `git add ai/lifecycle/`** — ADR-025 hook заблокирует. Только spec_operator или lifecycle.write_lifecycle
- Если backlog parser refactor оказывается > 80 LOC — разбей на helper в новом `scripts/vps/backlog_parser.py` (но добавь в Allowed Files и dependencies.md)
- Counter `.bootstrap-unparsable-count` — отдельный от `.bootstrap-anomaly-count` (последний про burst-creation, новый про parser fail)
