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
