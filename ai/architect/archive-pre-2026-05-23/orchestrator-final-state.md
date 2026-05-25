# Orchestrator Final State (North Star)

**Status:** north-star (implemented)
**Date:** 2026-03-17
**Last verified:** 2026-03-28

## Goal

Сделать оркестрацию линейной, управляемой и человеко-центричной:

- чат = обсуждение и intake
- inbox = только зрелые задачи
- spark = оформление спеки
- autopilot = реализация
- QA + Reflect = отчётные хвосты
- OpenClaw = наблюдатель, аналитик и инициатор следующего шага

---

## Core Flow

```text
Human/Tester chat
  -> OpenClaw discusses and clarifies
  -> OpenClaw writes mature item to ai/inbox/
  -> Spark (new Claude Code SDK session) converts inbox item to spec
  -> Spark writes spec to ai/features/ and backlog entry to ai/backlog.md
  -> Autopilot (new session) implements
  -> QA (new session) writes report file
  -> Reflect (new session) writes diary entries
  -> STOP
  -> OpenClaw analyzes outputs
  -> if follow-up needed: OpenClaw writes new inbox item
  -> else: OpenClaw reports completion
```

---

## Roles

### OpenClaw

Owns:
- chat discussion with humans
- clarification and scope shaping
- writing inbox items
- reading post-run artifacts
- deciding and proposing next step
- creating follow-up inbox items after analysis

Does **not**:
- implement code directly as part of orchestrator loop
- let other agents write into inbox

### Inbox

Purpose:
- queue of mature, discussion-ready tasks

Rule:
- **only OpenClaw writes to inbox**

### Spark

Runs:
- via Claude Code SDK
- every run in a fresh session

Owns:
- converting inbox item into implementation-ready spec
- writing spec to `ai/features/`
- writing backlog entry to `ai/backlog.md`

Rules:
- no extra questions if prompt explicitly says intake is complete
- no human approval step between Spark and Autopilot
- spec goes straight to executable backlog state

### Autopilot

Runs:
- via Claude Code SDK
- every run in a fresh session

Owns:
- executing approved spec from backlog
- implementation, commit, push

### QA

Runs:
- via Claude Code SDK
- every run in a fresh session

Owns:
- validating implementation
- writing result to file

Rules:
- does not write to inbox
- does not create specs
- does not trigger Spark directly

### Reflect

Runs:
- via Claude Code SDK
- every run in a fresh session

Owns:
- reviewing mistakes/patterns from the cycle
- writing conclusions to its diary

Rules:
- does not write to inbox
- does not create specs

---

## Chat Policy

In orchestrator chat:
- the owner and the tester have **equal authority**
- if either asks for a spec-worthy task and the discussion is complete, OpenClaw should prepare inbox input
- task legitimacy does not depend on who requested it

---

## Heavy Tools

Heavy tools such as:
- architect
- board
- other long-form design sessions

When used through Telegram/chat:
- OpenClaw reads their outputs
- OpenClaw distills outcomes into inbox items
- heavy tools themselves do not write to inbox directly

---

## Post-Run Behavior

### If QA passes
- QA report is saved to file
- Reflect diary is updated if relevant
- OpenClaw analyzes outputs and reports result
- cycle stops

### If QA fails
- QA report is saved to file
- OpenClaw reviews QA findings
- OpenClaw prepares ready-to-spec follow-up inbox items for Spark
- cycle resumes only through OpenClaw-managed inbox writing

### If Reflect finds useful lessons
- Reflect writes to diary
- OpenClaw may later convert those lessons into inbox items if action is justified
- Reflect never self-enqueues work

---

## Proactivity Model

OpenClaw should be proactive, but safely.

### Primary trigger
- wake/callback/event after Autopilot, QA, Reflect completion

### Safety net
- cron-based periodic check

Recommended model:
- **hybrid** = callback first, cron as fallback

This avoids both:
- missed results
- pure polling lag

---

## Required Artifacts

### Inbox
- `ai/inbox/*.md`
- written only by OpenClaw

### Spec
- `ai/features/*.md`

