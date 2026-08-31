# Tech: [TECH-194] ARCH-193 follow-up — worktree hook gap + WT-sync env loss + callback exit-code parser

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-25

**Amends:** ARCH-193 (lifecycle write-once-done invariant)
**Related:** BUG-185 (was BUG-974, lifecycle WT drift), BUG-188 (claude-runner false-fail), ARCH-187 (identity enforcement + WT sync Layer 3)

---

## Why

ARCH-193 закрыл 2 из 4 необходимых слоёв защиты lifecycle write integrity. После 4 часов наблюдения за оркестратором (2026-05-25 20:21 → 22:30 EEST) обнаружены **три новых поверхностных слоя**, через которые система продолжает разрушать инвариант:

1. **awardybot:BUG-1075** — autopilot закоммитил `ai/lifecycle/BUG-1075.yaml` прямым `git commit` с `updated_by: autopilot` (нарушение ADR-025). Hook ARCH-193 должен был отвергнуть — НЕ отверг.
2. **dowry:BUG-450** — после Success завершения 5 lifecycle файлов в working tree: 1 staged (BUG-450 — диверг HEAD=done vs WT=queued), 2 modified (ARCH-448, BUG-449), **2 deleted** (TECH-446, TECH-447).
3. **awardybot после смены** — 2 lifecycle файла dirty без видимой причины.
4. **wb FTR-182.yaml утром 25.05** — тот же сценарий привёл к падению `assert_clean_lifecycle_tree` и downtime оркестратора 5.5 часов.

Все 4 кейса — одна семья: **WT diverges from HEAD после lifecycle.write_lifecycle**. Плюс **callback на blocked задачах диспатчит qa+reflect**, сжигая ~$2.50 на ложный round (BUG-1075 кейс).

Если не починить — каждый рестарт оркестратора будет fail на dirty WT, каждая blocked задача будет стоить +$2.50 в qa/reflect, а autopilot будет продолжать прямо коммитить lifecycle yaml в worktree, нарушая ADR-025 SoT.

---

## Symptoms (наблюдаемые)

### S1 — Autopilot direct lifecycle commit обходит ARCH-193 hook

**Кейс:** `awardybot:BUG-1075` (pueue 430, 21:04-21:26 EEST).

```
commit 7d2717a2 (HEAD -> fix/BUG-1075)
Author: Ellevated <ellevatedai@gmail.com>
Date:   Mon May 25 21:24:08 2026 +0300

    docs(BUG-1075): Task 0 diagnose — bug self-resolved, blocked for user approval

 ai/lifecycle/BUG-1075.yaml | 16 +++++++++++-----
 1 file changed, 11 insertions(+), 5 deletions(-)
```

Lifecycle yaml содержит `updated_by: autopilot` в transitions. Это **прямой git commit**, не atomic plumbing через `lifecycle.write_lifecycle`. ARCH-193 ADR-025 hook должен был отвергнуть (autopilot убран из `_ALLOWED_WRITERS`), но НЕ отверг.

### S2 — WT diverges from HEAD после lifecycle write

**Кейс:** `dowry:BUG-450` (pueue 431, 21:10-22:17 EEST), завершилась Success, 4 коммита merged.

```
$ git -C /home/dld/projects/dowry status --short ai/lifecycle/
M  ai/lifecycle/BUG-450.yaml         # STAGED divergence
 M ai/lifecycle/ARCH-448.yaml        # modified WT
 M ai/lifecycle/BUG-449.yaml
 D ai/lifecycle/TECH-446.yaml        # DELETED
 D ai/lifecycle/TECH-447.yaml        # DELETED

$ git show HEAD:ai/lifecycle/BUG-450.yaml | grep status
status: done                         # HEAD = done by callback

$ grep status ai/lifecycle/BUG-450.yaml
status: queued                       # WT = queued by spark (stale)
```

callback корректно записал `done` в HEAD через atomic plumbing. **WT не синхронизировался.** При следующем autopilot run в этом worktree `git add .` протолкнёт stale yaml.

### S3 — Lifecycle drift растёт со временем

