# Bug Fix: [BUG-192] Callback gate `_subject_implements` blind to real autopilot commit formats

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-25

---

## Symptom

Ночью 2026-05-24/25 callback (`verify_status_sync` в `scripts/vps/callback.py`) демоутнул 5 завершившихся успешно (exit_code=0) autopilot-сессий в `blocked` с reason=`no_merged_implementation`, хотя код был реально написан и merge'нут в `origin/develop`. Audit-log (`scripts/vps/callback-audit.jsonl`):

| ts                   | project    | spec       | in→out          | reason                   | code_commits | code_loc |
|----------------------|------------|------------|-----------------|--------------------------|--------------|----------|
| 2026-05-24T21:52:17Z | dowry      | FTR-441    | done→blocked    | no_merged_implementation | 3            | 121      |
| 2026-05-24T22:06:54Z | wb         | FTR-182    | done→blocked    | no_merged_implementation | 0            | 0        |
| 2026-05-24T22:28:16Z | awardybot  | FTR-1076   | done→blocked    | no_merged_implementation | 3            | 458      |
| 2026-05-25T00:04:40Z | awardybot  | FTR-1077   | blocked→blocked | no_merged_implementation | 2            | 653      |
| 2026-05-25T01:16:52Z | awardybot  | FTR-1078   | done→blocked    | no_merged_implementation | 2            | 502      |

FTR-1078 случайно "спасся" во второй попытке (pueue 412) через `already_done_terminal` (Rule 7) — race condition с `lifecycle.write_lifecycle` (см. Defect 3 → ARCH-193). FTR-1076 не повезло так же.

Только 2 спеки за ночь прошли gate чисто (BUG-1065, ARCH-440) — у них совпал commit format.

---

## Root Cause — три независимых дефекта

### Defect 1 (in scope): `_subject_implements` слишком строг

`scripts/vps/callback.py:673-711` принимает ТОЛЬКО:

```python
# Conventional with EXACT-case spec_id in scope
re.match(r"^[a-z]+\(([^)]*)\)!?:", subject)
if spec_id in scopes:    # <— case-sensitive list membership
# Merge with space immediately after
re.match(rf"^merge\s+{re.escape(spec_id)}\b", subject, re.IGNORECASE)
# Legacy bare
re.match(rf"^{re.escape(spec_id)}:\s", subject)
```

Симуляция на 6 реальных коммитах FTR-1076 → **0/6** matches. Реальные формы, которые **должны** считаться валидными, но не считаются:

| Реальный subject                                                       | Почему не матчит                                       |
|------------------------------------------------------------------------|--------------------------------------------------------|
| `feat(ftr-1076): add WB API key Pydantic schemas`                      | scope lowercase → `"FTR-1076" in ["ftr-1076"]` = False |
| `chore(ftr-1076): mark done in spec + backlog`                         | то же                                                  |
| `Merge feature/FTR-1076: SRID — MC admin endpoint`                     | regex требует `\s+` сразу за Merge, а стоит `feature/` |

`gate_logic.py:167` (`match_subject`) — **тот же код**, "Renamed from callback._subject_implements". Один и тот же баг в двух местах.

### Defect 2 (in scope): autopilot не имеет SSOT для commit format

Модель сама выбирает scope, **разные сессии — разный стиль на одну и ту же спеку**. Из 8 спек за ночь:

| Прошли gate ✅              | Не прошли gate ❌                                                          |
|----------------------------|----------------------------------------------------------------------------|
| `chore(ARCH-440): ...`     | `feat(ftr-1076): ...` (lowercase)                                          |
| `fix(BUG-1065): ...`       | `feat(billing): SRID pre-withdrawal gate (Layer 3 of 3)` (component scope) |
|                            | `feat(migrations): create dowry.principal_tariffs (FTR-441 Task 2/3)`      |
|                            | `fix(db): restore missing uq_account_group constraint (BUG-439)`           |

Нет жёсткой инструкции в `.claude/agents/coder.md` или `.claude/skills/autopilot/SKILL.md` про обязательный формат `<type>(SPEC_ID): description` с UPPERCASE scope.

### Defect 3 (OUT OF SCOPE → ARCH-193): self-promote vs gate SoT

Внутри autopilot session коммиты вида `lifecycle(FTR-1078): done` создаются (committer time 04:12 внутри pueue 412 session), хотя по ADR-023 единственный writer — callback после exit. И FTR-1078 в развитии получил `lifecycle(FTR-1078): done` (04:12), потом `lifecycle(FTR-1078): blocked` (04:16) — Rule 7 "done is terminal" нарушено.

