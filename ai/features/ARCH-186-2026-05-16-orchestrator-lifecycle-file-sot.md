# ARCH-186 — Orchestrator Lifecycle State SoT (git per-spec YAML)

<!-- DLD-CALLBACK-MARKER-START v1 -->
**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-16
<!-- DLD-CALLBACK-MARKER-END -->

<!-- DLD-CALLBACK-MARKER-START v1 -->
<!-- **Blocked Reason:** populated by callback.py when guard demotes to blocked -->
<!-- DLD-CALLBACK-MARKER-END -->

## ⚠️ ACTION REQUIRED: HUMAN REVIEW BEFORE AUTOPILOT

Это R1 P0 — state machine migration, cross-domain, ~600 LOC изменений в production. Founder **должен** прочитать spec и явно отпустить в autopilot перед запуском. Не auto-handoff. Никаких exceptions.

---

## Контекст

**Источник:** Council #2 synthesis — `ai/.council/20260516-github-issues-task-sot/synthesis.md`

**Решение совета:** 3 эксперта (Security, Pragmatist, Product) отвергли GitHub Issues как SoT; независимо сошлись на Option D — git per-spec yaml. Architect остался единственным сторонником Issues. Detailed rationale + dissent в synthesis.md.

**Корневая проблема:** lifecycle state (Status) задач хранится в `ai/backlog.md` table cells + `ai/features/{SPEC}.md` Status field внутри `DLD-CALLBACK-MARKER` блоков. Этот медиум — shared mutable text в git working tree, мутируется 6+ writers (orchestrator, callback, spark, planner, Hermes, manual) без storage-enforced invariant. За 2.5 месяца — 10+ фиксов вокруг одного контракта (TECH-166/168/169/172/177/181/182/BUG-185), каждый закрывал одну race и открывал другую.

**Последний эпизод (2026-05-15/16):** dowry:FTR-431 ×8, FTR-432 ×9, awardybot:TECH-965 ×10 циклов за ночь. BUG-185 фикс не сработал (0 строк `AUTOSTASH_CALLBACK_RESTORE` в логах).

## Цель

Перенести lifecycle state в **per-spec git-versioned YAML файл** (`ai/lifecycle/{spec_id}.yaml`), где **callback — единственный writer** через **atomic git plumbing commit** (private `GIT_INDEX_FILE`, без модификации working tree). Markdown остаётся как **auto-rendered read-only view**. Multi-machine workflow founder'а сохраняется (3 машины + ноут + VPS + Hermes) — все читают через `git pull`.

**Race condition становится физически невозможна** — git plumbing atomicity + CAS `update-ref` + structural enforcement (callback не трогает WT) + no-dirty-WT invariant убирают race-class.

---

## Architecture

### YAML schema (`ai/lifecycle/{spec_id}.yaml`)

```yaml
spec_id: TECH-183
status: queued | in_progress | blocked | done
priority: p0 | p1 | p2
kind: bug | ftr | tech | arch
blocked_reason: "Autopilot timed out — no commits in allowed files"   # nullable
started_at: "2026-05-16T10:30:00Z"   # nullable, set on queued→in_progress
finished_at: "2026-05-16T14:22:00Z"  # nullable, set on →done
allowed_files_hash: "sha256:abc..."  # snapshot at queue time
updated_at: "2026-05-16T14:22:00Z"
updated_by: callback   # callback | spark | manual
version: 7             # monotonic counter for CAS
transitions:
  - from: queued
    to: in_progress
    at: "2026-05-16T10:30:00Z"
    by: callback
    pueue_id: 2891
```

### Writer contract (single writer enforced by module + CI)

| Writer | Allowed | Mechanism |
|---|---|---|
| `callback.py` | yes | `scripts/vps/lifecycle.py::write_lifecycle()` |
| `orchestrator.py` | **bootstrap only** (новый spec.md без lifecycle.yaml) | `lifecycle.create_initial()` через тот же модуль |
| Spark / planner / Hermes / manual | **no** | CI check fails any PR touching `ai/lifecycle/` outside callsites above |