```
20:21 EEST (старт оркестратора):  awardybot 0, dowry 0, wb 0 dirty
22:30 EEST (через 2 часа):        awardybot 2, dowry 5, wb 0 dirty
```

### S4 — Callback диспатчит qa+reflect на blocked задачах

**Кейс:** `awardybot:BUG-1075` — autopilot завершил с `task_status=blocked`, lifecycle = blocked. Callback **читает** `task_status` из agent_output (Step 4, строка 1335), но dispatch qa+reflect происходит в Step 6 **до** проверки `task_status` в Step 7:

```
21:26:31 INFO: parsed: project=awardybot task=BUG-1075 status=done
21:26:34 INFO: QA dispatched: awardybot:qa-BUG-1075 pueue_id=432
21:26:36 INFO: reflect dispatched: awardybot:reflect-BUG-1075 pueue_id=433
21:26:39 INFO: NOOP: BUG-1075 — already blocked     ← поздно, qa+reflect уже летят
```

Cost: qa = 31 turns / $2.11, reflect = 11 turns / $0.50 = **+$2.61 на каждую blocked**.

### S5 — wb FTR-182 утром (исторический пример того же бага)

2026-05-24 22:58 EEST — spec_operator демоутнул FTR-182 в worktree dowry (не в нашем кейсе, но похожий путь). Atomic plumbing записал в HEAD, WT остался в старом состоянии. 2026-05-25 13:44 EEST — orchestrator restart → `assert_clean_lifecycle_tree` FATAL → daemon downtime 5.5 часов.

```
RuntimeError: Dirty lifecycle tree in /home/dld/projects/wb:
  M ai/lifecycle/FTR-182.yaml
```

---

## Root Cause Analysis

### Layer C — Pre-commit hook не работает в worktrees (три под-бага)

`core.hooksPath` установлен относительным путём `.git-hooks` (через `setup-vps.sh --phase4-hooks`). Git резолвит относительный hooksPath **от `$PWD` git-команды**, не от gitdir. Autopilot всегда работает в worktree:

```
/home/dld/projects/awardybot/.worktrees/BUG-1075/  ← cwd autopilot
       ↓ git commit
git looks for: .worktrees/BUG-1075/.git-hooks/pre-commit
                                    ↑ НЕТ такого файла
       ↓
silently skipped → commit разрешён БЕЗ guard.mjs проверки
```

**Доказательство:**
```bash
$ git -C /home/dld/projects/awardybot worktree list
/home/dld/projects/awardybot                      [develop]
/home/dld/projects/awardybot/.worktrees/BUG-1075  [fix/BUG-1075]   ← autopilot работал здесь

$ git -C /home/dld/projects/awardybot config core.hooksPath
.git-hooks                                                          ← RELATIVE

$ ls /home/dld/projects/awardybot/.worktrees/BUG-1075/.git-hooks/
ls: cannot access ...: No such file or directory
```

ARCH-193 Task 5 (`setup-vps.sh --phase4-hooks idempotent installer`) ставил hook только в main repo, **не в worktrees**, и относительным путём — что не работает для worktrees.

#### C2 — pre-commit wrapper использует relative path к guard.mjs → fail-open

Даже после исправления hooksPath на absolute — `.git-hooks/pre-commit` проверяет:

```bash
if [[ -x ".claude/hooks/pre-commit-lifecycle-guard.mjs" ]] && command -v node >/dev/null 2>&1; then
```

CWD при выполнении хука = worktree root. Если ветка worktree не содержит `.claude/hooks/pre-commit-lifecycle-guard.mjs` → условие FALSE → **guard silently skipped → `exit 0` → commit ALLOWED**. Хук найден и запущен (абсолютный hooksPath работает), но lifecycle guard не выполнен. **Fail-open, не ошибка конфигурации.**

#### C3 — guard.mjs использует relative path к `event_writer.py` → audit bypass gap

guard.mjs при `LIFECYCLE_WRITE_AUTHORIZED=1` вызывает:

```js
execFileSync('python3', ['scripts/vps/event_writer.py', process.cwd(), ...])
```