Это **архитектурный** вопрос (кто SoT — callback gate или autopilot self-write), требует Council. См. Out of Scope.

---

## Reproduction Steps

```bash
cd /home/dld/projects/awardybot
git log --grep "FTR-1076" --oneline
# → cc6b88f6 feat(ftr-1076): add set_seller_wb_api_key_impl + PUT route
#   (4 task commits + Merge feature/FTR-1076)

python3 -c "
import sys; sys.path.insert(0, '/home/dld/projects/dld/scripts/vps')
from callback import _subject_implements
for sub in [
    'feat(ftr-1076): add WB API key Pydantic schemas',
    'Merge feature/FTR-1076: SRID — MC admin endpoint',
    'chore(ftr-1076): mark done in spec + backlog',
]:
    print(_subject_implements(sub, 'FTR-1076'), sub)
"
# Expected: True for all. Actual: False for all.
```

Then in audit log:
```bash
grep '"spec_id": "FTR-1076"' /home/dld/projects/dld/scripts/vps/callback-audit.jsonl | tail -2
# → "reason": "no_merged_implementation" (демоут несмотря на 3 коммита и 458 LOC)
```

---

## Fix Approach

### Task 1 — Level 1a: case-insensitive scope match

`scripts/vps/callback.py:703` и аналогично в `scripts/vps/gate_logic.py`:

```python
# было
if spec_id in scopes:
    return True

# стало
if any(s.strip().upper() == spec_id.upper() for s in scopes):
    return True
```

### Task 2 — Level 1b: merge with branch prefix

`scripts/vps/callback.py:706` и `scripts/vps/gate_logic.py`:

```python
# было
if re.match(rf"^merge\s+{re.escape(spec_id)}\b", subject, re.IGNORECASE):

# стало
if re.match(rf"^merge\s+(\S+/)?{re.escape(spec_id)}\b", subject, re.IGNORECASE):
```

Это покрывает `Merge feature/FTR-1076`, `Merge autopilot/BUG-XXX`, `Merge fix/BUG-YYY` и т.д.

**НЕ принимаем** trailing-form `feat(component): ... (SPEC-ID Task N)` — TECH-177 явно запрещает body/trailer mentions из-за false-positive incident 2026-05-04 (awardybot). Это решение по committer'ской дисциплине, не technical: trailing-форму чиним через Level 2.

### Task 3 — Level 2: autopilot commit-format SSOT

В `.claude/agents/coder.md` (новый раздел или начало файла) + sync в `template/.claude/agents/coder.md` (правило `template-sync.md`):

```markdown
## Commit Format (MANDATORY)

When committing as part of an autopilot SPEC_ID task, the commit subject MUST follow:

  <type>(SPEC_ID): <imperative description>

Where:
- `<type>` = feat | fix | chore | docs | refactor | test (Conventional Commits)
- `SPEC_ID` = the EXACT spec ID in UPPERCASE (e.g. `FTR-1076`, not `ftr-1076`)
- Spec ID MUST be in scope `()`, NOT in trailing text like `(FTR-XXX Task N)`

✅ Allowed:
  feat(FTR-1076): add WB API key Pydantic schemas
  fix(BUG-439): restore missing uq_account_group constraint
  test(TECH-189): autouse db isolation fixture
  chore(ARCH-186): bootstrap epic tracker

❌ Forbidden:
  feat(ftr-1076): ...                    # lowercase scope
  feat(billing): ... (FTR-1076 Task 3)   # component scope, spec_id in trail
  fix(db): ... (BUG-439)                 # trailing-only spec_id
  feat: FTR-1076 description             # no scope, spec_id in message

Why: callback gate (scripts/vps/callback.py:_subject_implements) parses ONLY
the scope. Trailing mentions trigger false-positives from cross-references
(TECH-177 incident 2026-05-04). Compliance is enforced by gate — non-compliant
commits cause false demote and burn compute on re-dispatch.

For merge commits (PHASE 3): `Merge feature/SPEC_ID: <description>` is
accepted by gate (Level 1b fix).
```

То же — в `.claude/skills/autopilot/SKILL.md` и `template/.claude/skills/autopilot/SKILL.md` — короткая отсылка к coder.md или дубликат раздела.

---

## Impact Tree Analysis

### Step 1: UP — кто использует?

`_subject_implements` / `match_subject` callers:

| Caller                            | Файл                                              |
|-----------------------------------|---------------------------------------------------|
| `_is_done_on_develop`             | `scripts/vps/callback.py:773`                     |
| `find_implementation_commit`      | `scripts/vps/gate_logic.py:170` (renamed copy)    |
| Tests                             | `scripts/vps/tests/test_callback.py:355-368`      |

