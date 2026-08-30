# Upstream Signals from Architect

**Date:** 2026-02-28
**Source:** Architect Board (8 personas + synthesis)
**Architecture:** Alternative B — Domain-Pure

---

## Signals for Board (target=board)

### SIGNAL-001: Google OAuth Verification is Critical Path
**Severity:** Critical
**Detail:** Google OAuth App Verification takes 4-6 weeks external review. Must submit day 31 of Phase 2. Blocks public launch (>100 users). Requires privacy policy, homepage, demo video, security questionnaire.
**Recommendation:** Board should add this to Phase 2 timeline. Privacy policy must be ready by day 30. Testing mode (100 user cap) available before verification.

### SIGNAL-002: Pricing Tier Task Definition Needed
**Severity:** High
**Detail:** Board says "500 tasks/workspace/month for Solo." Architect needs precise definition: is 1 briefing = 1 task? Or does each source fetch count? Usage cap enforcement depends on this.
**Recommendation:** Board should define: 1 briefing compilation = 1 task (recommended by Data Architect).

### SIGNAL-003: Multi-Workspace Priority Scope
**Severity:** Medium
**Detail:** Pro tier has 3 workspaces. Are priorities per-workspace or per-user? If per-workspace, different workspaces can have different priorities (personal vs work). If per-user, priorities are shared.
**Recommendation:** Board should decide. Architect recommends per-workspace (different contexts of use).

### SIGNAL-004: Degraded Briefing Policy
**Severity:** Medium
**Detail:** When a source is unhealthy (e.g., Gmail OAuth expired), should briefing compile without that source (degraded) or block until all sources healthy?
**Recommendation:** Architect implements degraded delivery (partial briefing > no briefing). Board should confirm this is the right UX.

---

## Signals for Spark (target=spark)

### SIGNAL-005: Onboarding Flow is Critical for Conversion
**Detail:** Sub-10-minute time-to-first-value requires: (1) Clerk signup (2 min), (2) Add 1 source — RSS or HN, no OAuth (1 min), (3) Set priorities (2 min), (4) Trigger first briefing (instant). Gmail/Calendar as day-2 upgrades (OAuth friction).
**Priority:** First feature spec should be onboarding flow.

### SIGNAL-006: Telegram Bot Commands
**Detail:** Bot needs: /start (connect channel), /stop (disconnect), /briefing (manual trigger), /settings (show prefs). Each command maps to an API endpoint.

### SIGNAL-007: Feedback Capture UI
**Detail:** For behavioral memory to work, briefings must capture engagement: opened, item_clicked, item_dismissed, full_read, skipped. Telegram inline keyboards recommended. This is the compound loop that creates switching cost.

---

## Process Signals (target=architect-next)

### SIGNAL-008: Cross-Critique Confirmed Data Architect Dominance
**Detail:** Data Architect (Martin) ranked best by 5 of 7 personas. The data model decisions (append-only ledger, two-table memory, structured JSON) were the most impactful.
**Lesson:** In future Architect sessions, give Data persona more explicit agenda weight.

### SIGNAL-009: Devil Found 5 Contradictions, All Resolved
**Detail:** Evaporating Cloud technique resolved all 5 contradictions (domain count, scheduler, storage, OAuth ownership, tool calls). No unresolved tensions in final architecture.
**Lesson:** Devil is most valuable when contradictions are NAMED and given formal resolution structure.

### SIGNAL-010: "Agent-runtime" as Context was Unanimously Rejected
**Detail:** Domain persona identified "agent-runtime" as a technical term masquerading as domain concept. All other personas agreed. LLM execution is infrastructure inside Briefing context.
**Lesson:** Always check Business Blueprint domain names against DDD linguistic test.

---

## SIGNAL-2026-05-23-2300

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | ARCH-190 (gate-daemon shadow, Wave 1 MP-001) |
| Target | architect |
| Type | gap |
| Severity | warning |

### Message