`scripts/vps/event_writer.py` — относительный путь от CWD (worktree/project root). В awardybot/dowry/wb `scripts/vps/event_writer.py` отсутствует → `catch {}` → **audit event тихо теряется**. Bypass работает корректно (exit 0), но не логируется. Подтверждено в прямом тесте: bypass сработал, event_writer.py не найден, best-effort silent fail.

### Layer D — `_atomic_write` теряет `env` при `checkout-index`

`scripts/vps/lifecycle.py:266-275`:

```python
# Layer 3 (ARCH-187 / ADR-024): sync WT to new HEAD blob...
sync_result = _run(
    ["git", "checkout-index", "--force", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
    cwd=repo_dir,
    # ← env=env ОТСУТСТВУЕТ
)
```

Без `env={GIT_INDEX_FILE: idx_path}` `checkout-index` читает **default `.git/index`** (stale snapshot до atomic write), а не приватный `idx_path` с новым blob. Если default index не содержит файла или содержит старую версию:
- **Файла нет в default index** → `error: git checkout-index: <file> is not in the cache` (видно в callback-debug.log:18, BUG-439 кейс)
- **Файл с другим blob в default index** → WT возвращается к стейту default index, не к новому HEAD

ARCH-187 Layer 3 был задуман как backstop для ARCH-186 "никогда не трогать WT", но реализация **не работает**. ADR-024 говорит «WT sync best-effort», но это означает что в проде разработчики получают dirty WT после каждой `write_lifecycle`.

Баг затрагивает **все** операции через `_atomic_write`: `write_lifecycle` (обновления статуса) **и** `create_initial` (создание новых yaml). При `create_initial` файл создаётся в HEAD, но НИКОГДА не появляется в WT. В `git status` это ` D` (unstaged deletion) — файл есть в HEAD, отсутствует в WT. Именно это объясняет TECH-446 и TECH-447 в S2: не стейл-контент, а файлы которые вообще не были созданы в WT.

**Тест `test_lifecycle.py:234` явно документирует это поведение:**
```python
# Plumbing write adds the file to HEAD but NOT to WT.
# In production the orchestrator calls git pull to sync WT.
```
Текущий production workaround — `git pull` при рестарте оркестратора. Layer D fix делает sync атомарным после каждой записи.

**Alternative fix:** `git checkout HEAD -- {path}` (вместо `checkout-index --force`). Читает из HEAD напрямую, без зависимости от приватного индекса. Именно этот подход уже используется в тестах. Потенциальный downside: обновляет default `.git/index`. Предпочтительный вариант если `env=env` не решает проблему при `create_initial` (приватный индекс содержит правильный blob, но путь у `checkout-index` может не резолвиться если CWD нестандартный).

### Layer E — Callback читает `task_status` слишком поздно (после dispatch)

`scripts/vps/callback.py`: callback **читает** `task_status` из agent_output в **Step 4** (строка 1335 через `extract_agent_output`), но dispatch qa+reflect происходит в **Step 6** (строки 1357–1371) без проверки `task_status`. Только в **Step 7** (строки 1373+) происходит проверка `task_status` и потенциальный demote lifecycle в blocked — но qa+reflect уже диспатчены.

```python
# pseudo, РЕАЛЬНОЕ поведение (не "не читает" — читает, но порядок неправильный):
skill, preview, task_status = extract_agent_output(pueue_id, ...)  # Step 4: читает

# Step 6: dispatch БЕЗ проверки task_status
if skill == "autopilot" and status == "done":   # status = pueue result ("done"="Success")
    dispatch_qa(spec_id)                         # ← диспатч, task_status не проверяется
    dispatch_reflect(task_label)

# Step 7: ТЕПЕРЬ проверяет task_status — поздно
if skill == "autopilot" and status in ("done", "failed"):
    if task_status in ("blocked", "needs_review"):
        target = "blocked"               # lifecycle обновится, qa+reflect уже летят
        log("STATUS: task_status=%s → target=blocked", task_status)
```

Cost: +$2.50-3 на каждую blocked задачу впустую. На объёме 10 blocked/день = +$25/день = $750/мес чисто на ложные qa/reflect.

---

## Связь с ARCH-193 (что закрыто, что открыто)