### Step 2: DOWN — что зависит?

| Уровень   | Что меняется                                                        |
|-----------|---------------------------------------------------------------------|
| callback  | `_subject_implements` — 2 regex pattern + 1 list comparison         |
| gate_logic| `match_subject` — те же 2 паттерна                                  |
| autopilot | новый раздел в coder.md + ссылка из autopilot/SKILL.md              |

### Step 3: BY TERM — grep entire project

| Term                            | Files (expected to update)                                       |
|---------------------------------|------------------------------------------------------------------|
| `_subject_implements`           | callback.py (1), tests/test_callback.py (already has cases)      |
| `match_subject`                 | gate_logic.py (1), tests/test_gate_logic.py — extend             |
| `^merge\s+{spec_id}\b`          | callback.py:706, gate_logic.py — sync                            |
| commit format rules             | coder.md (new), autopilot/SKILL.md (mention), templates (sync)   |

### Step 4: Checklist обязательных папок

- [x] `scripts/vps/` — callback.py + gate_logic.py + tests
- [x] `tests/` — unit tests extension
- [x] `.claude/agents/` + `template/.claude/agents/` (template-sync.md)
- [x] `.claude/skills/autopilot/` + `template/.claude/skills/autopilot/`

### Step 5: DUAL SYSTEM — нет (один writer, один формат)

---

## Research Sources

- **Memory:** `~/.claude/projects/-home-dld-projects-dld/memory/project_callback-false-done-pattern.md` — known TECH-176/177/179 series; algorithm for diagnosing recurrence
- **ADR-023** (rules/architecture.md): lifecycle SoT = git per-spec YAML; callback = sole writer
- **TECH-177 docstring** (`callback.py:676-679`): body/footer/trailer mentions DO NOT count — anti-false-positive from awardybot 2026-05-04 incident. Level 1c (trailing fallback) explicitly NOT done because of this.
- **Audit evidence**: `scripts/vps/callback-audit.jsonl` (14 decisions 24-05 20:00 → 25-05 05:00)
- **Existing tests**: `scripts/vps/tests/test_callback.py:355-368` — covers current accepted forms; new tests must KEEP them passing AND add new forms.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback.py` — Level 1a + 1b: 2 regex patches in `_subject_implements` (modify)
- `scripts/vps/gate_logic.py` — same 2 regex patches in `match_subject` (modify)
- `scripts/vps/tests/test_callback.py` — extend existing tests for new accepted forms (modify)
- `.claude/agents/coder.md` — new `## Commit Format` section (modify)
- `template/.claude/agents/coder.md` — sync (modify; template-sync.md rule)
- `.claude/skills/autopilot/SKILL.md` — short reference to coder.md commit format (modify)
- `template/.claude/skills/autopilot/SKILL.md` — sync (modify)

<!-- DLD-CALLBACK-MARKER-END -->

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Definition of Done

- [ ] **Task 1 landed**: `_subject_implements` (callback.py) и `match_subject` (gate_logic.py) принимают `feat(ftr-1076):` case-insensitive
- [ ] **Task 2 landed**: оба принимают `Merge feature/FTR-1076:` / `Merge autopilot/SPEC:` / любой `Merge <prefix>/SPEC-ID`
- [ ] **Task 3 landed**: `.claude/agents/coder.md` + `template/.claude/agents/coder.md` содержат раздел `## Commit Format` с правилом
- [ ] **All existing tests** in `scripts/vps/tests/test_callback.py` (lines 355-368) STILL PASS
- [ ] **TECH-177 invariant preserved**: subjects типа `feat(other): see also FTR-925` или `Refs: FTR-925` НЕ матчатся (regression test)
- [ ] **New unit tests** покрывают 6 реальных subject форм из ночного audit log (FTR-1076 кейс)
- [ ] **Integration test**: симуляция callback.verify_status_sync на mocked repo с lowercase scope коммитом → должна вернуть status=done, не blocked
- [ ] **No new failures** — `./test fast` зелёный
- [ ] **commit format** соблюдён: `fix(BUG-192): ...` UPPERCASE scope (self-eats own dogfood)

---

## Tests

### Unit Tests (extend `scripts/vps/tests/test_callback.py`)