`ai/architect/migration-path.md` MP-001 description (lines 39-59) characterizes gate-daemon's logic as "Single rule gate: `git log origin/develop --grep \"SPEC-ID\"` (touching allowed_files)." This characterization, taken literally, would re-introduce the TECH-177 incident class (body/trailer mentions of a SPEC-ID falsely marking it done).

The migration-path itself is correct in spirit — it says gate_logic.py contains `find_implementation_commit` extracted from callback — but the "single rule" framing is mis-leading enough that a future operator/agent reading only the architectural summary could ship the regression.

### Evidence

- Devil scout Attack 2 + Attack 10: bare `--grep` matches commit message body, not subject. Pre-TECH-177 behavior.
- Callback today uses two-step approach: `git log --pretty=%h%x00%s -- <paths>` (path filter), then Python `_subject_implements(subject, spec_id)` (subject-only). See `callback.py:734-775` (_is_done_on_develop) + `callback.py:673-711` (_subject_implements).
- ARCH-190 spec explicitly REJECTS bare `--grep` and mandates `find_implementation_commit` extract preserve the two-step approach (Task 1 acceptance criterion + EC-1, EC-3, EC-9 tests).

### Suggested Action

Architect updates `migration-path.md` MP-001 description to replace:
> "Single rule: `git log origin/develop --grep \"SPEC-ID\"` (touching allowed_files)."

with:
> "Single-rule gate (preserved from callback): path-filter via `git log -- <allowed_files>`, then Python subject-only match via `_subject_implements` (extracted to `gate_logic.match_subject`). NOT bare `--grep SPEC-ID` — that matches body/trailer mentions (TECH-177 incident class)."

Also update the "8-rule redesign" reference: `callback._spec_has_merged_implementation` was renamed to `_is_done_on_develop` in commit `cefaa55` (2026-05-21). Migration docs should use the current name to avoid future agents grepping for a function that no longer exists.

---

## SIGNAL-2026-05-23-2300-process

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | ARCH-190 |
| Target | spark |
| Type | meta-observation |
| Severity | info |

### Message

Devil scout returned its analysis as a `result` message (text), not as a written file at the prompted output path. The other 3 scouts wrote files correctly. ADR-007 (caller-writes fallback) handled this — facilitator wrote `research-devil.md` from the response text — but this is the 2nd time in 3 sessions Devil specifically has failed file-write.

### Suggested Action

`.claude/agents/spark/devil.md` could benefit from a more explicit "MUST use Write tool — text response alone is treated as DATA LOSS" reminder, mirroring the SUBAGENT MUST USE WRITE TOOL pattern from `spark/completion.md:298`. Low priority — fallback works — but if Devil drifts further, the meta-cost compounds.


---

### SIGNAL-2026-05-25-1340

- **Source:** autopilot (ARCH-193)
- **Target:** spark
- **Type:** missing_rule
- **Message:** Spec author listed `.claude/hooks/pre-commit-lifecycle-guard.mjs` in Allowed Files but missed `template/.claude/hooks/pre-commit-lifecycle-guard.mjs`. Coder correctly synced both copies per template-sync.md, forcing the autopilot operator to update Allowed Files mid-flow. Three other `template/.claude/*` mirrors WERE listed (coder.md, finishing.md, autopilot-git.md) — the omission was an oversight, not intent.
- **Evidence:** ai/features/ARCH-193-*.md Allowed Files (before edit) vs `.claude/rules/template-sync.md` mandate
- **Suggested Rule for /spark:** When a `.claude/<path>` file is added to Allowed Files AND a matching `template/.claude/<path>` exists, automatically include the template mirror. Could be enforced via Phase 5.5 SSOT lint or facilitator checklist.

### SIGNAL-2026-05-25-1340-2

