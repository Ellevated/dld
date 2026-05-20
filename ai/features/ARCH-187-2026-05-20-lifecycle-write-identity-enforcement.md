# ARCH-187 — Lifecycle Write Identity Enforcement (ADR-023 gap closure)

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-20

## ⚠️ ACTION REQUIRED: HUMAN REVIEW BEFORE AUTOPILOT

R1 × P0 — изменения в `callback.py` + `lifecycle.py` + `spec_operator.py` + skills audit + новый pre-commit hook. Cross-domain, ~300-500 LOC. Per CLAUDE.md routing **P0 × R1 = HUMAN**, не auto-handoff. Founder читает spec и явно отпускает в autopilot.

---

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
- `.claude/hooks/hooks.config.mjs` — register new pre-commit hook
- `template/.claude/hooks/pre-commit-lifecycle-guard.mjs` — NEW: same hook in template
- `template/.claude/hooks/hooks.config.mjs` — register in template
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

Заполняется autopilot'ом при отклонении плана от реальности.