```python
class TestSubjectImplementsRealWorld:
    """Real-world subjects from awardybot 2026-05-24/25 night — should all match."""

    def test_lowercase_scope(self):
        assert callback._subject_implements(
            "feat(ftr-1076): add WB API key Pydantic schemas", "FTR-1076"
        )
        assert callback._subject_implements(
            "chore(ftr-1076): mark done in spec + backlog", "FTR-1076"
        )

    def test_merge_with_branch_prefix(self):
        assert callback._subject_implements(
            "Merge feature/FTR-1076: SRID — MC admin endpoint", "FTR-1076"
        )
        assert callback._subject_implements(
            "Merge autopilot/BUG-1065 into develop", "BUG-1065"
        )
        assert callback._subject_implements(
            "Merge fix/BUG-439 — restore constraint", "BUG-439"
        )

    def test_case_insensitive_multi_scope(self):
        # mixed case in multi-scope
        assert callback._subject_implements(
            "feat(area, ftr-1076, FTR-1077): both", "FTR-1077"
        )

class TestSubjectImplementsAntiFalsePositive:
    """TECH-177 invariant: body/trailer mentions DO NOT count.
       MUST stay False after BUG-192 fix."""

    def test_trailing_only_rejected(self):
        # spec_id in trailing description, NOT in scope — must reject
        assert not callback._subject_implements(
            "feat(billing): SRID pre-withdrawal gate (FTR-1077 Task 3)", "FTR-1077"
        )
        assert not callback._subject_implements(
            "fix(db): restore constraint (BUG-439)", "BUG-439"
        )

    def test_see_also_rejected(self):
        assert not callback._subject_implements(
            "feat(other): see also FTR-925", "FTR-925"
        )

    def test_refs_footer_rejected(self):
        # we only get subject (first line), but ensure 'Refs:' style line
        # at start would also not match
        assert not callback._subject_implements(
            "Refs: FTR-925", "FTR-925"
        )
```

### Integration Test (extend `tests/integration/test_callback_already_merged.py` or new)

```python
def test_callback_recognizes_lowercase_scope_merge(tmp_path):
    """End-to-end: callback.verify_status_sync sees merged commit with
       lowercase scope + branch-prefix merge — should NOT demote."""
    # 1. setup repo with origin/develop containing:
    #    - feat(ftr-100): impl (touches src/x.py)
    #    - Merge feature/FTR-100: ...
    # 2. write lifecycle FTR-100 = "queued"
    # 3. call verify_status_sync(repo, "FTR-100", target="done")
    # 4. assert lifecycle status == "done"
    # 5. assert audit reason == "ok"  (not "no_merged_implementation")
```

### Regression Test (gate_logic parity)

```python
def test_gate_logic_match_subject_parity_with_callback():
    """Ensure both functions accept identical sets of subjects after fix."""
    test_cases = [
        ("feat(ftr-1076): impl", "FTR-1076", True),
        ("Merge feature/FTR-1076: foo", "FTR-1076", True),
        ("feat(other): see FTR-925", "FTR-925", False),
    ]
    for subject, spec_id, expected in test_cases:
        assert callback._subject_implements(subject, spec_id) == expected
        assert gate_logic.match_subject(subject, spec_id) == expected
```

---

## Out of Scope (will be separate specs)

### ARCH-193 (TBD) — SoT decision: callback gate vs autopilot self-promote

**Symptom observed:** FTR-1078 lifecycle went `done → blocked` in 4 minutes (04:12 → 04:16), violating Rule 7 "done is terminal". Self-referential `lifecycle(FTR-1078): done` commits appear inside autopilot sessions — who's writing them? ADR-023 says only callback. Either:

- a docs leak (some other process imports `lifecycle.write_lifecycle`), or
- callback re-entrancy / race, or
- explicit autopilot-internal self-promote step

Decision needed (Council): keep callback as sole writer + close the leak, OR formalize self-promote as legitimate path and rewrite gate as advisory.

**Why deferred:** architectural decision with cross-cutting impact. Council #2 (ARCH-186) already negotiated SoT — re-opening requires same level of rigor.

### Manual: recovery of 5 blocked specs (FTR-1076, FTR-1077, FTR-441, BUG-439, FTR-182)

User confirmed manual handling after BUG-192 landing — not in this spec's DoD.

---

## Flow Coverage Matrix

| # | Step                                                          | Covered by Task | Status |
|---|---------------------------------------------------------------|-----------------|--------|
| 1 | autopilot writes commits with consistent format               | Task 3          | ✓      |
| 2 | callback parses lowercase scope                               | Task 1          | ✓      |
| 3 | callback parses `Merge feature/SPEC-ID:`                      | Task 2          | ✓      |
| 4 | gate_logic.match_subject parity                               | Tasks 1 + 2     | ✓      |
| 5 | TECH-177 anti-body invariant preserved                        | Tests           | ✓      |
| 6 | end-to-end: blocked spec stays done after fix landing         | Integration test| ✓      |
