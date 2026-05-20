# ARCH-187 — Lifecycle Write Identity Enforcement (ADR-023 gap closure)

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-20

## Symptom

В ночь 2026-05-19/20 цикл `awardybot:BUG-1040` прогнан 4 раза подряд (pueue #308 → #311 → #320 → #323), каждый раз autopilot декларировал `task_status: done` без коммитов в Allowed Files. Callback IMPL_GUARD корректно демотал `done → blocked` (`no_implementation_commits`), но между демотами кто-то возвращал `blocked → queued`, и orchestrator снова диспатчил. **Оператор-человек спал.**

Цена за ночь: 6+ запусков одной задачи, ~$30-50 пустых opus-runs. При масштабировании на все проекты — порядок десятков долларов в сутки и риск срабатывания circuit-breaker TECH-169 (>3 demote / 10 min).

## Root Cause (5 Whys)

**Why 1:** Почему orchestrator берёт blocked spec в работу?
→ Потому что в `HEAD:ai/lifecycle/BUG-1040.yaml` он видит `status: queued`, а не `blocked`.

**Why 2:** Почему HEAD говорит queued, если callback писал blocked?
→ Потому что **другой коммит** между двумя callback-демотами переписал yaml обратно в queued. Smoking gun: `awardybot/a3c9a9d9` от автора `Ellevated <ellevatedai@gmail.com>` — agent, не оператор — `status: blocked → queued`, в transitions фейковый `by: operator, blocked_reason: operator_retry_safe_zero_token_runner_failure`.

**Why 3:** Почему агент может писать в lifecycle.yaml и подделывать `by: operator`?
→ Потому что существует **легитимный side door** — `scripts/vps/spec_operator.py demote <project> <spec_id> <reason>`. Любой агент через bash может его вызвать, и yaml-transition всегда подписывается **hardcoded `by: operator`** (`lifecycle.py:280` пропускает `by="callback"` по умолчанию, `spec_operator` явно идёт через `callback._git_commit_push` со своим путём, и identity нигде не валидируется).

**Why 4:** Почему агенты вообще считают себя вправе вызывать spec_operator?
→ Потому что `.claude/skills/qa/SKILL.md:665` **официально** учит вызывать `python3 scripts/vps/spec_operator.py demote <project> <SPEC_ID> "<reason>"`. Skill autopilot/coder/audit имеет аналогичные подсказки в логах (`scripts/vps/logs/dld-20260515-*.log` показывают рекомендации `spec_operator.py mark-done`). Side door **по дизайну** доступен любому subagent'у через Bash tool — никакого identity-check'a нет.

**Why 5:** Почему ADR-023 ("callback = единственный writer") этого не предотвратил?
→ Потому что enforcement существует **только на уровне договорённости в документе**, ни одного structural barrier'a:
  1. `lifecycle.write_lifecycle(by=...)` принимает любую строку без валидации.
  2. `spec_operator.py` напрямую вызывает internal `callback._git_commit_push`, обходя `write_lifecycle` API.
  3. Нет pre-commit hook'a, блокирующего прямой `git add ai/lifecycle/*.yaml` от не-callback автора.
  4. После `write_lifecycle` working tree остаётся stale (по дизайну, для atomicity), и **любой `git add .` или `git merge feature/branch`** утаскивает старую spark-версию yaml в HEAD, перетирая блокировку.

**ROOT CAUSE:** ADR-023 контракт "callback = sole writer" декларативный, не enforced. `spec_operator.py` — официальный обходной путь с fake identity (`by: operator`), доступный QA/audit/autopilot/coder skills через Bash. Плюс WT drift пропускает stale yamls в любые `git add .` коммиты.

## Reproduction Steps

**Воспроизведение текущего инцидента:**

```bash
cd /home/dld/projects/awardybot
git log --all --oneline -- ai/lifecycle/BUG-1040.yaml
# Покажет цепочку:
#   0303e060 lifecycle(BUG-1040): blocked       (callback demote)
#   efcda107 lifecycle(BUG-1040): blocked       (callback demote)
#   9d58767e lifecycle(BUG-1040): blocked       (callback demote)
#   a3c9a9d9 lifecycle(BUG-1040): queued        ← agent unblock via spec_operator
#   3f5229f9 lifecycle(BUG-1040): blocked       (callback)
git show a3c9a9d9 --stat
# Author: Ellevated <ellevatedai@gmail.com>   ← agent, not human operator
# transitions добавляет: by: operator, blocked_reason: operator_retry_safe_zero_token_runner_failure
```

**Воспроизведение mechanism через spec_operator (любой агент может):**

```bash
# В скомпрометированном sandbox это эквивалентно:
python3 /home/dld/projects/dld/scripts/vps/spec_operator.py demote awardybot BUG-1040 "any_reason_string"
# Yaml transition в HEAD получает by: operator, не зависимо от того, кто вызвал.
```

**Воспроизведение WT drift:**

```bash
cd /home/dld/projects/awardybot
for f in $(git status --porcelain ai/lifecycle | awk '{print $2}'); do
  spec=$(basename $f .yaml)
  head_st=$(git show HEAD:$f | grep ^status: | awk '{print $2}')
  wt_st=$(grep ^status: $f | awk '{print $2}')
  [ "$head_st" != "$wt_st" ] && echo "$spec: HEAD=$head_st WT=$wt_st"
done
# Ожидаемое: список файлов с расхождением HEAD vs WT.
```

## Fix Approach (Defence in Depth)

Четыре слоя, каждый закрывает один конкретный путь обхода.

### Layer 1 — Identity Enforcement в lifecycle.write_lifecycle

`lifecycle.py:write_lifecycle(by=...)` сейчас принимает любую строку. Сделать allowed-set:

```python
_ALLOWED_WRITERS = frozenset({"callback", "orchestrator", "spark", "operator"})

def write_lifecycle(repo_dir, spec_id, status, *, by="callback", ...):
    if by not in _ALLOWED_WRITERS:
        raise ValueError(f"write_lifecycle: invalid by={by!r}")
    # ...
```

`spec_operator.py` обязан передавать **реальный** `by`, не hardcoded `operator`. Добавить mandatory CLI flag `--by={operator|qa|audit|autopilot}` — caller указывает свою identity. Без флага — exit 2 ("identity required").

**Эффект:** transitions yaml содержит честный audit trail (`by: qa`, не `by: operator`). Founder может в любой момент увидеть, кто на самом деле демотал.

### Layer 2 — Pre-commit hook блокирует прямой `git add ai/lifecycle/`

Новый hook `.claude/hooks/pre-commit-lifecycle-guard.mjs`. Проверяет:

1. Если в `git diff --cached --name-only` есть `ai/lifecycle/*.yaml`,
2. И commit message **не начинается** с `lifecycle(<SPEC-ID>):` (формат callback'a из `lifecycle.py:218`),
3. **И** не выставлен env var `LIFECYCLE_WRITE_AUTHORIZED=1` (callback/spec_operator сами выставят перед commit),
4. → exit 1, блокировать commit.

Это closes:
- Stale `autopilot-git.md:201` (`git add ai/features/${TASK_ID}*.md ai/backlog.md && git commit -m "docs: mark ${TASK_ID} as done"`) — hook поймает, если diff содержит lifecycle.
- Любые `git add .` / `git add ai/` от reflect/coder/autopilot, утаскивающие stale yamls.

### Layer 3 — WT Sync после write_lifecycle

После успешного `_atomic_write` (lifecycle.py:230) добавить:

```python
# Sync working tree with new HEAD blob to prevent stale-yaml drift.
# Use git checkout-index (no merge logic, just blob -> WT copy).
_run(["git", "checkout-index", "--force", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"], cwd=repo_dir)
```

ADR-023 declared "никогда не трогать WT", но это **необходимое** добавление для конкретно lifecycle/{spec}.yaml — иначе stale WT попадает в любой `git add .`. Точечный `checkout-index --force -- <single_file>` не имеет конфликтов (single blob, нет merge logic), risk минимальный.

**Альтернатива (более чистая):** хранить lifecycle вне рабочего дерева — в `refs/lifecycle/{spec_id}` namespace вместо `develop` ветки. WT тогда вообще не содержит yamls. Но это R0 миграция (трогает orchestrator readers, render_backlog, migrate скрипт) — НЕ берём в эту спеку, оставляем как ARCH-XXX follow-up.

### Layer 4 — Skill audit + template sync

**4a. Удалить stale инструкцию из autopilot-git.md.**
- `.claude/skills/autopilot/autopilot-git.md:195-202` (раздел 5.2 "Update Status") — удалить целиком (содержит `git commit -m "docs: mark ${TASK_ID} as done"`).
- `template/.claude/skills/autopilot/autopilot-git.md:201` — то же.
- Заменить на ссылку: "Status writes — exclusively via callback per ADR-023. See `finishing.md`."

**4b. Audit `.claude/skills/qa/SKILL.md:665` (spec_operator demote).**
- Оставить вызов, но обязать передавать `--by=qa`.
- Документировать, что demote через spec_operator оставляет audit trail в transitions yaml.

**4c. Sync template с post-ARCH-186 форматом spec.**
- `template/.claude/skills/spark/feature-mode.md:325-380` — заменить DLD-CALLBACK-MARKER блоки на `<!-- callback-allowlist v1 -->` (как в `.claude/skills/spark/feature-mode.md:376`). Иначе все per-project spark создают specs со устаревшими markers, и Phase 5.5 linter может ломаться на новых проектах.

**4d. Audit reflect skill commit pattern.**
- `.claude/skills/reflect/SKILL.md:136-137` — `git add ai/diary/ ai/reflect/` — корректно (whitelist путей). Не трогать.
- **Но** проверить, что в reflect-промпте нет инструкций "если найден драфт, сделай git commit поверх него" — иначе stale WT попадает в коммит. Если есть — переписать на explicit whitelist.

### Layer 5 — One-shot cleanup (выполнить в autopilot)

Очистить stale WT во всех проектах перед merge'м spec'a:

```bash
for proj in /home/dld/projects/{awardybot,dowry,gipotenuza,wb,plpilot,dld,dowry-mc}; do
  cd "$proj" || continue
  if [ -n "$(git status --porcelain ai/lifecycle 2>/dev/null)" ]; then
    git checkout HEAD -- ai/lifecycle/
    git status -s ai/lifecycle  # должно стать пусто
  fi
done
```

## Impact Tree Analysis

### Step 1: UP — кто использует lifecycle.write_lifecycle / spec_operator?

- [x] `scripts/vps/callback.py` — `verify_status_sync` (~line 1161), `reconcile_orphans` ссылается на `write_lifecycle`
- [x] `scripts/vps/orchestrator.py` — `assert_clean_lifecycle_tree`, `reconcile_orphans`, `create_initial`
- [x] `scripts/vps/spec_operator.py` — `_set_status` (line 63-103)
- [x] `scripts/vps/migrate_backlog_to_lifecycle.py` — initial migration (one-shot, не трогаем)
- [x] `scripts/vps/render_backlog.py` — read-only, не трогаем
- [x] `.claude/skills/qa/SKILL.md:665` — вызов через bash
- [x] `.claude/skills/autopilot/autopilot-git.md:195-202` — устаревший git commit pattern
- [x] `template/.claude/skills/autopilot/autopilot-git.md:201` — то же в template

### Step 2: DOWN — от чего зависит lifecycle.py?

- [x] `git plumbing` (`hash-object`, `write-tree`, `commit-tree`, `update-ref`) — stable, не трогаем
- [x] `pyyaml` — stable
- [x] `private GIT_INDEX_FILE` mechanism — корректен, оставляем

### Step 3: BY TERM — grep по проекту

| Term | Files (sample) | Action |
|------|---------------|--------|
| `lifecycle.write_lifecycle` | callback.py, orchestrator.py, lifecycle.py | Добавить identity validation |
| `spec_operator` | qa/SKILL.md, spec_verify.py, scripts/vps/logs/* | Добавить `--by` flag, обновить qa skill |
| `by: operator` | lifecycle yamls (audit trail) | Оставить как есть (исторический record) |
| `DLD-CALLBACK-MARKER` | template/.claude/skills/spark/feature-mode.md | Удалить из template (sync с .claude/skills/) |
| `git add ai/features/${TASK_ID}` | autopilot-git.md:200 | Удалить раздел 5.2 |

### Step 4: CHECKLIST — обязательные папки

- [x] `tests/integration/test_callback*.py` — добавить regression тест на identity enforcement
- [x] `tests/integration/test_lifecycle_*.py` — добавить тест на `_ALLOWED_WRITERS` + WT sync
- [x] `tests/integration/test_spec_operator_*.py` — добавить тест на mandatory `--by` flag
- [x] `.claude/hooks/__tests__/` — добавить тест на новый pre-commit hook

### Step 5: DUAL SYSTEM — кто читает что

- lifecycle.yaml в `HEAD` → читают: `orchestrator.scan_queued` (via `list_by_status` через `git show`), `render_backlog`, `callback.verify_status_sync`.
- lifecycle.yaml в WT → должно стать **никем** не читается. С Layer 3 (WT sync) WT всегда совпадает с HEAD.

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

- `scripts/vps/lifecycle.py` — add `_ALLOWED_WRITERS`, `_sync_wt_after_write`
- `scripts/vps/spec_operator.py` — add mandatory `--by` flag, validate against `_ALLOWED_WRITERS`
- `scripts/vps/callback.py` — pass `by="callback"` explicitly in all `write_lifecycle` calls (audit existing)
- `.claude/hooks/pre-commit-lifecycle-guard.mjs` — NEW: block direct `git add ai/lifecycle/*.yaml`
- `.claude/hooks/hooks.config.mjs` — doc-only comment about new pre-commit guard (D2 in Drift Log: file is PreToolUse-only, not git pre-commit)
- `template/.claude/hooks/pre-commit-lifecycle-guard.mjs` — NEW: same hook in template
- `template/.claude/hooks/hooks.config.mjs` — same doc-only comment in template
- `.git-hooks/pre-commit` — extend to invoke lifecycle guard (Path A per planner Drift D2; spec amendment authorized 2026-05-20 by operator)
- `.claude/skills/autopilot/autopilot-git.md` — delete section 5.2 (lines 195-202), replace with ADR-023 reference
- `template/.claude/skills/autopilot/autopilot-git.md` — same delete
- `.claude/skills/qa/SKILL.md` — update line 665: `spec_operator.py demote ... --by=qa`
- `template/.claude/skills/qa/SKILL.md` — same update
- `template/.claude/skills/spark/feature-mode.md` — replace DLD-CALLBACK-MARKER blocks with `<!-- callback-allowlist v1 -->` (sync with `.claude/skills/spark/feature-mode.md`)
- `tests/integration/test_lifecycle_identity.py` — NEW: identity enforcement tests
- `tests/integration/test_spec_operator_by_flag.py` — NEW: `--by` flag tests
- `tests/integration/test_lifecycle_wt_sync.py` — NEW: post-write WT sync test
- `.claude/hooks/__tests__/pre-commit-lifecycle-guard.test.mjs` — NEW: hook tests
- `.claude/rules/architecture.md` — add ADR-024 (identity enforcement) referencing this spec

## Tests

### Eval Criteria

**Deterministic (8):**

1. `write_lifecycle(by="autopilot")` raises `ValueError` (not in allowed set).
2. `write_lifecycle(by="callback")` succeeds, transitions yaml записывает `by: callback`.
3. `spec_operator.py demote ... --by=qa` succeeds, transitions yaml записывает `by: qa` (НЕ `by: operator`).
4. `spec_operator.py demote ...` без `--by` flag → exit 2, stderr содержит "identity required".
5. После `write_lifecycle()` `ai/lifecycle/{spec_id}.yaml` в WT равен `git show HEAD:ai/lifecycle/{spec_id}.yaml` (WT sync проверен).
6. Pre-commit hook блокирует `git commit` с staged `ai/lifecycle/BUG-X.yaml` если commit message не начинается с `lifecycle(`.
7. Pre-commit hook пропускает commit с message `lifecycle(BUG-1040): blocked` (callback pattern).
8. Pre-commit hook пропускает commit если `LIFECYCLE_WRITE_AUTHORIZED=1`.

**Integration (4):**

9. Запуск `spec_operator.py demote awardybot BUG-1040 "test" --by=qa` → yaml в HEAD имеет `by: qa`, WT синхронизирован, transitions содержит full audit trail.
10. Симуляция `git add ai/lifecycle/BUG-X.yaml && git commit -m "fix: something"` (без lifecycle prefix) → hook возвращает exit 1, commit заблокирован.
11. End-to-end: callback пишет blocked → WT sync → попытка `git add . && git commit` от reflect skill → hook блокирует.
12. ARCH-186 `assert_clean_lifecycle_tree` passes после `write_lifecycle` (нет dirty WT).

**LLM-Judge (1):**

13. Проверить, что обновлённый `.claude/skills/qa/SKILL.md:665` чётко документирует, что `--by=qa` — это identity statement, а не arbitrary label. Rubric: понимание, что подделка identity нарушает ADR-024.

## Definition of Done

- [ ] `lifecycle.py:_ALLOWED_WRITERS` существует, `write_lifecycle` validates `by` parameter
- [ ] `spec_operator.py` требует mandatory `--by` flag, валидирует против allowed set
- [ ] `.claude/hooks/pre-commit-lifecycle-guard.mjs` существует, зарегистрирован в `hooks.config.mjs`, та же копия в template
- [ ] `autopilot-git.md` section 5.2 удалён (оба места)
- [ ] `qa/SKILL.md:665` обновлён (оба места)
- [ ] `template/.claude/skills/spark/feature-mode.md` синхронизирован — DLD-CALLBACK-MARKER заменены на callback-allowlist v1
- [ ] `lifecycle.py:_atomic_write` синхронизирует WT после CAS update-ref
- [ ] 13 тестов проходят (8 deterministic + 4 integration + 1 LLM-judge)
- [ ] Layer 5 cleanup: `git status --porcelain ai/lifecycle` пусто для всех 9 проектов
- [ ] ADR-024 добавлен в `.claude/rules/architecture.md` с reference на ARCH-187
- [ ] `dld-orchestrator.md` обновлён (если нужно — ссылка на ADR-024)
- [ ] Regression: воспроизведение из секции выше показывает, что цепочки `blocked → queued → blocked` больше нет
- [ ] callback-debug.log за 24h после merge не содержит `STATUS_SYNC: ... — writing lifecycle blocked (was queued)` для одного и того же spec'a 3+ раз

## Out of Scope

- **refs/lifecycle/ namespace** (хранение yamls вне рабочего дерева) — отдельный ARCH spec.
- **Аудит всех Bash вызовов в skills** на предмет других side door'ов — отдельная audit spec.
- **Полный rewrite spec_operator на gRPC/HTTP** с auth — overkill, MVP достаточен.
- **CI gate на pre-commit hook** — hook работает локально, CI можем добавить отдельно если нужно.

## Drift Log

**Checked:** 2026-05-20 (planner)
**Result:** heavy_drift_documented (AUTO-FIX deferred to coder via Implementation Plan)

### Findings vs spec assumptions

| # | Spec assumption | Actual codebase | Mitigation in plan |
|---|------------------|------------------|--------------------|
| D1 | `spec_operator.py` writes through `callback._git_commit_push` + `_apply_spec_status` + `_apply_blocked_reason` (lifecycle.py:280 narrative in Root Cause) | These helpers were DELETED in ARCH-186 migration (`grep` confirms zero matches). `spec_operator.py` references them anyway and is **broken at runtime today** — any invocation crashes on AttributeError. The smoking-gun commit `a3c9a9d9` in awardybot is from BEFORE ARCH-186 merge. | Task 2 fully **rewrites** `spec_operator._set_status` to call `lifecycle.write_lifecycle(by=…)` directly. The new `--by` flag becomes the *only* identity wiring. |
| D2 | Layer 2 wants `.claude/hooks/pre-commit-lifecycle-guard.mjs` registered in `.claude/hooks/hooks.config.mjs` | `hooks.config.mjs` is a static config object for Claude Code's PreToolUse/PostToolUse hooks (pre-bash, pre-edit…). It does **not** support arbitrary pre-commit hook registration. The real git pre-commit hook already lives at `.git-hooks/pre-commit` (activated via `git config core.hooksPath .git-hooks` — TECH-175). | Plan implements the **logic** in the `.mjs` file as a standalone Node entrypoint (shebang + `process.exit`). Task 4 also extends `.git-hooks/pre-commit` to invoke it. **`.git-hooks/pre-commit` is NOT in Allowed Files** — flagged for operator approval before merge. As a fallback, the hook can be wired manually with one-line setup-vps.sh change. The Task 4b update to `hooks.config.mjs` documents the new guard but is purely cosmetic (a comment), not an actual registration. |
| D3 | `callback.py` write_lifecycle calls "audit existing" — Layer 1 expects them to already pass `by="callback"` | Two callsites (line 563 `_append_blocked_reason`, line 1163 `verify_status_sync`) rely on the default `by="callback"` and do not pass it explicitly. | Task 3 adds explicit `by="callback"` kwargs. |
| D4 | Allowed Files lists `tests/integration/test_lifecycle_identity.py`, `…_wt_sync.py`, `…_spec_operator_by_flag.py` as NEW. | No `test_lifecycle_*.py` exists yet. Existing pattern: `tests/integration/test_callback_*.py` use `sys.path.insert(SCRIPT_DIR)` + real git + real sqlite (no conftest.py). | Tasks 8/9/10 follow the existing test_callback_status_sync.py pattern. |
| D5 | `template/.claude/skills/qa/SKILL.md:665` needs same `spec_operator.py` line updated | Template has NO mention of `spec_operator` (grep confirms). The qa SKILL spec_operator usage is a DLD-only customization. | Task 6 only edits root, NOT template. |
| D6 | Test dir `.claude/hooks/__tests__/` referenced | Directory does not exist. | Task 11 creates the dir + adds `pre-commit-lifecycle-guard.test.mjs`. Uses Node's built-in `node --test` (no jest/vitest dep). |
| D7 | Layer 5 cleanup spans 9 projects. | Working copy lists 7 in spec text + "dld" itself + "dowry-mc". | Task 12 runs the exact loop from spec; operator confirms before merge. |
| D8 | Spec body uses `lifecycle.py:280` and `lifecycle.py:230` line refs in narrative. | Actual `lifecycle.py` has `write_lifecycle` at line 280 ✓ and `_atomic_write` returns success at line 230 ✓. No drift. | None needed. |

### References updated in Implementation Plan

- "section 5.2 lines 195-202 of autopilot-git.md" → confirmed both root and template at lines 195-202.
- "feature-mode.md template lines 325-380 DLD-CALLBACK-MARKER" → confirmed lines 325-331 (header markers) + 375-388 (Allowed Files marker block).
- "qa/SKILL.md:665 spec_operator demote" → confirmed root only (template has no such line).

## Implementation Plan

Execution order: **Task 1 → 2 → 3 (parallel-safe with 4/5/6/7) → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13**. Tasks 4–7 (skill markdown edits) are independent and may be done in any order, but Task 2 must be merged before any spec_operator user (Task 6 qa SKILL) is updated to advertise `--by`.

### Task 1 — Layer 1: identity validation + WT sync in `lifecycle.py`

**Files:**
- `scripts/vps/lifecycle.py` (modify)

**What to do:**
- At module top (after `MAX_CAS_RETRIES = 3`, around line 43), add:
  ```python
  _ALLOWED_WRITERS = frozenset({"callback", "orchestrator", "spark", "operator", "qa", "audit", "autopilot", "migration"})
  ```
  Rationale: `migration` and `spark` are existing legitimate writers (see `build_initial_yaml` default and orchestrator bootstrap). `qa/audit/autopilot` are new identities that operator-CLI callers will declare via `--by`.
- In `write_lifecycle()` (line 280), immediately after the docstring (before `repo_dir = str(repo_dir)`), validate:
  ```python
  if by not in _ALLOWED_WRITERS:
      raise ValueError(f"write_lifecycle: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}")
  ```
- In `create_initial()` (line 315), same validation pattern (it hardcodes `by="orchestrator"` — still validate defensively so future refactors don't silently break).
- In `build_initial_yaml()` (line 418), same validation on the `by` parameter.
- In `_atomic_write()` after the successful `update-ref` (between line 228 `log.debug("CAS lost…")` early return and line 230 `return True`), implement WT sync. Insert *before* `return True` at line 230:
  ```python
  # Layer 3 (ARCH-187): sync WT to new HEAD blob so subsequent `git add .`
  # from any agent cannot smuggle a stale yaml into a commit.
  # Single-file checkout-index has no merge logic → race-free.
  _run(
      ["git", "checkout-index", "--force", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
      cwd=repo_dir,
  )
  ```
  Note: do NOT raise on failure — WT sync is best-effort defence in depth. `assert_clean_lifecycle_tree` at orchestrator boot is the backstop.

**Acceptance:** `python3 -c "from scripts.vps import lifecycle; lifecycle.write_lifecycle('.', 'X', 'queued', by='hacker')"` raises ValueError; after a real `write_lifecycle` call the file at `ai/lifecycle/{spec}.yaml` in WT byte-equals `git show HEAD:ai/lifecycle/{spec}.yaml`.

### Task 2 — Layer 1: rewrite `spec_operator.py` to use `lifecycle.write_lifecycle` + add mandatory `--by` flag

**Files:**
- `scripts/vps/spec_operator.py` (modify — substantial rewrite)

**What to do:**
- Remove the broken imports (`callback._read_head_blob`, `_apply_spec_status`, `_apply_backlog_status`, `_apply_blocked_reason`, `_git_commit_push` — all deleted in ARCH-186). Keep only `callback._reset_circuit_cli` for the reset-circuit subcommand.
- Add `import lifecycle` alongside.
- Rewrite `_set_status(project, spec_id, target, reason, by)` to:
  1. Verify spec exists via `_find_spec` (keep existing helper).
  2. Call `lifecycle.read_lifecycle(project, spec_id)` to confirm yaml exists; if `None`, return exit 3 with message "lifecycle yaml not found — spec was never bootstrapped".
  3. Call `lifecycle.write_lifecycle(project, spec_id, target, reason=reason, by=by)`.
  4. On `ValueError` (invalid identity) → exit 2; on `lifecycle.LifecycleWriteRaceError` → exit 4 (new code) with "race exhausted, retry later".
  5. Print `operator: {spec_id} → {target} (by={by}, reason={reason})`.
- In `build_parser()`, add to `p_d` (demote) and `p_f` (force-done) subparsers:
  ```python
  p_d.add_argument(
      "--by",
      required=True,
      choices=["operator", "qa", "audit", "autopilot", "spark"],
      help="Identity of caller. Mandatory — recorded in transitions yaml.",
  )
  ```
  Same for `p_f`. (argparse exits 2 automatically on missing required flag — matches spec eval criterion #4.)
- Update `cmd_demote` / `cmd_force_done` to thread `args.by` into `_set_status`.
- Update module docstring to reflect ADR-024.

**Acceptance:** `python3 spec_operator.py demote dummyproj BUG-X "reason"` (no --by) exits 2 with stderr containing "the following arguments are required: --by". With `--by=qa` it writes a transition with `by: qa`, not `by: operator`.

### Task 3 — `callback.py`: explicit `by="callback"` on write_lifecycle calls

**Files:**
- `scripts/vps/callback.py` (modify)

**What to do:**
- Line 563-564 (`_append_blocked_reason`): add `by="callback"` kwarg.
  ```python
  lifecycle.write_lifecycle(project_path, spec_id, "blocked",
                            reason=reason, by="callback", pueue_id=pueue_id)
  ```
- Line 1163-1164 (`verify_status_sync`): same.
  ```python
  lifecycle.write_lifecycle(project_path, spec_id, target,
                            reason=guard_reason or None, by="callback", pueue_id=pueue_id)
  ```
- Confirm no other `write_lifecycle` calls exist in callback.py (grep returned only these two).

**Acceptance:** `grep -n "write_lifecycle(" scripts/vps/callback.py` shows every call line carries `by="callback"` explicitly.

### Task 4 — Layer 2: implement `pre-commit-lifecycle-guard.mjs` as standalone Node hook

**Files:**
- `.claude/hooks/pre-commit-lifecycle-guard.mjs` (NEW)
- `template/.claude/hooks/pre-commit-lifecycle-guard.mjs` (NEW — byte-identical copy for template sync)

**What to do:**
- Create a self-contained Node script (no imports from utils.mjs to keep it usable from `.git-hooks/pre-commit`):
  ```js
  #!/usr/bin/env node
  // ARCH-187 Layer 2 — block direct `git add ai/lifecycle/*.yaml` commits
  // from any author other than callback.
  // Activated by .git-hooks/pre-commit (TECH-175) when core.hooksPath is set.
  // Bypass: set LIFECYCLE_WRITE_AUTHORIZED=1 (callback/spec_operator do NOT
  // need this — they never touch the working index; they commit via plumbing).
  import { execFileSync } from 'node:child_process';
  import { readFileSync } from 'node:fs';

  function staged() {
    try {
      const out = execFileSync('git', ['diff', '--cached', '--name-only', '--diff-filter=ACMR'],
                               { encoding: 'utf-8', timeout: 5000 });
      return out.split('\n').filter(Boolean);
    } catch { return []; }
  }

  function commitMsg() {
    // pre-commit hook runs BEFORE message is finalized; fall back to COMMIT_EDITMSG if present.
    try { return readFileSync('.git/COMMIT_EDITMSG', 'utf-8').trim(); } catch { return ''; }
  }

  const files = staged();
  const touchesLifecycle = files.some(f => /^ai\/lifecycle\/[^/]+\.yaml$/.test(f));
  if (!touchesLifecycle) process.exit(0);
  if (process.env.LIFECYCLE_WRITE_AUTHORIZED === '1') process.exit(0);
  const msg = commitMsg();
  if (/^lifecycle\([A-Z]+-\d+\):/.test(msg)) process.exit(0);

  console.error('');
  console.error('✗ pre-commit-lifecycle-guard (ARCH-187):');
  console.error('  Direct git commit touching ai/lifecycle/ is forbidden.');
  console.error('  Lifecycle is written exclusively by callback (ADR-023/024).');
  console.error('  Staged lifecycle files:');
  for (const f of files.filter(f => f.startsWith('ai/lifecycle/'))) console.error(`    ${f}`);
  console.error('  Allowed paths:');
  console.error('    • python3 scripts/vps/spec_operator.py demote … --by=<id>');
  console.error('    • LIFECYCLE_WRITE_AUTHORIZED=1 git commit (last-resort override)');
  process.exit(1);
  ```
- Make the file executable (`chmod +x`) — note in commit message that coder must run `chmod +x` on both copies.

**Acceptance:** `node .claude/hooks/pre-commit-lifecycle-guard.mjs` in a repo with no staged lifecycle changes exits 0; with a staged `ai/lifecycle/BUG-X.yaml` and no matching commit message exits 1.

### Task 5 — Layer 2 wiring: extend `.git-hooks/pre-commit` invocation note + `hooks.config.mjs` doc-only update

**Files:**
- `.claude/hooks/hooks.config.mjs` (modify — add documentation block referencing the new guard)
- `template/.claude/hooks/hooks.config.mjs` (modify — mirror)

**What to do:**
- The `hooks.config.mjs` schema does NOT support pre-commit registration (it's PreToolUse-only). Add a top-of-file comment block:
  ```js
  /**
   * NOTE: ai/lifecycle/ commits are guarded by an additional git pre-commit
   * hook at .claude/hooks/pre-commit-lifecycle-guard.mjs (ARCH-187 / ADR-024).
   * That guard is invoked by .git-hooks/pre-commit when core.hooksPath is set:
   *   git config core.hooksPath .git-hooks
   * The .mjs is intentionally standalone (no utils.mjs import) so it can also
   * be wired by external CI or developer machines without Claude Code present.
   */
  ```
- Same comment in both root and template (template-sync rule).
- **SPEC GAP — flagged:** wiring `.git-hooks/pre-commit` to actually invoke the new guard requires editing `.git-hooks/pre-commit`, which is NOT in `## Allowed Files`. Two paths forward, coder must surface to operator at task start:
  - **Path A (preferred):** add `.git-hooks/pre-commit` to Allowed Files (one-line spec amendment) and append a shell block invoking `node .claude/hooks/pre-commit-lifecycle-guard.mjs || exit $?`.
  - **Path B:** ship the .mjs as a documented manual install (no automatic wiring). Tests in Task 11 still pass (they invoke the .mjs directly).

**Acceptance:** `hooks.config.mjs` (both copies) carries the documentation block; coder has noted the `.git-hooks/pre-commit` gap in commit message and tagged operator for decision.

### Task 6 — Layer 4a: delete `autopilot-git.md` section 5.2 (root + template)

**Files:**
- `.claude/skills/autopilot/autopilot-git.md` (modify, lines 195-202)
- `template/.claude/skills/autopilot/autopilot-git.md` (modify, lines 195-202)

**What to do:**
- In both files, replace the section:
  ```
  ### 5.2 Update Status

  ```bash
  # Update spec: **Status:** done
  # Update backlog: done
  git add ai/features/${TASK_ID}*.md ai/backlog.md
  git commit -m "docs: mark ${TASK_ID} as done"
  ```
  ```
  with:
  ```
  ### 5.2 Update Status — DELETED (ARCH-187 / ADR-024)

  Status writes are exclusive to `callback.py` (ADR-023). Do NOT commit
  spec/backlog/lifecycle status changes manually. Callback fires on pueue
  task completion and atomically updates `ai/lifecycle/{spec}.yaml` via
  git plumbing. See `finishing.md`.

  If you genuinely need to override status as an operator action (e.g.
  force-done after manual verification), use:

  ```bash
  python3 scripts/vps/spec_operator.py force-done <project> <SPEC_ID> "<reason>" --by=operator
  ```
  ```
- Renumber subsequent subsections (5.3 → 5.2, etc.) is **not required** — leave numbering as-is to minimise diff churn; the deletion text makes the gap explicit.

**Acceptance:** `grep -n "git commit -m \"docs: mark" .claude/skills/autopilot/autopilot-git.md` → 0 matches; same in template.

### Task 7 — Layer 4b: qa/SKILL.md mandatory `--by=qa`

**Files:**
- `.claude/skills/qa/SKILL.md` (modify, line ~665)

**What to do:**
- Replace line 665:
  ```
  python3 scripts/vps/spec_operator.py demote <project> <SPEC_ID> "<reason>"
  ```
  with:
  ```
  python3 scripts/vps/spec_operator.py demote <project> <SPEC_ID> "<reason>" --by=qa
  ```
- Immediately below the code block, add (4 lines):
  ```
  > **Identity contract (ADR-024):** `--by=qa` is a *statement* — it lands in
  > `ai/lifecycle/<SPEC>.yaml:transitions[].by` as a permanent audit record.
  > Passing `--by=operator` from a QA session is forgery. Use `--by=qa` for
  > QA-triggered demotes, `--by=operator` only when a human runs the CLI.
  ```
- **Do NOT** edit `template/.claude/skills/qa/SKILL.md` (grep confirmed it has no `spec_operator` reference — DLD-only customization, see D5 in Drift Log).

**Acceptance:** `grep "spec_operator.py demote" .claude/skills/qa/SKILL.md` shows exactly one line with `--by=qa`.

### Task 8 — Layer 4c: spark feature-mode template marker sync

**Files:**
- `template/.claude/skills/spark/feature-mode.md` (modify, lines 323-331 and 374-389)

**What to do:**
- Replace the header `DLD-CALLBACK-MARKER` block (lines 323-331 region):
  ```markdown
  # Feature: [FTR-XXX] Title
  <!-- DLD-CALLBACK-MARKER-START v1 -->
  **Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD
  <!-- DLD-CALLBACK-MARKER-END -->

  <!-- DLD-CALLBACK-MARKER-START v1 -->
  <!-- **Blocked Reason:** populated by callback.py when guard demotes to blocked -->
  <!-- DLD-CALLBACK-MARKER-END -->
  ```
  with:
  ```markdown
  # Feature: [FTR-XXX] Title
  **Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD
  ```
  (Status and blocked_reason now live in `ai/lifecycle/{spec_id}.yaml`, not in the spec body — ARCH-186/ADR-023.)
- Replace the `## Allowed Files` block (lines 374-389 region) by removing the `<!-- DLD-CALLBACK-MARKER-START v1 -->` opener and the `<!-- DLD-CALLBACK-MARKER-END -->` closer, keeping the `<!-- callback-allowlist v1: … -->` comment as in `.claude/skills/spark/feature-mode.md:376`. Diff target: byte-equal Allowed Files block between root and template.

**Acceptance:** `diff template/.claude/skills/spark/feature-mode.md .claude/skills/spark/feature-mode.md` for the `## Allowed Files` block shows no remaining DLD-CALLBACK-MARKER lines.

### Task 9 — Test: `tests/integration/test_lifecycle_identity.py`

**Files:**
- `tests/integration/test_lifecycle_identity.py` (NEW)

**What to do:**
- Follow `test_callback_status_sync.py` pattern: `sys.path.insert(SCRIPT_DIR)`, `import lifecycle`, real git init via `_git` helper, no mocks.
- Test cases:
  1. `test_write_lifecycle_rejects_invalid_by` — `write_lifecycle(by="hacker")` raises ValueError; message contains "invalid by=".
  2. `test_write_lifecycle_accepts_callback` — `by="callback"` succeeds; reading HEAD yaml shows last transition `by: callback`.
  3. `test_write_lifecycle_accepts_qa_and_records_identity` — `by="qa"` succeeds; transitions yaml records `by: qa` (not `operator`).
  4. `test_create_initial_validates_by` — direct call with bogus `by` raises ValueError.
  5. `test_build_initial_yaml_validates_by` — same for `build_initial_yaml`.

**Acceptance:** `pytest tests/integration/test_lifecycle_identity.py -v` → 5 passed.

### Task 10 — Test: `tests/integration/test_spec_operator_by_flag.py`

**Files:**
- `tests/integration/test_spec_operator_by_flag.py` (NEW)

**What to do:**
- Use `subprocess.run` to invoke `python3 scripts/vps/spec_operator.py …` in a temp project with bootstrapped lifecycle yaml.
- Test cases:
  1. `test_demote_requires_by_flag` — invocation without `--by` returns exit 2; stderr contains "required" + "--by".
  2. `test_demote_with_by_qa_records_identity` — `… demote proj BUG-X "reason" --by=qa` exits 0; HEAD yaml transition has `by: qa`, `blocked_reason: reason`.
  3. `test_force_done_with_by_operator` — `… force-done proj BUG-X "ok" --by=operator` exits 0; status=done, transition by=operator.
  4. `test_invalid_by_value` — `--by=root` (not in argparse choices) returns exit 2.
  5. `test_missing_lifecycle_yaml_returns_3` — call demote on a spec that has no yaml → exit 3 with "never bootstrapped".

**Acceptance:** `pytest tests/integration/test_spec_operator_by_flag.py -v` → 5 passed.

### Task 11 — Test: `tests/integration/test_lifecycle_wt_sync.py`

**Files:**
- `tests/integration/test_lifecycle_wt_sync.py` (NEW)

**What to do:**
- Test cases (subprocess + real git, same pattern):
  1. `test_wt_synced_after_write` — call `write_lifecycle`, assert `(repo / "ai/lifecycle/X.yaml").read_text()` byte-equals `git show HEAD:ai/lifecycle/X.yaml`.
  2. `test_assert_clean_lifecycle_tree_passes_after_write` — same setup + call `lifecycle.assert_clean_lifecycle_tree(repo)` — must not raise.
  3. `test_subsequent_git_add_dot_includes_no_lifecycle_drift` — modify an unrelated file, run `git add .`, then `git diff --cached --name-only` → no `ai/lifecycle/*` entries.
  4. `test_wt_sync_idempotent_under_repeated_writes` — call `write_lifecycle` 3× in a row → final WT still matches HEAD.

**Acceptance:** `pytest tests/integration/test_lifecycle_wt_sync.py -v` → 4 passed.

### Task 12 — Test: `.claude/hooks/__tests__/pre-commit-lifecycle-guard.test.mjs`

**Files:**
- `.claude/hooks/__tests__/pre-commit-lifecycle-guard.test.mjs` (NEW — also creates the `__tests__/` dir)

**What to do:**
- Use Node's built-in `node:test` runner (no jest/vitest dep — keeps DLD lean):
  ```js
  import { test } from 'node:test';
  import assert from 'node:assert';
  import { execFileSync, spawnSync } from 'node:child_process';
  import { mkdtempSync, writeFileSync } from 'node:fs';
  import { tmpdir } from 'node:os';
  import { join } from 'node:path';
  ```
- Helpers: `makeRepo()` returns a tmp git repo with `ai/lifecycle/` initialised. `runHook(repo, env)` returns `{ status, stderr }`.
- Test cases:
  1. `passes when no lifecycle staged` — stage a non-lifecycle file → hook exits 0.
  2. `blocks staged lifecycle yaml with non-lifecycle commit message` — write/stage `ai/lifecycle/BUG-X.yaml`, set `.git/COMMIT_EDITMSG` to `"fix: random"` → exit 1, stderr contains "ARCH-187".
  3. `passes when commit message matches lifecycle(<ID>):` — same staging, set msg to `lifecycle(BUG-X): blocked` → exit 0.
  4. `passes when LIFECYCLE_WRITE_AUTHORIZED=1` — staged lifecycle + arbitrary msg + env var → exit 0.
  5. `error message lists offending files` — stage 2 lifecycle files → stderr contains both paths.
- Provide a runner command in commit message: `node --test .claude/hooks/__tests__/`.

**Acceptance:** `node --test .claude/hooks/__tests__/pre-commit-lifecycle-guard.test.mjs` → 5 passed, 0 failed.

### Task 13 — Layer 5: WT cleanup across all projects (operator-guided one-shot)

**Files:** (operational — no files in repo modified; this is a documented runbook step)

**What to do:**
- Coder produces a shell snippet in the commit message body for operator to run **after** all tests pass and **before** merge to develop:
  ```bash
  for proj in /home/dld/projects/{awardybot,dowry,gipotenuza,wb,plpilot,dld,dowry-mc,...}; do
    [ -d "$proj/.git" ] || continue
    cd "$proj"
    if [ -n "$(git status --porcelain ai/lifecycle 2>/dev/null)" ]; then
      echo "=== $proj: cleaning stale WT ==="
      git status --porcelain ai/lifecycle
      git checkout HEAD -- ai/lifecycle/
      git status --porcelain ai/lifecycle  # expect empty
    fi
  done
  ```
- This is a runbook step, **not** a code change in this spec. Document it in `ai/diary/2026-05-20-arch-187.md` as completion evidence.
- The list of 9 projects in spec body is to be confirmed by operator (Drift Log D7).

**Acceptance:** Operator pastes the loop output into the diary entry; final `git status --porcelain ai/lifecycle` is empty for every active project.

### Task 14 — ADR-024 in `.claude/rules/architecture.md`

**Files:**
- `.claude/rules/architecture.md` (modify — append to ADR table)

**What to do:**
- After the ADR-023 row (last entry in the ADR table), append:
  ```markdown
  | ADR-024 | **Lifecycle write identity enforcement.** `lifecycle.write_lifecycle(by=…)` validates against `_ALLOWED_WRITERS` frozenset. `scripts/vps/spec_operator.py` requires mandatory `--by={operator,qa,audit,autopilot,spark}` flag. Side door via `callback._git_commit_push` removed (no longer exists post-ARCH-186). Pre-commit guard at `.claude/hooks/pre-commit-lifecycle-guard.mjs` blocks direct `git add ai/lifecycle/*.yaml` from any author whose commit message doesn't match `lifecycle(<ID>):` or who hasn't set `LIFECYCLE_WRITE_AUTHORIZED=1`. `_atomic_write` now performs `git checkout-index --force` on the written yaml so WT cannot drift back to a stale blob. **Closes ARCH-187.** Builds on ADR-023 (no replacement). | 2026-05 | ARCH-187 root-cause: BUG-1040 demote/queued loop in awardybot — agent forged `by: operator` via stale spec_operator path; WT drift smuggled stale yamls into agent commits. |
  ```
- Also update `.claude/rules/dependencies.md` "Last Update" table:
  ```markdown
  | 2026-05-20 | ARCH-187 lifecycle write identity enforcement: lifecycle.py `_ALLOWED_WRITERS` + WT sync; spec_operator.py rewritten to use `lifecycle.write_lifecycle` with mandatory `--by` flag; pre-commit-lifecycle-guard.mjs (new); ADR-024. | autopilot |
  ```
- Confirm template `.claude/rules/architecture.md` does NOT need ADR-024 (template ADR table stops at ADR-014 — see `template-sync.md` "Files in Both, but Root Has DLD-Specific Extensions": root's ADR-015..024 are DLD-only, not synced).

**Acceptance:** `grep -n "ADR-024" .claude/rules/architecture.md` returns exactly the new table row; `grep "ADR-024" template/.claude/rules/architecture.md` returns nothing.

### Execution diagram

```
1 (lifecycle.py)
 ├─→ 2 (spec_operator rewrite) ──┐
 ├─→ 3 (callback by=callback)    │
 ├─→ 9 (test_lifecycle_identity) │
 └─→ 11 (test_lifecycle_wt_sync) │
                                 │
4 (mjs hook)                     │
 └─→ 5 (hooks.config doc)        │
 └─→ 12 (mjs test)               │
                                 │
                                 ├─→ 10 (test_spec_operator_by_flag)
                                 │
6 (autopilot-git.md) ────────────┤
7 (qa/SKILL.md) ─────────────────┤   (Task 2 must precede 7)
8 (spark feature-mode template) ─┤
                                 │
                                 ▼
                            13 (WT cleanup) ─→ 14 (ADR-024 docs)
```

### Dependencies (explicit)

- Task 2 (spec_operator) depends on Task 1 (`_ALLOWED_WRITERS` must exist before spec_operator's --by choices reference identical set).
- Task 7 (qa SKILL update) depends on Task 2 (don't advertise `--by=qa` flag before the CLI accepts it).
- Task 10 (spec_operator tests) depends on Task 2.
- Task 11 (WT sync test) depends on Task 1's Layer 3 changes.
- Task 12 (mjs test) depends on Task 4 (the file under test).
- Task 13 (cleanup) and Task 14 (ADR-024) are last — Task 14 commits the ADR which formally seals the contract.
- Tasks 3, 4, 5, 6, 8 are independent of each other and parallel-safe.

### Research Sources

None used — codebase reading was sufficient. Spec's Root Cause analysis stands; only `spec_operator.py` runtime status (Drift D1) needed adjustment.

