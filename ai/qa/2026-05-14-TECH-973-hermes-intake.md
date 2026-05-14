## TECH-973 QA — Hermes intake contract

**Spec status:** `queued` (не `done`), но артефакты частично созданы — провёл verification против Acceptance Criteria.

### Результат: 5 проверок — 2 ✓, 3 ✗

| ID | Check | Result |
|----|-------|--------|
| AV-S1 | `ai/inbox/README.md` exists | ✓ PASS |
| AV-F1 | `pytest -k scan_inbox` (7 tests) | ✓ PASS |
| EC-4 | `grep -rn "OpenClaw" .claude/` = 0 | ✗ FAIL — 10 hits в 4 файлах |
| Task 2 | ADR-022 в `architecture.md` | ✗ FAIL — нет ADR-022, есть только ADR-021 |
| README↔ADR | README ссылается на ADR-022 | ✗ FAIL — битая ссылка (ADR-022 не существует) |

---

### F1: OpenClaw → Hermes rename не выполнен (Major)

**Expected:** `grep -rn "OpenClaw" .claude/` = 0 (Task 3 acceptance, EC-4).
**Actual:** 10 mentions в 4 файлах:
- `.claude/skills/reflect/SKILL.md` — 6 mentions (lines 110, 131, 169, 178, 179, 182)
- `.claude/skills/audit/night-mode.md` — 1 mention (line 91)
- `.claude/skills/bughunt/completion.md` — 3 mentions (lines 10, 22, 60)
- `.claude/rules/dependencies.md` — 1 mention (line 191, `notify() — send OpenClaw event`)

**User impact:** агенты при context-load читают «OpenClaw», в репо реальность называется Hermes — разъезд языка.

### F2: ADR-022 не добавлен в architecture.md (Major)

**Expected:** Task 2 — добавить ADR-022 «Hermes intake supervisor».
**Actual:** в `.claude/rules/architecture.md` есть только ADR-021 (`Hermes intake gate`, TECH-181). ADR-022 отсутствует.
**Hint:** README.md уже ссылается на ADR-022 (строки 108, 110) — нужно либо добавить ADR-022, либо переписать README на ADR-021.

### F3: Битая внутренняя ссылка в `ai/inbox/README.md` (Minor)

`ai/inbox/README.md:110` указывает на несуществующий ADR-022. Следствие F2.

---

### Что работает ✓

- `ai/inbox/README.md` создан, содержит полную таблицу из 7 статусов, lifecycle-диаграмму, инварианты «Hermes — единственный writer queued», ссылку на TECH-181 и `scan_inbox` regex (соответствует Design + EC-5).
- 7 regression-тестов `scan_inbox` зелёные (включая `test_scan_inbox_ignores_draft`, `test_scan_inbox_ignores_clarifying_stale_rejected`, `test_scan_inbox_dispatches_queued`, `test_scan_inbox_ignores_legacy_new`, `test_scan_inbox_no_status_field`) — покрывает EC-1, EC-2, EC-3.
- Hard gate работает машинно (TECH-181 уже задеплоен).

---

### Recommendation

Спека `queued` — корректно, она ещё не отдана автопилоту целиком. Из 4 задач закрыты: Task 1 (README), Task 4 (тесты). Остаются Task 2 (ADR-022) и Task 3 (rename 4 файлов). После их выполнения спека пройдёт DoD.