### Backlog
- `ai/backlog.md`

### QA output
- file-based report (exact location to standardize)

### Reflect output
- reflect diary / diary entries

---

## Invariants

1. **Only OpenClaw writes to inbox**
2. **Inbox contains only mature tasks**
3. **Spark does not ask new questions when intake is explicitly complete**
4. **There is no approval gate between Spark and Autopilot**
5. **Spark, Autopilot, QA, Reflect each run in fresh Claude Code SDK sessions**
6. **QA writes files, not inbox items**
7. **Reflect writes diary notes, not inbox items**
8. **Heavy-tool outputs are mediated by OpenClaw before entering inbox**
9. **After Autopilot -> QA -> Reflect, the cycle stops**
10. **Any new cycle starts only through OpenClaw analysis and inbox writing**

---

## Resolved Questions

| # | Question | Resolution | Where |
|---|----------|-----------|-------|
| 1 | QA report path/format | `ai/qa/{YYYY-MM-DD}-{slug}.md` | `.claude/skills/qa/SKILL.md` |
| 2 | OpenClaw artifact monitoring | `ai/openclaw/pending-events/*.json` | `scripts/vps/event_writer.py` |
| 3 | Callback/wake integration | `event_writer.wake_openclaw()` → `openclaw system event --mode now` | `scripts/vps/event_writer.py:62` |
| 4 | Spark prompt contract | `[headless]` marker + `Source:` field in prompt | `.claude/skills/spark/SKILL.md` (Headless Mode) |
| 5 | OpenClaw cycle summary | OpenClaw reads pending-events, decides format | OpenClaw bot logic |

---

## Direct Mode vs Orchestrator Mode

QA + Reflect tail is dispatched by `callback.py`, which is triggered by pueue task completion.

| Mode | How | QA + Reflect? |
|------|-----|---------------|
| **Orchestrator (VPS)** | inbox → Spark → backlog → pueue → Autopilot → pueue callback | ✅ Full tail |
| **Direct (Claude Code)** | User runs `/autopilot SPEC-ID` locally | ❌ No tail |
| **Hybrid** | User creates spec + push → orchestrator picks from backlog | ✅ Full tail |

**Direct mode** has only inline reflect (finishing.md Step 3: upstream signals).
For full QA + Reflect after direct `/autopilot`, run `/qa SPEC-ID` and `/reflect` manually.

---

## Implementation Status (2026-03-28)

| Component | File | Status |
|-----------|------|--------|
| Orchestrator poll loop | `scripts/vps/orchestrator.py` | ✅ Deployed |
| Pueue callback (QA/Reflect dispatch) | `scripts/vps/callback.py` | ✅ Fixed: slot+log+phase |
| OpenClaw event writer | `scripts/vps/event_writer.py` | ✅ Deployed |
| Agent runner (SDK) | `scripts/vps/claude-runner.py` | ✅ Agent SDK v0.1.48 |
| Provider dispatcher | `scripts/vps/run-agent.sh` | ✅ claude/codex/gemini |
| DB state management | `scripts/vps/db.py` + `schema.sql` | ✅ SQLite WAL |
| Orphan slot watchdog | `orchestrator.py:release_orphan_slots()` | ✅ BUG-162 |

### Fixes applied 2026-03-28

| Fix | Issue | Where |
|-----|-------|-------|
| Phase deadlock | QA/Reflect set `qa_pending` → stuck | `callback.py:367` — `qa-*/reflect-*` → `idle` |
| QA/Reflect invisible | No slot/log for tail tasks | `callback.py:276-297` — `try_acquire_slot` + `log_task` |
| Spark event missing | OpenClaw unaware of new specs | `callback.py:305` — added `spark` to event skills |
| resolve_label double-prefix | DB path produced `pid:pid:task` | `callback.py:65` — `startswith` guard |

---

## North Star Summary

```text
OpenClaw is the only intake writer.
Spark is the spec factory.
Autopilot is the implementation engine.
QA writes reports.
Reflect writes diary lessons.
The loop stops after reporting.
OpenClaw reads the results and decides what happens next.
```