| Layer | Описание | ARCH-193 | TECH-194 |
|---|---|---|---|
| A | Rule 7 structural в `lifecycle.write_lifecycle` | ✅ Closed | — |
| B | autopilot/spark убраны из `_ALLOWED_WRITERS` | ✅ Closed | — |
| C | Pre-commit hook coverage всех проектов | ⚠️ Partial (main repo only) | **Fix scope** |
| D | WT sync `env=env` в `_atomic_write` | ❌ Not in scope | **Fix scope** |
| E | Callback `task_status` parser | ❌ Not in scope | **Fix scope** |
| F | Skill prompts hard-rule | ✅ Closed | — |

Layer C — ARCH-193 поставил hook в main repo, но не в worktree (где autopilot реально работает). Поэтому защита не работает.

---

## Scope

**In scope:**
- Layer C1 fix: absolute `core.hooksPath` в `setup-vps.sh --phase4-hooks`
- Layer C2 fix: pre-commit wrapper использует `GIT_COMMON_DIR` для resolve guard.mjs (устраняет fail-open в worktrees без `.claude/hooks/`)
- Layer C3 fix: guard.mjs resolve `event_writer.py` относительно `import.meta.url` (не CWD) — audit работает для DLD repo независимо от worktree
- Layer D fix: `env=env` в `checkout-index` call в `_atomic_write` (строка 270) + `_atomic_write_file` (строка 591); scope включает `create_initial` — те же строки
- Layer E fix: добавить `task_status` check в Step 6 (перед dispatch qa+reflect), не только в Step 7
- Cleanup существующих dirty lifecycle в awardybot/dowry (5+ файлов суммарно)
- Regression tests: 
  - Layer C1: hook отвергает `git commit ai/lifecycle/` из worktree
  - Layer C2: guard не fail-open в worktree где `.claude/hooks/` отсутствует в ветке
  - Layer D: после `write_lifecycle` WT == HEAD (включая `create_initial` — новый файл появляется в WT)
  - Layer E: `task_status=blocked` не диспатчит qa+reflect
- Migration helper для существующих проектов (relative → absolute hooksPath)

**Out of scope:**
- Переписывать `_atomic_write` целиком — фикс только `env=env`
- Менять формат `task_status` JSON contract
- Auto-recovery от dirty WT на orchestrator startup (отдельная спека — TECH-XXX nice-to-have)
- Удалять `--by=operator` валидацию в spec_operator (это правильный escape, в ARCH-193 объяснено)

---

## Tasks

### Task 1: Layer D — fix `env=env` loss in `_atomic_write` WT sync

**Files:** `scripts/vps/lifecycle.py`

**Change:** добавить `env=env` в оба `checkout-index --force` вызова (строки ~270 и ~591). Scope включает оба места — `_atomic_write` (используется в `write_lifecycle` **и** `create_initial`) и `_atomic_write_file` (используется в `write_file_atomic`).

```python
# BEFORE (строка ~270):
sync_result = _run(
    ["git", "checkout-index", "--force", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
    cwd=repo_dir,
)

# AFTER:
sync_result = _run(
    ["git", "checkout-index", "--force", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
    cwd=repo_dir,
    env=env,
)
```

Без `env=env` git использует default `.git/index` где lifecycle yaml **отсутствует** (он не добавляется через `git add`, только через atomic plumbing) → `checkout-index` тихо возвращает rc=1, WT не обновляется. Это затрагивает и `create_initial` — новые yaml никогда не появляются в WT после создания.

**Alternative fix (если `env=env` недостаточно):** заменить `checkout-index` на:
```python
sync_result = _run(
    ["git", "checkout", "HEAD", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
    cwd=repo_dir,
)
```
Читает blob напрямую из HEAD commit (не из индекса). Этот подход уже используется в тестах (`test_lifecycle.py:237`). Downside: обновляет default `.git/index`. Использовать как fallback если `checkout-index + env=env` показывает проблемы с `create_initial`.

**Test (Layer D):** `tests/scripts/test_lifecycle_wt_sync.py` (NEW)
- After `write_lifecycle(repo, spec_id, status="blocked", by="callback")`:
  - `git show HEAD:ai/lifecycle/{spec_id}.yaml` content == WT file content
  - `git status --short ai/lifecycle/` returns empty