**Bootstrap path (resolves Devil DA-12):** orchestrator на каждом цикле сканирует `ai/features/*.md` против `ai/lifecycle/*.yaml`. Spec.md без lifecycle.yaml → `lifecycle.create_initial(spec_id, parse_priority_kind_from_spec(spec_path))` со `status: queued`. Дальше обычный dispatch flow. Spark остаётся **read-only к lifecycle** — создаёт только spec.md, orchestrator подхватывает.

### Atomic plumbing commit (external scout finding #1)

```python
def write_lifecycle(repo_dir, spec_id, status, reason=None, by="callback"):
    yaml_bytes = render_yaml(spec_id, status, reason, by)
    # 1. PRIVATE index — не трогаем shared .git/index (Devil DA-1..4 fix)
    with tempfile.NamedTemporaryFile(dir=f"{repo_dir}/.git", delete=False) as f:
        idx_path = f.name
    try:
        env = {"GIT_INDEX_FILE": idx_path, **os.environ}
        # Seed index from HEAD
        run(["git", "read-tree", "HEAD"], cwd=repo_dir, env=env)
        # Stage blob
        blob = run(["git", "hash-object", "-w", "--stdin"], input=yaml_bytes, env=env, cwd=repo_dir).stdout.strip()
        run(["git", "update-index", "--cacheinfo", f"100644,{blob},ai/lifecycle/{spec_id}.yaml"], cwd=repo_dir, env=env)
        # If render-backlog enabled — also stage backlog.md (same atomic commit)
        if should_render():
            backlog_blob = run(["git", "hash-object", "-w", "--stdin"], input=render_backlog_bytes(), env=env, cwd=repo_dir).stdout.strip()
            run(["git", "update-index", "--cacheinfo", f"100644,{backlog_blob},ai/backlog.md"], cwd=repo_dir, env=env)
        tree = run(["git", "write-tree"], cwd=repo_dir, env=env).stdout.strip()
        head = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
        msg = f"lifecycle({spec_id}): {status}"
        commit = run(["git", "commit-tree", tree, "-p", head], input=msg, cwd=repo_dir, env=env).stdout.strip()
        # CAS update-ref (external scout finding #2) — fails if HEAD moved
        run(["git", "update-ref", "refs/heads/develop", commit, head], cwd=repo_dir)
        run(["git", "push", "origin", "develop"], cwd=repo_dir)
    finally:
        os.unlink(idx_path)
```

