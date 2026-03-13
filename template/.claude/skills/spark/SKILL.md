---
name: spark
description: Feature specification and research agent. Multi-agent with 4 scouts. Creates specs in ai/features/.
---

# Spark v2 — Multi-Agent Specification

Transforms raw ideas into specs via 4 parallel scouts + research + structured dialogue.

**Activation:** `spark`, `spark quick`, `spark deep`

## When to Use
- New feature, user flow change, architecture decision
- New tool or prompt modification
- **Bug fix** — after diagnosing cause, before fix

**Don't use:** Hotfixes <5 LOC (fix directly), pure refactoring without spec

## v2 Changes
- **Multi-agent:** 4 scouts (external, codebase, patterns, devil) replace single-agent research
- **Blueprint constraint:** If `ai/blueprint/system-blueprint/` exists, Spark works WITHIN it
- **Tests mandatory:** Every spec must have ## Tests section (min 3 test cases)
- **Blueprint Reference:** New section linking spec to system blueprint
- **Auto-decide:** Simple features skip human approval
- **Escalation to Architect:** Technical architecture questions → `/architect`, not human
- **Upstream reflect:** After spec, write signals to `ai/reflect/upstream-signals.md`

## Principles
1. **READ-ONLY MODE** — Spark NEVER modifies files (except creating spec in `ai/features/` and `ai/diary/`)
2. **AUTO-HANDOFF** — After spec is ready, auto-handoff to autopilot (no manual "plan" step)
3. **Research-First** — 4 parallel scouts before designing
4. **AI-First** — Can we solve via prompt change?
5. **Socratic Dialogue** — Ask 5-7 deep questions before designing (human-initiated features)
6. **YAGNI** — Only what's necessary
7. **Explicit Allowlist** — Spec must list ONLY files that can be modified
8. **Learn from Corrections** — Auto-capture user corrections to diary
9. **Blueprint Compliance** — All decisions within System Blueprint constraints

## Status Ownership

**See CLAUDE.md#Task-Statuses** for canonical status definitions.

**Key point:** Spark creates specs in `draft` status. Human approves via Telegram → `queued`.
Orchestrator manages the `draft → queued` transition. Spark NEVER sets `queued` directly.

---

## Headless Mode

When running from orchestrator (automated pipeline), Spark detects headless context:

**Detection:** prompt contains `[headless]` marker OR `Source: council|qa|architect|bughunt|reflect`

**Behavior in headless mode:**
- DO NOT ask Socratic clarifying questions — all information is already in the prompt
- If `Context:` field present — READ the linked document for full context before designing
- If data is insufficient — make a reasonable decision independently or escalate via `/council`
- PRESERVE ability to invoke council, scout, and other skills when genuinely needed
- Create spec in `draft` status (orchestrator handles approval via Telegram)

**Behavior in interactive mode (default):**
- Normal Socratic dialogue, questions, user interaction
- Create spec in `draft` status (user approves via Telegram or directly)

---

## Mode Detection

Spark operates in three modes:

| Trigger | Mode | Read Next |
|---------|------|-----------|
| "new feature", "add", "want", "create feature", "create spec", "write specification", "make feature" | **Feature Mode** | `feature-mode.md` |
| "bug", "error", "crashes", "doesn't work" (simple, <5 files) | **Quick Bug Mode** | `bug-mode.md` |
| "bug hunt", "deep analysis", complex bug (>5 files), explicit request | **→ /bughunt** | Redirect to standalone skill |

**Bug mode selection:** Start with Quick Bug. If 5 Whys reveals systemic issues → redirect to `/bughunt` standalone skill.

## Modules

| Module | When to Read | Content |
|--------|--------------|---------|
| `feature-mode.md` | Mode = Feature | Socratic Dialogue + research templates + spec template |
| `bug-mode.md` | Mode = Bug (Quick or Hunt) | Quick: 5 Whys. Hunt: multi-agent pipeline → report + grouped standalone specs |
| `completion.md` | After spec created | ID protocol, backlog, commit, handoff |

**Flow:**
```
Feature:    SKILL.md → feature-mode.md → completion.md
Quick Bug:  SKILL.md → bug-mode.md (Quick) → completion.md
Bug Hunt:   SKILL.md → bug-mode.md (Hunt) → completion.md
```

---

## STRICT RULES

**During Spark phase:**
- READ files — allowed
- SEARCH/GREP — allowed
- CREATE spec file in `ai/features/` — allowed
- WRITE to `ai/diary/` — allowed (corrections capture)
- MODIFY any other file — **FORBIDDEN**

**If task is not suitable for Spark:**
- Hotfix <5 LOC → fix directly without spec
- Pure refactoring without user request → ask user first

---

## Auto-Capture Corrections (MANDATORY)

When user corrects you during Spark dialogue — capture the learning!

**Detection:** User says something that contradicts/corrects your assumption

**Action:**
1. Acknowledge: "Got it, noted: [brief rule]"
2. Append to `ai/diary/corrections.md`:
```markdown
## YYYY-MM-DD: During TYPE-XXX

**Context:** [what we were discussing]
**I proposed:** [what I suggested]
**User corrected:** [what user said]
**Why:** [reason if given]
**Rule:** [generalized learning in imperative form]
```

**Examples of corrections to capture:**
- "No, that's not how it works for us" → capture how it actually works
- "This is too complex, make it simpler" → capture simplicity preference
- "Always use X instead of Y" → capture tool/pattern preference
- "This already exists in Z" → capture existing solution location

**Goal:** Build project memory. Same mistakes won't repeat.

---

## LLM-Friendly Architecture Checks

**See CLAUDE.md#Forbidden-CI-enforced and CLAUDE.md#Structure** for architecture rules.

Quick checklist before creating spec:
- Files < 400 LOC (600 for tests)
- New code in `src/domains/` or `src/infra/`, NOT legacy folders
- Max 5 exports per `__init__.py`
- Imports follow: shared → infra → domains → api

---

## Output

See `completion.md` for output format and handoff rules.

---

## Notification Output Format

Your final JSON `result_preview` is sent to the user via Telegram. Keep it concise:

```
{1-2 sentence description of what the spec proposes}
Задач: {N}
```

**BAD:** "Все 4 скаута завершились. Спека обновлена с учётом рекомендаций..."
**GOOD:** "Кнопки управления кампаниями: отмена, пауза, удаление по статусу. Задач: 3"