- After `create_initial(repo, spec_id, ...)`:
  - `ai/lifecycle/{spec_id}.yaml` **существует в WT** (не только в HEAD)
  - WT content == HEAD content (не ` D` в git status)
- Repeat для `write_file_atomic` path

### Task 2: Layer C — absolute hooksPath + wrapper GIT_COMMON_DIR + audit path

**Files:** `scripts/vps/setup-vps.sh`, `.git-hooks/pre-commit`, `template/.git-hooks/pre-commit`, `.claude/hooks/pre-commit-lifecycle-guard.mjs`, `template/.claude/hooks/pre-commit-lifecycle-guard.mjs`, новый helper `scripts/vps/install-hooks-all-worktrees.sh`

**C1 — absolute hooksPath (setup-vps.sh):**
```bash
# BEFORE (line 72):
git -C "${proj_path}" config core.hooksPath .git-hooks

# AFTER:
git -C "${proj_path}" config core.hooksPath "${proj_path}/.git-hooks"
```
Shared git config наследуется всеми worktrees → absolute path резолвится корректно из любого worktree.

**C2 — GIT_COMMON_DIR resolve в pre-commit wrapper (`.git-hooks/pre-commit`):**
```bash
# BEFORE:
if [[ -x ".claude/hooks/pre-commit-lifecycle-guard.mjs" ]] && command -v node >/dev/null 2>&1; then
    if ! node .claude/hooks/pre-commit-lifecycle-guard.mjs; then exit 1; fi
fi

# AFTER:
_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null)
_GUARD="$(dirname "${_COMMON_DIR}")/.claude/hooks/pre-commit-lifecycle-guard.mjs"
if [[ -x "${_GUARD}" ]] && command -v node >/dev/null 2>&1; then
    if ! node "${_GUARD}"; then exit 1; fi
fi
```
`git rev-parse --git-common-dir` возвращает absolute path к `.git/` main repo → guard.mjs всегда берётся из main repo, независимо от состояния ветки worktree. Eliminates fail-open.

**C3 — absolute event_writer.py в guard.mjs:**
```js
// BEFORE:
execFileSync('python3', ['scripts/vps/event_writer.py', process.cwd(), ...])

// AFTER (резолвим относительно guard.mjs, не CWD):
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const _guardDir = dirname(fileURLToPath(import.meta.url));
const _eventWriter = resolve(_guardDir, '../../scripts/vps/event_writer.py');
execFileSync('python3', [_eventWriter, process.cwd(), ...])
```
Guard живёт в `.claude/hooks/`, `../../scripts/vps/` = DLD repo root → `scripts/vps/event_writer.py` всегда найден для DLD repo. В других проектах (awardybot/dowry) guard.mjs берётся из DLD (через absolute hooksPath), поэтому path resolves корректно.

**Test (Layer C):** `tests/integration/test_worktree_hook_blocks.py` (NEW)
- Test 1: `git -C worktree add ai/lifecycle/TEST.yaml && git commit` → должен fail (guard runs via GIT_COMMON_DIR)
- Test 2: `LIFECYCLE_WRITE_AUTHORIZED=1 git ... commit` → pass + audit event (event_writer.py найден через absolute path)
- Test 3: worktree branch БЕЗ `.claude/hooks/` → guard всё равно запускается (GIT_COMMON_DIR fix)
- Test 4: relative hooksPath legacy → после rerun phase4-hooks становится absolute (`git config core.hooksPath` начинается с `/`)

### Task 3: Layer E — callback читает task_status перед dispatch

**Files:** `scripts/vps/callback.py`

**Change:** в обработчике pueue Success result добавить парсинг `agent_output.task_status`:

```python
def _resolve_final_status(pueue_result, agent_output):
    """Determine spec lifecycle status from pueue + agent JSON."""
    if pueue_result != "Success":
        return "failed"
    ts = agent_output.get("task_status", "").lower()
    if ts == "complete":
        return "done"
    if ts == "blocked":
        return "blocked"
    if ts in ("needs_user", "skipped"):
        return ts
    # legacy: no task_status field → fall back to done (backward compat)
    return "done"

# в main flow:
final = _resolve_final_status(result, agent_output)
if final == "blocked":
    log.info("autopilot returned blocked, skipping qa+reflect dispatch")
    # запись в lifecycle делает autopilot (НЕ должен — это Layer C scope, но legacy)
    return
if final == "done":
    dispatch_qa(spec_id)
    dispatch_reflect(spec_id)
```