- **Source:** autopilot (ARCH-193 Task 9)
- **Target:** spec-reviewer agent
- **Type:** prompt_gap
- **Message:** Spec Reviewer flagged Test 8 as "needs_implementation — event_writer.notify not verified" but missed that spec line 577 explicitly grants the structural-only fallback: "Practical approach: directly call lifecycle.write_lifecycle(done→blocked) ... full integration is overkill". Reviewer matched the test name + first sentence and missed the inline scope relaxation.
- **Evidence:** spec ai/features/ARCH-193-*.md line 577; spec-reviewer agent prompt in `.claude/agents/spec-reviewer.md`
- **Suggested Rule:** Spec-reviewer prompt should instruct: "Read the FULL test description in the spec — especially watch for 'Practical approach' / 'overkill' / 'simplification' phrases that scope down the requirement. Do not flag deviation if the spec itself authorized it."

## SIGNAL-2026-06-06-0001

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | TECH-197 |
| Target | architect |
| Type | gap |
| Severity | info |

### Message
Два независимых guard'а проверяют "impl merged on develop": `callback._is_done_on_develop` (origin/develop, bool) и `gate_logic.find_implementation_commit` (shadow gate-daemon, возвращает SHA). Дублирование логики subject-match + Allowed Files. Кандидат на унификацию в общий модуль после стабилизации TECH-197.

### Evidence
research-codebase.md: gate_logic.py:251 — переименованный _is_done_on_develop для shadow daemon (FF-09 clean separation, не импортирует callback). callback.py:736.

### Suggested Action
После TECH-197 — отдельный TECH на извлечение общего `is_implementation_on_develop(repo, spec_id, allowed) -> SHA|None`, используемого обоими (callback + gate-daemon), single source of subject/path matching.

### Process note (local)
4 scout'а сошлись на B (gate fetch-retry) + A (push-before-signal), но НЕДООЦЕНИЛИ timeout-interrupted-push подслучай: при timeout impl остаётся в LOCAL develop (autopilot убит между merge и push origin), и fetch-retry бесполезен — нечего fetch'ить. Push-local-before-gate выведен из reflog-форензики (BUG-1117: impl вошёл в origin только через callback lifecycle push, 13s после gate), НЕ из scout-research. Урок: для timing/race-багов git-форензика (reflog, commit timing vs gate timing) сильнее scout-research.

---

## SIGNAL-2026-06-13-TECH198

| Field | Value |
|-------|-------|
| Source | autopilot (TECH-198) |
| Target | architect |
| Type | follow-up |
| Severity | low |

### Message

`claude-runner.py` per-session heartbeat filename uses `ts_label = time.strftime("%Y%m%d-%H%M%S")` — 1-second resolution. Two same-project sessions starting in the same second collide on the heartbeat filename (second overwrites first). The reaper mitigates this via `started_at` cross-check + fail-open on ambiguity, but a future improvement should append pueue task ID or PID to `ts_label` for guaranteed uniqueness. Low priority — collision requires same-project, same-second start which is gated by the slot system (max 2 concurrent claude slots).

### Suggested Action

Add a follow-up TECH spec to change `ts_label` format from `%Y%m%d-%H%M%S` to `%Y%m%d-%H%M%S-{pueue_id}` or `%Y%m%d-%H%M%S-{pid}` in `claude-runner.py`. Coordinate with log file naming (same `ts_label` used for `.log` files).

---

### SIGNAL-2026-06-13-BUG199