**Why this is race-free:**
- Private `GIT_INDEX_FILE` — operator-staged changes в `.git/index` не утекают в commit (Devil DA-1..4)
- CAS `update-ref` form — если другой процесс продвинул HEAD, мы упадём с явной ошибкой и retry (external scout finding #2)
- Working tree **never touched** — autostash dance class не существует
- Идемпотентность через `version` counter в YAML

### No-dirty-WT invariant (three-level defense, patterns scout)

| Level | Where | Action |
|---|---|---|
| **Startup hard check** | orchestrator boot | `git status --porcelain ai/lifecycle/` непусто → **abort + Hermes alert** "Dirty lifecycle, fix manually" |
| **Per-cycle soft check** | каждые 5 мин в main loop | Dirty → log WARN + skip cycle (не autostash) |
| **Structural** | callback writes | pygit2/private GIT_INDEX_FILE never touches WT |

**Scope clarification (Devil DA-1..4):** dirty check охватывает **only** `ai/lifecycle/`. `ai/qa/`, `ai/reflect/`, `ai/inbox/` — outside scope (это домены QA/reflect/Hermes, не lifecycle). Если operator руками правит lifecycle.yaml — это и есть случай когда мы хотим, чтобы система остановилась и сказала «почини».

### Reader pattern (patterns scout)

```python
# orchestrator.scan_queued() — replaces scan_backlog regex
def scan_queued(repo_dir):
    queued = []
    for yaml_path in sorted(glob(f"{repo_dir}/ai/lifecycle/*.yaml")):
        data = yaml.safe_load(open(yaml_path))
        if data.get("status") in ("queued", "resumed"):
            queued.append(data["spec_id"])
    return queued
```

`yaml.safe_load` × 300 файлов = ~50-100ms. Acceptable для 5-минутного цикла.

### Restart reconcile (Devil DA-18 fix)

При startup orchestrator:
1. Прочитать все `ai/lifecycle/*.yaml`
2. Прочитать `pueue status --json`
3. Для каждого `status: in_progress` lifecycle: если соответствующего pueue task нет (или он `Failed`/`Killed`) → `lifecycle.write_lifecycle(spec_id, "queued", reason="orphaned from crash", by="callback")`
4. Log событие в `callback-audit.jsonl` для постмортема

### Multi-machine flow

| Узел | Что делает | Lifecycle access |
|---|---|---|
| Стационар | `git pull && git push` спек | Reader через FS |
| Ноут | то же | Reader через FS (offline-safe — git commit local, push later) |
| VPS (tmux) | ручной триаж | Reader через FS |
| **VPS (orchestrator+callback)** | **sole writer через atomic plumbing** | Reader+Writer |
| Hermes | Telegram queries (read-only, Phase 1) | Reader через FS |

---

## Tasks

### Task 1: `scripts/vps/lifecycle.py` — new module (~150 LOC)

**API:**
- `read_lifecycle(repo_dir, spec_id) -> dict | None`
- `write_lifecycle(repo_dir, spec_id, status, *, reason=None, by="callback", pueue_id=None, allowed_files_hash=None)` — atomic plumbing commit
- `create_initial(repo_dir, spec_id, priority, kind)` — bootstrap для новой spec.md
- `list_by_status(repo_dir, status: str|set[str]) -> list[dict]`
- `assert_clean_lifecycle_tree(repo_dir)` — startup invariant
- `reconcile_orphans(repo_dir, pueue_alive_ids: set[int])` — startup reconcile

**Invariants:**
- Atomic via `GIT_INDEX_FILE` + CAS `update-ref` + commit-tree (external scout pattern)
- Never modifies working tree
- Retries CAS up to 3 times on lost-race
- Version field is monotonic

### Task 2: `scripts/vps/callback.py` rewrite (`verify_status_sync` 284 LOC → ~40 LOC)

Replace всё marker reading/writing с одним вызовом `lifecycle.write_lifecycle()`. Implementation guard остаётся (git-diff check). Удалить:
- `_DLD_MARKER_START_RE`, `_DLD_MARKER_END_RE` (callback.py:594, 597)
- `_resync_backlog_to_spec` (line 580)
- `_append_blocked_reason` markdown editing (line 825) — теперь записывает `blocked_reason` в lifecycle.yaml
- Marker extraction helpers

**Sole-writer enforcement:** все 3 callsites записи Status (lines 1614, 580, 825) идут через `lifecycle.write_lifecycle()`. Никаких других вызовов `_git_commit_push` со Status content.

### Task 3: `scripts/vps/orchestrator.py` changes

- `scan_backlog` → `lifecycle.list_by_status({"queued", "resumed"})`. Удалить regex `r"\|\s*(queued|resumed)\s*\|"`.
- `scan_inbox` — **НЕ ТРОГАТЬ** (Hermes domain, орthogonal).
- `git_pull`: убрать autostash (81 LOC) → `git pull --ff-only`. Если non-FF — лог WARN + skip cycle.
- Удалить `_restore_callback_markers_from_head` (54 LOC).
- Добавить startup: `lifecycle.assert_clean_lifecycle_tree()` + `lifecycle.reconcile_orphans()`.
- Bootstrap: на каждом цикле, перед `scan_queued`, найти `ai/features/*.md` без `ai/lifecycle/*.yaml` → `lifecycle.create_initial()`.

### Task 4: `scripts/vps/render_backlog.py` — new (~80 LOC)

Render `ai/backlog.md` from `ai/lifecycle/*.yaml`. Group by section (current backlog.md headers сохранить). Вызывается callback'ом в том же atomic commit что и lifecycle update (best-effort — если render падает, лог WARN, не блокировать lifecycle write).

### Task 5: `scripts/vps/migrate_backlog_to_lifecycle.py` — one-shot (~100 LOC)

**Idempotent + dry-run + human gate (Devil mitigation):**
1. Parse `ai/backlog.md` table rows → extract (spec_id, status, priority, kind)
2. Parse `ai/features/{spec_id}*.md` → extract Status field + Blocked Reason если есть
3. Cross-validate: backlog row status MUST match spec Status field. Mismatch → ERROR + manual review needed.
4. Build YAML in-memory.
5. **Dry-run by default:** print proposed yamls + diff to terminal. Exit 0.
6. With `--commit` flag: write files to WT. Operator делает `git diff`, `git add ai/lifecycle/`, `git commit`. **No auto-commit.**
7. Round-trip: после write, re-parse созданные yamls и сравнить status set с original. Mismatch → exit 1.

### Task 6: DELETE files / functions

- `scripts/vps/marker_utils.py` — весь файл (117 LOC)
- `scripts/vps/tests/test_marker_utils.py` (118 LOC)
- `scripts/vps/tests/test_orchestrator_autostash_marker.py` (134 LOC)
- callback `verify_status_sync` старая (284 LOC) — заменена на ~40
- orchestrator `_restore_callback_markers_from_head` (54 LOC)
- orchestrator autostash code в `git_pull` (~81 LOC) — заменена на ff-only check (~10 LOC)
- TECH-169 circuit-breaker — **оставить как safety net** (не удалять, может пригодиться при unknown failure modes)

### Task 7: Spec template update

`.claude/skills/spark/feature-mode.md` template:
- Удалить `DLD-CALLBACK-MARKER-START/END` блоки
- Status секция теперь просто `## Lifecycle: ai/lifecycle/{spec_id}.yaml`
- Allowed Files остаётся (нужен для implementation guard)

### Task 8: `.claude/rules/architecture.md` — new ADR-023

```markdown
| ADR-023 | Lifecycle state SoT = git per-spec YAML | 2026-05 | См. dld-orchestrator.md§7 |
```

ADR text: state lives in `ai/lifecycle/{spec_id}.yaml`. Callback = single writer (enforced via `lifecycle.py` module API + CI check). Atomic plumbing commit via private `GIT_INDEX_FILE` + CAS `update-ref`. No-dirty-WT invariant убирает корень BUG-185.

**Superseded:** ADR-018 (callback Status enforcement в markdown) — заменён ADR-023. Помечен `superseded by ADR-023`.

### Task 9: `.claude/rules/dependencies.md` updates

Добавить `scripts/vps/lifecycle.py` секцию:
- Uses: `pathlib`, `subprocess` (git), `yaml`
- Used by: `callback.py`, `orchestrator.py`, `render_backlog.py`

Удалить `marker_utils.py` секцию. Обновить callback.py и orchestrator.py зависимости (убрать marker_utils, добавить lifecycle).

### Task 10: Tests (мин 3 новых, удалить 714 LOC старых)

См. ## Tests ниже.

### Task 11: Migration rollout

Pilot: dld проект. Один день наблюдения. Если re-dispatch loops == 0 за 24h — sweep остальные 9 проектов одной командой через autopilot per-project.

---

## Allowed Files

<!-- callback-allowlist v1 -->
<!-- DLD-CALLBACK-MARKER-START v1 -->
- `scripts/vps/lifecycle.py` — **NEW** module (atomic plumbing + reader + reconcile)
- `scripts/vps/callback.py` — rewrite verify_status_sync, удалить marker helpers
- `scripts/vps/orchestrator.py` — scan_queued, no-dirty-WT, ff-only pull, удалить _restore_callback_markers_from_head + autostash
- `scripts/vps/render_backlog.py` — **NEW** auto-render
- `scripts/vps/migrate_backlog_to_lifecycle.py` — **NEW** one-shot migration
- `scripts/vps/marker_utils.py` — **DELETE**
- `scripts/vps/tests/test_lifecycle.py` — **NEW** unit tests
- `scripts/vps/tests/test_orchestrator_lifecycle.py` — **NEW** integration
- `scripts/vps/tests/test_callback.py` — modify (drop marker tests, keep guard tests)
- `scripts/vps/tests/test_marker_utils.py` — **DELETE**
- `scripts/vps/tests/test_orchestrator_autostash_marker.py` — **DELETE**
- `.claude/skills/spark/feature-mode.md` — template без DLD-CALLBACK-MARKER
- `.claude/rules/architecture.md` — ADR-023
- `.claude/rules/dependencies.md` — lifecycle.py entry, drop marker_utils
- `ai/lifecycle/*.yaml` — **NEW** state files (data, не source)
- `ai/backlog.md` — становится auto-rendered read-only view
<!-- DLD-CALLBACK-MARKER-END -->

---

## Tests

### Test 1 (unit, lifecycle.py): atomic write under concurrency
```python
def test_concurrent_writes_no_loss(tmp_git_repo):
    """10 параллельных write_lifecycle() для разных spec — все попадают в HEAD, version counters монотонны."""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(10) as ex:
        list(ex.map(
            lambda i: lifecycle.write_lifecycle(tmp_git_repo, f"TECH-{i}", "queued"),
            range(10)
        ))
    # All 10 yamls in HEAD
    for i in range(10):
        data = lifecycle.read_lifecycle(tmp_git_repo, f"TECH-{i}")
        assert data["status"] == "queued"
        assert data["version"] >= 1
```

### Test 2 (unit, lifecycle.py): private GIT_INDEX_FILE — operator-staged files не утекают
```python
def test_operator_staged_file_does_not_leak(tmp_git_repo):
    """Operator делает git add some-other-file. Callback пишет lifecycle. Commit содержит ТОЛЬКО lifecycle, не some-other-file."""
    (tmp_git_repo / "operator-wip.txt").write_text("wip")
    run(["git", "add", "operator-wip.txt"], cwd=tmp_git_repo)
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-100", "done")
    # Last commit changed только ai/lifecycle/TECH-100.yaml
    out = run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=tmp_git_repo).stdout
    assert "ai/lifecycle/TECH-100.yaml" in out
    assert "operator-wip.txt" not in out
    # operator-wip.txt всё ещё staged, не потеряна
    assert "operator-wip.txt" in run(["git", "diff", "--cached", "--name-only"], cwd=tmp_git_repo).stdout
```

### Test 3 (regression, BUG-185 scenario): autostash race impossible
```python
def test_dirty_wt_does_not_revert_callback_write(tmp_git_repo):
    """Simulate BUG-185: dirty WT + callback write. Lifecycle.yaml в HEAD остаётся 'done' даже после следующего scan."""
    # Setup: spec is queued
    lifecycle.create_initial(tmp_git_repo, "TECH-200", "p1", "tech")
    # Dirty up WT (orchestrator's typical mess)
    (tmp_git_repo / "ai/qa/garbage.md").write_text("untracked")
    # Callback writes done
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-200", "done")
    # Orchestrator next cycle (no autostash dance)
    orchestrator.git_pull_ff_only(tmp_git_repo)  # no-op if up-to-date
    queued = lifecycle.list_by_status(tmp_git_repo, "queued")
    # BUG-185 would have showed TECH-200 here. Option D — never.
    assert "TECH-200" not in [s["spec_id"] for s in queued]
```

### Test 4 (integration, orchestrator restart reconcile): orphaned in_progress demoted
```python
def test_orphaned_in_progress_demoted_on_restart(tmp_git_repo, mock_pueue):
    """Lifecycle says in_progress, no live pueue task → reconcile demotes to queued."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-300", "in_progress", pueue_id=999)
    mock_pueue.set_alive_ids(set())  # task 999 не существует
    orchestrator.startup_reconcile(tmp_git_repo)
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-300")
    assert data["status"] == "queued"
    assert "orphaned from crash" in data["blocked_reason"] or data["transitions"][-1]["by"] == "callback"
```

### Test 5 (integration, no-dirty-WT invariant): dirty lifecycle aborts startup
```python
def test_dirty_lifecycle_aborts_orchestrator_startup(tmp_git_repo):
    """Manual edit to ai/lifecycle/TECH-X.yaml → startup raises."""
    lifecycle.create_initial(tmp_git_repo, "TECH-400", "p1", "tech")
    (tmp_git_repo / "ai/lifecycle/TECH-400.yaml").write_text("manually corrupted\n")
    with pytest.raises(RuntimeError, match="Dirty lifecycle"):
        lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)
```

### Test 6 (integration, bootstrap path): new spec.md → orchestrator creates lifecycle.yaml
```python
def test_bootstrap_creates_lifecycle_for_new_spec(tmp_git_repo):
    """Spark создал spec.md без lifecycle.yaml. Orchestrator cycle создаёт initial."""
    spec = tmp_git_repo / "ai/features/TECH-500-foo.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# TECH-500\n**Priority:** P1\n**Kind:** tech\n")
    assert not (tmp_git_repo / "ai/lifecycle/TECH-500.yaml").exists()
    orchestrator.bootstrap_new_specs(tmp_git_repo)
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-500")
    assert data["status"] == "queued"
    assert data["priority"] == "p1"
```

---

## Definition of Done

- [ ] Все 6 новых тестов проходят (`./test fast`)
- [ ] 714 LOC старых тестов удалены (test_marker_utils.py + test_orchestrator_autostash_marker.py + marker tests из test_callback.py)
- [ ] `marker_utils.py` удалён, нет imports
- [ ] `verify_status_sync` < 50 LOC, использует `lifecycle.write_lifecycle()`
- [ ] orchestrator startup: `assert_clean_lifecycle_tree()` + `reconcile_orphans()` + `bootstrap_new_specs()`
- [ ] orchestrator `git_pull` → `git pull --ff-only` (autostash удалён)
- [ ] Pilot на dld: миграция через `migrate_backlog_to_lifecycle.py --commit`, 24h наблюдения, **0 re-dispatch loops** в логах
- [ ] После pilot: rollout на 9 остальных проектов через `autopilot per project`
- [ ] ADR-023 в architecture.md; ADR-018 помечен `superseded by ADR-023`
- [ ] dependencies.md обновлён (lifecycle.py entry, marker_utils entries удалены)
- [ ] Spec template (.claude/skills/spark/feature-mode.md) — без DLD-CALLBACK-MARKER блоков
- [ ] backlog.md auto-rendered корректно (визуально совпадает с текущим форматом)
- [ ] CI check: PR touching `ai/lifecycle/` outside callback.py/lifecycle.py → fail
- [ ] No regressions в test_callback.py (guard тесты остались, marker тесты удалены)

---

## Migration Plan (приложение)

**День 0 (ship PR):**
- Merge PR в develop
- Stop orchestrator: `systemctl stop dld-orchestrator` (или kill pueue group)
- Run `python3 scripts/vps/migrate_backlog_to_lifecycle.py` (dry-run) на dld
- Human review diff
- Run с `--commit`, commit + push
- Start orchestrator
- Watch logs 24h: AUTOSTASH events = 0, no_dirty_WT skips = 0 ideally (если >0 — manual cleanup), re-dispatch loops = 0

**День 1:** if dld green — sweep 9 проектов одной командой:
```bash
for proj in $(ls -d /home/dld/projects/*/); do
  python3 scripts/vps/migrate_backlog_to_lifecycle.py --commit --repo "$proj"
done
```

**День 7:** post-mortem. Если incidents == 0 — Phase 1 (Hermes structured queries + dld triage CLI) можно начинать как новая spec.

---

## Research Sources

- `ai/.council/20260516-github-issues-task-sot/synthesis.md` — full council rationale
- `ai/.spark/ARCH-186/scout-external.md` — git plumbing patterns, CAS update-ref, per-file YAML validation
- `ai/.spark/ARCH-186/scout-codebase.md` — exact LOC counts, regex names, callsite map
- `ai/.spark/ARCH-186/scout-patterns.md` — atomic write mechanism, three-level no-dirty-WT defense, reader patterns
- `ai/.spark/ARCH-186/scout-devil.md` — edge cases mitigated (DA-1..4 index contamination, DA-12 bootstrap, DA-18 reconcile)
- ADR-018 (.claude/rules/architecture.md) — будет superseded
- BUG-185 — историческая попытка band-aid, удаляется в этом PR
- beads, tick-md — industry validation of git-as-state-SoT pattern