**Test (Layer E):** `tests/integration/test_callback_blocked_no_dispatch.py` (NEW)
- Setup: mock pueue Success + agent JSON `{"task_status": "blocked", "result_preview": "..."}`
- Assert: callback не диспатчит pueue add для qa/reflect
- Assert: lifecycle статус не меняется на done
- Counterexample: `task_status: complete` → dispatch QA+reflect как раньше

### Task 4: Cleanup existing dirty lifecycle + idempotent recovery

**Files:** new `scripts/vps/cleanup-lifecycle-drift.sh`

**Change:** скрипт для оператора — пройтись по всем проектам, для каждого dirty lifecycle yaml:
- Если staged: `git restore --staged` + `git checkout` (откат к HEAD)
- Если deleted: `git restore` (восстановить из HEAD)
- Если modified: `git checkout` (откат к HEAD — atomic plumbing уже записал актуальный SoT)

Запуск перед каждым orchestrator restart как защита от рецидива до полного фикса Layer D.

**Manual one-shot run сейчас:**
```bash
for p in awardybot dowry; do
  git -C /home/dld/projects/$p restore --staged ai/lifecycle/
  git -C /home/dld/projects/$p checkout HEAD -- ai/lifecycle/
done
```

### Task 5: Docs + ADR amendment

**Files:** `.claude/rules/architecture.md`, `.claude/rules/dependencies.md`, `.claude/skills/autopilot/autopilot-git.md`

**Change:**
- ADR-024 amendment: WT sync теперь действительно работает (Layer D fixed). Update текст: «Best-effort → reliable when env propagated».
- ADR-025 amendment: hook coverage = all repos + all worktrees (Layer C). Document absolute path requirement.
- autopilot-git.md: добавить hard rule о `task_status` JSON output как обязательном поле для `/autopilot` (Layer E contract).

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     Paths used by callback impl_guard for merge detection. -->

- `scripts/vps/lifecycle.py`
- `scripts/vps/callback.py`
- `scripts/vps/setup-vps.sh`
- `scripts/vps/cleanup-lifecycle-drift.sh`
- `scripts/vps/install-hooks-all-worktrees.sh`
- `scripts/vps/tests/test_lifecycle_wt_sync.py`
- `tests/integration/test_worktree_hook_blocks.py`
- `tests/integration/test_callback_blocked_no_dispatch.py`
- `.claude/rules/architecture.md`
- `.claude/rules/dependencies.md`
- `.claude/skills/autopilot/autopilot-git.md`
- `template/.claude/skills/autopilot/autopilot-git.md`
- `.git-hooks/pre-commit`
- `template/.git-hooks/pre-commit`
- `.claude/hooks/pre-commit-lifecycle-guard.mjs`
- `template/.claude/hooks/pre-commit-lifecycle-guard.mjs`

---

## Environment

nodejs: true (для guard.mjs тестов)
docker: false
database: false

---

## Eval Criteria (MANDATORY)

### Deterministic checks