- **Source:** autopilot (BUG-199 incident, awardybot pueue #574)
- **Target:** architect
- **Type:** gap
- **Message:** The autopilot execution contract has a dual-layer defense-in-depth gap: (1) the prompt's loop-mode EXIT directive was soft enough that the model continued working after spec completion, and (2) the only hard enforcement layer (pre-edit.mjs Allowed Files hook) degrades open on develop because the orchestrator did not pin the spec path via env var for autopilot dispatch (only inbox dispatch was wired). Both layers failed simultaneously, allowing out-of-scope commits to flow to origin/develop.
- **Evidence:** Commit `5196867e` (awardybot, 12:54:23 2026-06-13): `flows/cb-wb-end.yaml` + `scripts/create_flow_campaign.py` + `tests/architecture/test_flows_artefacts_packaged.py` — none in FTR-1185 Allowed Files. Pre-edit hook returned allow because `inferSpecFromBranch()` returns null on develop branch.
- **Fix applied:** BUG-199: (A) HARD-GATE in SKILL.md loop-mode section, (B) orchestrator now sets CLAUDE_CURRENT_SPEC_PATH for autopilot dispatch (not just inbox), (C) callback logs WARNING on out-of-scope files.

## SIGNAL-20260619-opus48-alignment

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | TECH-201..204 |
| Target | architect |
| Type | missing_rule |
| Severity | warning |

### Message
DLD has no standing process to re-align agent/skill prompts + effort/model
config when Anthropic ships a new model + prompting guide. The 4.7→4.8 switch
(2026-06-03) silently introduced recall regressions in finding-stage gates
(bughunt/night-mode/review obeyed "be conservative" literally) and fan-out
serialization (no "single message" instruction), discovered only by an ad-hoc
audit 16 days later. ADR-005/019 were also frozen at 4.6/4.7-era rationale.

### Evidence
Opus 4.8 guide (memory/reference_opus-4-8-prompting-guide.md): literal
instruction-following + code-review harness recall trap + fewer subagents by
default + effort default=high. Audit 2026-06-19 found ~20 affected files across
both .claude/ trees; SDK effort enum (low|medium|high|max) lacks the `xhigh`
DLD uses pervasively in frontmatter.

### Suggested Action
Architect: add a lightweight "model-upgrade checklist" ritual (or extend
/upgrade) that, on each Anthropic model bump, diffs the new prompting guide
against (a) finding-stage gate prompts, (b) fan-out dispatch blocks, (c)
effort/model routing tables + ADRs. Make model-capabilities.md the SSOT mirror
of frontmatter (TECH-203 starts this).

---

## SIGNAL-20260727-spark-ARCH-209

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | ARCH-209 |
| Target | architect |
| Type | contradiction |
| Severity | info |

> **Исправлено 2026-07-27.** Первая редакция этого сигнала утверждала, что
> `callback._render_and_commit_backlog` стирает `AFTER`-маркеры на каждом цикле, и
> ссылалась на BUG-217. Это неверно: у функции ноль call-sites, вызов удалён в ARCH-196
> (см. `CHANGELOG.md:26`), а живой путь `lifecycle._atomic_write` -> `sync_status`
> сохраняет всё, кроме ячейки статуса. Проверено на коммите `ee6aaec`. BUG-217 отозвана.
> Severity понижен critical-адъяцентный -> info: дефекта нет, асимметрия есть.

### Message

Зависимости между спеками (`AFTER <ID>`) - единственное поле, чей источник истины
находится в `ai/backlog.md`, а не в `ai/lifecycle/*.yaml`. ADR-023 объявляет backlog
рендером, не SoT.

Сегодня это работает: `sync_status` бережёт всё, кроме ячейки статуса, и маркеры живут.
Но защищено это соглашением, а не тестом. Разрушительный `render_backlog.render_backlog()`
остаётся в модуле как операторский инструмент, и один его запуск сотрёт весь граф
зависимостей проекта - молча, потому что `_backlog_deps` на пустом множестве просто
вернёт "зависимостей нет" и спека уедет в диспатч раньше срока.

### Evidence

`orchestrator._backlog_deps` (`orchestrator.py:737-755`) читает `AFTER` только из строки
backlog. `render_backlog.sync_status` (`:246-273`) сохраняет остальные байты и в своём
docstring прямо перечисляет, что разрушает полная пересборка: "founder descriptions /
section structure / AFTER markers". Ни один тест не проверяет, что маркер переживает
запись статуса.

Первое живое использование механизма - ARCH-209 и TECH-216, заведённые 2026-07-27.
До этого маркеров в backlog не было ни одного за всю историю проекта, поэтому
асимметрия ни разу не проявилась.

### Suggested Action

Architect: решить, переезжает ли `after:` в `ai/lifecycle/{id}.yaml` как поле схемы -
это смена формата на 10 проектах и 197 файлах, размер ADR. Минимальная альтернатива:
регрессионный тест "AFTER переживает write_lifecycle" плюс явная запись в ADR-023, что
backlog является SoT для одного поля.

---

## SIGNAL-20260727-spark-lessons-bank

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | ARCH-209 |
| Target | architect |
| Type | gap |
| Severity | info |

### Message

Gate 7 (Historical Risks) авто-проходит во всех девяти написанных сегодня спеках, потому
что `ai/lessons/` содержит только `.gitkeep` (0 байт, 2026-05-10) — ни `index.jsonl`, ни
доменных подпапок. Секция `## Historical Risks` присутствует в каждой спеке и в каждой
пуста.

Гейт, который никогда не срабатывает, не отличим от отсутствующего гейта. При этом
дефектный след по `scripts/vps/` богат и лежит в git-истории и в docstring'ах — сегодня
его пришлось собирать вручную по каждой спеке.

### Evidence

`ls -la ai/lessons/` → только `.gitkeep`. `feature-mode.md` Gate 7: «If `ai/lessons/`
does not exist in the project → Gate 7 auto-passes». Директория существует и пуста —
формально это даже не тот случай, который описывает гейт.

### Suggested Action

Architect: либо засеять банк уроков (`/seed-lessons` существует как триггер в
`localization.md`), либо снять секцию из шаблона спеки. Пустая обязательная секция учит
её игнорировать.

---

### SIGNAL-2026-07-28-0130
- **Source:** autopilot (TECH-212)
- **Target:** spark
- **Type:** gap
- **Message:** Секция `## Design` спеки содержала нерабочий код, который был бы скопирован
  дословно, если бы планировщик не перепроверил. `get_db` — это `@contextmanager`, поэтому
  предложенный спекой делегат `db_decisions.record_decision(get_db(), ...)` передал бы в лист
  `_GeneratorContextManager` вместо `Connection`, и ни одна запись никогда бы не закоммитилась.
  Правильная форма — `with get_db(immediate=...) as conn:`. Spark пишет примеры кода в Design,
  не исполняя их; для рефакторингов с транзакциями это дорогая ошибка (тихая потеря записи).
- **Evidence:** `ai/features/TECH-212-2026-07-27-split-db-module.md:187-193` (исходный снippet)
  vs `scripts/vps/db.py:52` (`@contextmanager def get_db`)

### SIGNAL-2026-07-28-0131
- **Source:** autopilot (TECH-212)
- **Target:** spark
- **Type:** gap
- **Message:** Спека не заметила, что `immediate=True` (BEGIN IMMEDIATE) — часть контракта
  трёх выносимых функций (`clear_decisions`, `save_finding`, `update_finding_status`).
  Дословный перенос без этого флага дал бы race-condition, который не поймал бы ни один тест.
  Impact Tree в Spark смотрит на имена и импорты, но не на семантику транзакций.
- **Evidence:** `git show HEAD~4:scripts/vps/db.py:142,163,343,374` — четыре `get_db(immediate=True)`

### SIGNAL-2026-07-28-0132
- **Source:** autopilot (TECH-212)
- **Target:** spark
- **Type:** contradiction
- **Message:** Собственный критерий спеки EC-7 (`grep 'f"SELECT'` → 0 попаданий) противоречил
  её же плану «дословного переноса»: `get_projects_for_night_scan` строит
  `f"SELECT ... IN ({placeholders})"`. Дословный перенос провалил бы приёмку спеки.
  Eval Criteria пишутся отдельно от Design и не проверяются на совместимость с ним.
- **Evidence:** спека EC-7 (строка ~269) vs `git show HEAD~4:scripts/vps/db.py:527`

### SIGNAL-2026-07-28-0133
- **Source:** autopilot (TECH-212)
- **Target:** spark
- **Type:** gap
- **Message:** Оценка «делегат стоит одну строку» ошиблась в ~5 раз: 12 рукописных `def`-делегатов
  стоили бы 60-72 строки и вывели бы `db.py` на 395-407 при лимите 400 — то есть спека,
  выполненная буквально, могла не достичь собственной цели. Спасла замена на `_delegate`-фабрику
  (~30 строк, итог 373). LOC-бюджет раскола стоит считать, а не оценивать на глаз.
- **Evidence:** `ai/features/TECH-212-...md:154` («делегат — одна строка») vs `scripts/vps/db.py:373`

### SIGNAL-2026-07-28-0134
- **Source:** autopilot (TECH-212)
- **Target:** architect
- **Type:** missing_rule
- **Message:** Exa MCP исчерпал кредиты — `web_search_exa` возвращает HTTP 402. Это деградирует
  research-стек ВСЕХ агентов на этой VDS (planner, scout, spark-research, bughunt solution-architect),
  причём молча: агент просто ищет хуже и продолжает. `scripts/check-research-stack.py` существует,
  но ничто не зовёт его периодически. Ни один автопилот-прогон не сообщит об этом сам, если
  не спросить агента напрямую.
- **Evidence:** planner TECH-212 → `web_search_exa` HTTP 402; `CLAUDE.md` § «Verifying the research stack»

### SIGNAL-2026-07-28-0135
- **Source:** autopilot (TECH-212)
- **Target:** architect
- **Type:** gap
- **Message:** `ruff format --check .` красный на `develop` для 17 файлов, при этом CI-джоб
  `python-lint` делает ровно `ruff format --check .`. Значит CI-гейт форматирования либо уже
  красный, либо его никто не смотрит. Локально `ruff` вообще не установлен ни в venv, ни на PATH
  проекта (нашёлся только в `~/.local/bin`), поэтому ни один агент не проверит формат, если ему
  явно не подсказать путь. CI-parity гейт TECH-206 покрывает тесты, но не линтер.
- **Evidence:** `ruff format --check .` на develop → «17 files would be reformatted»;
  `.github/workflows/ci.yml` job `python-lint`

### SIGNAL-2026-07-28-1105
- **Source:** autopilot (BUG-218)
- **Target:** spark
- **Type:** gap
- **Message:** Спека Task 4 была материально неверна и, выполненная как написано, оставила бы
  дерево красным через две границы коммита. Три из десяти happy-path тестов
  (`test_orchestrator.py:954/989/1144`) УЖЕ патчили `write_lifecycle` как `mock_write` и
  ассертили `mock_write.assert_not_called()`. Task 2 (запись `in_progress`) ломает ровно эти
  ассерции, а Task 4 предлагал «добавить патч в стек» — патч там уже был; чинить надо было
  ассерцию, и делать это внутри Task 2, а не через два коммита. Плюс acceptance Task 4 гласил
  «ни одна ассерция не ослаблена», что заблокировало бы кодера на его же гейте.
  Корень: спека писала Impact Tree по `grep "assert result is True"` (нашла 10 строк верно),
  но не читала, что каждый из этих тестов уже делает с `write_lifecycle`. Проверка «кто
  вызывает» была, проверки «что уже замокано и что про это ассертится» — не было.
  Предлагаемое правило для Spark: если правка добавляет вызов X в продовый путь, Impact Tree
  обязан грепнуть тесты на `mock`/`patch` этого же X и перечислить существующие ассерции
  про него — они и есть то, что сломается.
- **Evidence:** `scripts/vps/tests/test_orchestrator.py:956, :991, :1146` (`mock_write.assert_not_called()`)
  против спеки § Implementation Plan Task 4 Step 1; Drift Log D1/D2/D3 в теле спеки

### SIGNAL-2026-07-28-1106
- **Source:** autopilot (BUG-218)
- **Target:** architect
- **Type:** gap
- **Message:** Корневой `tests/` красный на `develop` — 3 падения, воспроизводятся на чистом
  `origin/develop` без каких-либо правок:
  `test_callback_blocked_no_dispatch.py::test_missing_task_status_dispatches`,
  `test_callback_status_sync.py::test_ec15_operator_uncommitted_edits_in_spec_survive`,
  `test_callback_allowlist_v1.py::test_ec3_v1_marker_numbered_list_ignored`.
  CI-джоб `ci.yml` делает `pytest tests/`, то есть этот джоб на develop уже красный.
  Вместе с SIGNAL-2026-07-28-0135 (`ruff format --check` красный там же) это значит, что на
  develop красны минимум два CI-джоба, и ни один автопилот-прогон этого не замечает: gate
  автопилота исторически гонял только `scripts/vps/tests`. Пока baseline красный, «дельта
  ноль» — единственный честный критерий, но его надо считать явно, иначе следующий прогон
  либо примет чужую красноту за свою, либо спрячет свою за чужой.
  Дополнительно: `tests/integration/test_claude_runner_post_result_exception.py` не собирается
  вообще — `ModuleNotFoundError: claude_agent_sdk` (пакета нет в окружении VPS-агента), то есть
  коллекция падает целиком, если не игнорировать модуль явно.
- **Evidence:** `pytest tests/ scripts/vps/tests/` на fix/BUG-218 → 3 failed / 685 passed;
  те же три теста на `origin/develop` → 3 failed; `.github/workflows/ci.yml:90`

---
### SIGNAL-2026-07-28-1210
- **Source:** autopilot (TECH-210, цикл 2)
- **Target:** spark
- **Type:** gap
- **Message:** Один и тот же дефект авторства заблокировал TECH-210 **дважды подряд**, и
  второй раз — внутри блока, который чинил первый. Цикл 1: § Impact Tree Step 1 грепал
  только `scripts/vps/`, корневое дерево `tests/` не проверялось. Владелец снял блокер
  резолюцией от 2026-07-28 и записал правило «Impact Tree Step 1 грепает от корня
  репозитория». Но сама резолюция содержит замер-таблицу
  («`_is_done_on_develop` | 13 ссылок | **0** monkeypatch»), сделанный тем же способом —
  и он ложен: в корневом `tests/integration/` 22 `monkeypatch.setattr` на гейтовые функции
  в 5 файлах вне Allowed Files. То есть правило записали, а следующий же замер в том же
  документе сделали в нарушение правила.
  Вывод для Spark: правило «грепать от корня» недостаточно, пока оно живёт как текст в
  спеке. Замер, от которого зависит выбор подхода (сколько файлов сломается, есть ли
  monkeypatch-потребители), должен быть **воспроизводимой командой в теле спеки**, а не
  таблицей с числами. Число в таблице невозможно перепроверить, не переделав работу;
  команду — можно, за секунду.
- **Evidence:** спека `ai/features/TECH-210-2026-07-27-gate-dedup-single-source.md`
  § «✅ РЕШЕНО 2026-07-28» таблица замера vs фактический
  `grep -rn 'monkeypatch.setattr(callback, "_is_done_on_develop"' tests/` → 11 попаданий
  в 5 файлах (+11 на `_fetch_develop`); `tests/integration/test_callback_already_merged.py:151,243`

## SIGNAL-2026-08-30-arch-219

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | ARCH-219 |
| Target | architect |
| Type | gap |
| Severity | warning |

### Message
Карта «тип спеки → префикс ветки» существует только в прозе, в двух файлах, и расходится:
`worktree-setup.md:102-108` (таблица без GROWTH) и `autopilot-git.md:52-58` (bash `case`,
GROWTH падает в `task/`). В Python её нет; `orchestrator_queue.record_dispatch:328` пишет
`feature/` для всех типов. TECH-220 вводит `gate_ancestry.branch_ref_for` как единственный
источник (GROWTH → `growth/`) с меткой L-derived-4, но проза остаётся второй копией.

### Evidence
`ai/.spark/20260830-ARCH-219/research-devil.md` §Argument 1; `research-codebase.md` §Step 2.

### Suggested Action
После TECH-221 (правит обе копии промптов) — вынести таблицу в один файл, на который ссылаются
оба промпта, либо генерировать фрагмент промпта из `gate_ancestry._BRANCH_PREFIX`.

### Process signal
Бриф скаутам содержал две фактические ошибки (`_merge_confirmed` приписан `callback_sync`;
`tests/regression/test_callback_spec_corpus.py` назван корпусом subject-вердиктов) — оба
поправил codebase-скаут grep'ом. Скаут, проверяющий бриф, окупился; Verified References — рабочий гейт.
