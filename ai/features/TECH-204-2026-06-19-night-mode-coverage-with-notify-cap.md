# Feature: [TECH-204] night-mode coverage (DB-all, notify medium+ with cap)

**Priority:** P1 | **Date:** 2026-06-19

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).

## Why

The nightly auto-audit (`/audit night` via `night-reviewer.sh`) is the
unattended safety net: it runs across all VPS projects and writes findings
straight to SQLite + Telegram (Hermes) with **no downstream human or LLM
filter**. Its prompt (`skills/audit/night-mode.md`) currently hard-gates:
`Only include findings with confidence >= medium`. Per the Opus 4.8 prompting
guide (`memory/reference_opus-4-8-prompting-guide.md`), 4.8 obeys this bar more
literally than 4.7, so real-but-uncertain bugs are silently never persisted —
and because nobody reviews the discards, the loss is invisible.

But unlike bughunt personas (which have a validator downstream — see TECH-201),
night-mode has nothing after it. Pure coverage would flood the founder's
Telegram with low-confidence noise at 3 AM (devil finding A-2, Blocker:
`event_writer.py` sends one notification per new finding, no batching, no cap).

**Decision (founder, 2026-06-19): DB-all, notify-only-medium+ with cap.**
Persist EVERY finding to SQLite tagged with confidence (recall preserved, low
not lost), but send to Hermes/Telegram only `confidence >= medium`, capped at
~10 per run with a summary line for the remainder.

## Context

- `night-mode.md` self-debate ("argue FOR and AGAINST") is good — keep it as a
  **labeling** step (sets confidence), not a **gating** step.
- `night-reviewer.sh` dedups via `INSERT OR IGNORE` on
  `sha256(project_id + file + issue_type)` and notifies per new finding.
- Confirm whether `db.py save-finding` + schema already store a `confidence`
  column; if not, add it (Git-First migration only — never apply directly).
- Diff vs template night-mode.md is a single line (`event_writer.py` vs
  `notify.py`) — keep that difference, sync the rest.

---

## Scope
**In scope:**
- `night-mode.md` (root + template): change confidence from gate to label;
  emit ALL findings tagged `high|medium|low`; exclude only PROVEN non-issues
  (AGAINST argument proves it is correct behavior, not merely uncertain).
- `night-reviewer.sh`: persist all findings to DB; send Hermes notifications
  only for `confidence >= medium`; cap notifications at `MAX_HERMES_PER_RUN`
  (default 10) + one summary line ("+N more findings, see DB").
- If `confidence` not yet persisted: add column via `schema.sql` migration +
  `db.py save-finding` accepts confidence (Git-First).

**Out of scope:**
- bughunt personas / coroner / review (TECH-201).
- Changing the self-debate prompt structure (keep it).
- Batching redesign of `event_writer.py` (only a count cap in the sh loop).

---

## Impact Tree Analysis

### Step 1: UP — who reads night findings?
- Founder via Telegram (Hermes), and the SQLite `night_findings` table
  (operator/Hermes queries). Cap affects only the Telegram path.

### Step 2: DOWN — what does night-reviewer depend on?
- `db.py` (save-finding / get-new-findings CLI), `event_writer.py` (notify),
  `claude` CLI output JSON (findings array, now must carry `confidence`).

### Step 3: BY TERM
- `grep -rn "confidence >= medium\|confidence: high.*medium" .claude/skills/audit template/.claude/skills/audit`
- `grep -n "save-finding\|get-new-findings\|event_writer" scripts/vps/night-reviewer.sh`

### Step 4: CHECKLIST
- [ ] `scripts/vps/schema.sql` — confidence column (if missing).
- [ ] `db.py` save-finding signature — confidence param.
- [ ] Migration is Git-First (CI applies, never direct).
- [ ] Both night-mode.md copies edited.

### Verification
- [ ] DB receives low-confidence rows; Telegram receives only medium+ ≤ cap.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `.claude/skills/audit/night-mode.md` — confidence as label not gate (modify)
- `template/.claude/skills/audit/night-mode.md` — sync (modify)
- `scripts/vps/night-reviewer.sh` — persist all, notify medium+ with cap (modify)
- `scripts/vps/db.py` — save-finding accepts/stores confidence (modify if needed)
- `scripts/vps/schema.sql` — night_findings.confidence column (modify if missing)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps) + audit skill.
**Cross-cutting:** Errors (shell `set -euo pipefail`), SQL via `python3 db.py`
parameterized only (ADR-017 — never shell-interpolate SQL).
**Data model:** `night_findings` table (+ confidence column).

---

## Historical Risks

<!-- lessons-binding v1 -->

none (no `ai/lessons/` bank). Relevant prior art: ADR-017 (no shell SQL),
shell-safety rules in architecture.md.

---

## Approaches

### Approach 1: DB-all, notify-medium+ with cap (SELECTED)
**Summary:** Persist everything tagged; Telegram only medium+ capped at 10.
**Pros:** Full recall in DB; founder not flooded; reversible.
**Cons:** Two-tier logic (persist vs notify) adds a branch in the sh loop.

### Approach 2: Pure coverage + cap only
**Cons:** Low-confidence still hits Telegram up to cap → cry-wolf risk.

### Approach 3: Leave as-is
**Cons:** Keeps the 4.8 recall regression (the whole reason for this spec).

### Selected: 1
**Rationale:** Preserves recall where it is free (DB) and spends the scarce
resource (founder attention) only on confident findings, bounded by a cap.