| ID | Check | How to verify |
|---|---|---|
| D1 | `_atomic_write` передаёт env в checkout-index | `grep "checkout-index" scripts/vps/lifecycle.py` → все вхождения с `env=env` |
| D2 | После `write_lifecycle` WT файл == HEAD blob | `tests/scripts/test_lifecycle_wt_sync.py::test_wt_synced_after_write` PASS |
| C1 | Hook отвергает direct commit ai/lifecycle/ из worktree | `tests/integration/test_worktree_hook_blocks.py::test_worktree_commit_blocked` PASS |
| C2 | `setup-vps.sh --phase4-hooks` ставит absolute hooksPath | `git -C <any project> config core.hooksPath` начинается с `/` |
| C3 | guard.mjs работает из worktree | `tests/integration/test_worktree_hook_blocks.py::test_guard_in_worktree` PASS |
| C4 | guard не fail-open в worktree без `.claude/hooks/` | `tests/integration/test_worktree_hook_blocks.py::test_guard_no_failopen` PASS — guard запускается даже если branch не содержит `.claude/hooks/` |
| C5 | audit event логируется при LIFECYCLE_WRITE_AUTHORIZED=1 в DLD repo | bypass + `grep LIFECYCLE_AUTHORIZED_BYPASS` в event log → запись найдена |
| E1 | callback не диспатчит qa+reflect при `task_status=blocked` | `tests/integration/test_callback_blocked_no_dispatch.py::test_blocked_no_dispatch` PASS |
| E2 | callback диспатчит qa+reflect при `task_status=complete` | `tests/integration/test_callback_blocked_no_dispatch.py::test_complete_dispatches` PASS |

### Integration checks

| ID | Scenario | Expected |
|---|---|---|
| I1 | Orchestrator startup на проекте с dirty lifecycle | После Task 4 — clean WT; assert_clean_lifecycle_tree PASS |
| I2 | autopilot пытается direct commit ai/lifecycle/ из worktree | Hook reject + exit 1, lifecycle yaml не входит в commit |
| I3 | autopilot завершается с task_status=blocked | callback: NO qa dispatch, NO reflect dispatch, log "autopilot returned blocked" |
| I4 | Полный цикл: autopilot success → callback done → qa+reflect → backlog render | Все промежуточные WT снимки чистые (`git status` empty для `ai/lifecycle/`) |

---

## Definition of Done

- [ ] D1, D2 deterministic checks PASS (включая `create_initial` — новый файл появляется в WT)
- [ ] C1, C2, C3, C4, C5 deterministic checks PASS
- [ ] E1, E2 deterministic checks PASS
- [ ] I1-I4 integration checks PASS
- [ ] Существующие dirty lifecycle в awardybot/dowry почищены (Task 4 one-shot)
- [ ] Все 10 проектов из projects.json имеют установленный hook с absolute path
- [ ] Зафиксированы ADR amendments в architecture.md
- [ ] Полный orchestrator stack restart → нет FATAL на startup
- [ ] 24h наблюдения: lifecycle drift в любом проекте === 0
- [ ] Cost telemetry: blocked задачи больше не несут расход на qa+reflect

---

## Out of Scope (отложено в backlog для отдельной спеки)

- Auto-recovery от dirty lifecycle на orchestrator startup (вместо FATAL делать `git checkout` с audit log)
- spec_operator резка `--by=autopilot/spark` choices полностью (ARCH-193 убрал из argparse, но валидация в lifecycle всё ещё может пропустить если кто-то вызовет напрямую через Python)
- `task_status` JSON contract как формальный schema (сейчас free-form string field)
- Telemetry dashboard для lifecycle drift (count dirty файлов в час по проектам)

---

## Risk

- **Layer C изменение hooksPath на absolute** может сломать существующие worktrees если оператор не запустит migration helper. Mitigation: Task 4 включает помощник, setup-vps.sh phase4-hooks делает migration idempotently.
- **Layer E фикс callback** может оставить blocked задачи без cleanup signal в backlog. Mitigation: callback всё равно делает lifecycle write (через atomic plumbing), backlog render подхватит.
- **Layer D `env=env` fix** изменяет поведение WT sync — может выявить другие dependent bugs (rare). Mitigation: integration test I4 covers full cycle.

---

## Notes

Эта спека — **direct продолжение ARCH-193**. ARCH-193 закрыл инвариант на уровне атомарной операции (Rule 7 structural). TECH-194 закрывает **доставку этой операции** (hook делает rejection, atomic plumbing синхронизирует WT, callback читает реальный agent статус). После TECH-194 закрытия — все 4 кейса из Symptoms становятся структурно невозможны.

Forensic addendum к ARCH-193 (`ai/.council/20260525-ARCH-193/forensic-addendum.md`) идентифицировал Layer C на уровне awardybot/dld/dowry, но не упоминал worktree-специфичную проблему. Это новое открытие после ARCH-193 done.
