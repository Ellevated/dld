# `ai/inbox/` — Intake SSOT

Single source of truth for **intake file status lifecycle**.

`ai/inbox/` is the only entry point between the founder's stream of consciousness
(Telegram, voice notes, ad-hoc thoughts) and the AI pipeline (Spark → autopilot).
This directory is supervised by **Hermes** (the conversational supervisor agent,
formerly known as "OpenClaw").

> **Scope of this document:** statuses of *intake files in `ai/inbox/`*.
> Do **not** confuse with **backlog spec** statuses
> (`draft`/`queued`/`in_progress`/`blocked`/`resumed`/`done`) —
> those live in `ai/backlog.md` / `ai/features/*.md` and are validated by
> `_VALID_STATUSES` in `scripts/vps/callback.py:417`.

---

## Status lifecycle

Every file in `ai/inbox/*.md` has exactly one `**Status:**` field.
The orchestrator (`scan_inbox()` in `scripts/vps/orchestrator.py:315`)
dispatches **only `queued`** to Spark — every other status is ignored.

| Status | Written by | Eligible for `scan_inbox` dispatch? | Meaning |
|--------|-----------|-------------------------------------|---------|
| `draft` | author / Telegram bridge / any source | ❌ | Raw thought, unstructured idea, not yet reviewed by Hermes. |
| `clarifying` | Hermes | ❌ | Hermes has asked Oleg a clarifying question, awaiting answer. |
| `stale` | Hermes | ❌ | Idea no longer relevant; archive candidate. |
| `rejected` | Hermes | ❌ | Oleg said "no"; do not process. |
| `queued` | **only Hermes** | ✅ | Business-complete brief; ready for Spark. |
| `processing` | orchestrator (`scan_inbox`) | — | Already handed off to Spark/autopilot. |
| `done` | autopilot / callback | — | Item converted into a spec or otherwise closed. |

**Hard gate:** the regex in `scan_inbox` is `\*\*Status:\*\*\s*queued` —
literally only `queued` triggers dispatch.
Legacy statuses (`new`, `processed`, etc.) are silently ignored. Clean break,
no auto-migration (see TECH-181).

---

## Who writes what — invariants

1. **Hermes is the only writer of `queued`** in `ai/inbox/`.
   Every other source writes `Status: draft` and lets Hermes decide.
2. **Reflect and QA do not self-loop into `queued`.**
   - `reflect` writes its findings to `ai/reflect/findings-*.md`
     (see `.claude/skills/reflect/SKILL.md` step 5).
   - QA writes reports to `ai/qa/*.md`.
   - Hermes reviews those artifacts later and **may** create an inbox item from them
     — but never as `queued` without an explicit Oleg sign-off.
3. **Autopilot does not write to `ai/inbox/` at all.**
   Post-mortems and learnings go to `ai/diary/` or feed reflect via `ai/reflect/`.
4. **Orchestrator does not change semantic status.**
   `scan_inbox` flips `queued → processing` and moves the file to
   `ai/inbox/done/` — purely a state machine of the file itself, not a
   business decision.

---

## File format

```markdown
# Title — one line

**Status:** draft
**Source:** telegram | qa | reflect | autopilot | manual
**Route:** spark            # optional, defaults to spark
**Provider:** claude | codex # optional
**Context:** TECH-NNN        # optional

Free-form body. Hermes will tighten this into a brief before promoting to `queued`.
```

The orchestrator parses these fields via `_parse_inbox_file` in
`scripts/vps/orchestrator.py`.

---

## Lifecycle diagram

```
                ┌────────────┐
 Telegram ─────▶│            │
 reflect  ─────▶│   draft    │──── Hermes asks ────▶  clarifying
 QA       ─────▶│            │                              │
                └─────┬──────┘                              │
                      │                                     ▼
                      │                          (Oleg answers / silence)
                      │                                     │
                      │       Hermes decides                │
                      ▼                                     │
                ┌────────────┐    Hermes ─▶  rejected       │
                │  Hermes    │    Hermes ─▶  stale          │
                │  review    │◀────────────────────────────┘
                └─────┬──────┘
                      │ Hermes promotes
                      ▼
                ┌────────────┐
                │   queued   │── scan_inbox ─▶  processing  ─▶  done
                └────────────┘     (orchestrator state machine only)
```

---

## Related

- **TECH-181** — added the `scan_inbox` hard gate (orchestrator side).
- **TECH-184** — this document + ADR-022 (Hermes-side contract).
- **ADR-021** (`.claude/rules/architecture.md`) — Hermes intake gate.
- **ADR-022** (`.claude/rules/architecture.md`) — Hermes is the only writer of `queued`.
- `scripts/vps/orchestrator.py:315` — `scan_inbox()` implementation.
- `scripts/vps/tests/test_orchestrator.py` — regression suite.