---

## Design

### night-mode.md (both copies)
- `:37` `**Rule:** Only include findings with confidence >= medium.` →
  "Rule: emit EVERY finding tagged with confidence (high|medium|low). The
  self-debate sets the confidence label; it MUST NOT exclude a candidate.
  Exclude only if the AGAINST argument proves it is not a defect at all
  (i.e. the 'bug' is correct behavior), not merely uncertain."
- `:104` `CONFIDENCE: Only include if confidence >= medium` → "CONFIDENCE: tag
  every finding; emit all; exclude only proven non-issues."
- `:64` field-rule table: confidence values `high, medium` → `high, medium, low`;
  "Low confidence = excluded" → "Low confidence = retained in DB, not notified".

### night-reviewer.sh
- For each finding from `claude` JSON: always `db.py save-finding ...
  --confidence "$conf"` (persist all).
- Notification loop over `get-new-findings`: filter to `confidence in
  (high, medium)`; emit at most `MAX_HERMES_PER_RUN` (default 10, env-overridable)
  `event_writer.py` calls; if more remain, send ONE summary line
  ("+N more findings (incl. low-confidence), see night_findings DB").
- Keep `set -euo pipefail`, quote all vars, SQL only via `db.py`.

### db.py / schema.sql (only if confidence not already stored)
- `night_findings` add `confidence TEXT DEFAULT 'medium'`.
- `save-finding` CLI accepts `--confidence`.
- Migration Git-First (CI applies).

---

## Implementation Plan

### Task 1: Confirm/extend confidence persistence
**Type:** migrate
**Files:** `scripts/vps/schema.sql`, `scripts/vps/db.py`
**Acceptance:** `night_findings` has a `confidence` column; `db.py save-finding`
accepts `--confidence`; if column already existed, no-op + note in log.

### Task 2: night-mode.md confidence as label (2 files)
**Type:** code
**Files:** `.claude/skills/audit/night-mode.md`, `template/.claude/skills/audit/night-mode.md`
**Acceptance:** no "Only include if confidence >= medium"; emits all tagged;
excludes only proven non-issues; field table allows `low`.

### Task 3: night-reviewer.sh persist-all + notify-cap
**Type:** code
**Files:** `scripts/vps/night-reviewer.sh`
**Acceptance:** all findings saved with confidence; notifications only medium+,
≤ MAX_HERMES_PER_RUN, with summary remainder; shell-safety preserved.

### Execution Order
1 → 2 → 3

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | gate removed | `grep -rn "Only include.*confidence >= medium\|Only include if confidence" .claude/skills/audit template/.claude/skills/audit` | 0 matches | deterministic | guide | P0 |
| EC-2 | low retained in field rule | `grep -n "low" .claude/skills/audit/night-mode.md` (confidence row) | present | deterministic | design | P1 |
| EC-3 | cap constant present | `grep -n "MAX_HERMES_PER_RUN" scripts/vps/night-reviewer.sh` | ≥1 | deterministic | A-2 fix | P0 |
| EC-4 | shell safety intact | `grep -n "set -euo pipefail" scripts/vps/night-reviewer.sh` | present | deterministic | shell rules | P0 |
| EC-5 | confidence column | `python3 scripts/vps/db.py --help` or schema grep `confidence` in night_findings | present | deterministic | design | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-6 | tmp DB (DB_PATH=/tmp), 12 findings (3 low) | run save-finding for all + notify filter | 12 rows in DB, ≤10 notify calls, low excluded from notify | integration | A-2 | P0 |

### Coverage Summary
- Deterministic: 5 | Integration: 1 | LLM-Judge: 0 | Total: 6 (min 3) ✓

### TDD Order
1. EC-6 integration test (DB_PATH=/tmp) → implement → pass
2. EC-1..EC-5 static checks

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | sh parses | `bash -n scripts/vps/night-reviewer.sh` | exit 0 | 10s |
| AV-S2 | db.py imports | `python3 -c "import sys;sys.path.insert(0,'scripts/vps');import db"` | exit 0 | 10s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | persist-all, notify-cap | `DB_PATH=/tmp/nm_test.db` | save 12 findings (3 low), run notify filter | 12 saved, notify ≤10, 0 low notified |

### Verify Command

```bash
bash -n scripts/vps/night-reviewer.sh && echo "sh OK"
DB_PATH=/tmp/nm_test_$$.db python3 -c "import sys;sys.path.insert(0,'scripts/vps');import db; print('db OK')"
grep -n "MAX_HERMES_PER_RUN" scripts/vps/night-reviewer.sh
grep -rn "Only include if confidence" .claude/skills/audit template/.claude/skills/audit || echo "OK: gate removed"
rm -f /tmp/nm_test_*.db
```

> **Note:** local DB tests MUST use `DB_PATH=/tmp/...` — never the prod DB
> (opens circuit-breaker). See memory feedback `callback-test-db-path`.

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] All findings persisted to DB with confidence label
- [ ] Telegram notifications only confidence>=medium, capped + summary
- [ ] night-mode.md (both) emits all, gate removed

### Tests
- [ ] EC-1..EC-6 pass (EC-6 with DB_PATH=/tmp)
- [ ] `bash -n` clean

### Technical
- [ ] SQL only via parameterized db.py (ADR-017)
- [ ] Migration Git-First (no direct apply)
- [ ] root/template night-mode.md parity (except the notify.py/event_writer.py line)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
