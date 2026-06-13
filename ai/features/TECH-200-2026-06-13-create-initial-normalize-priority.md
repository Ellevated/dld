# Feature: [TECH-200] Normalize priority case in lifecycle.create_initial

**Priority:** P2 | **Date:** 2026-06-13

> **Lifecycle state** is tracked in `ai/lifecycle/TECH-200.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.

## Why

`lifecycle.create_initial` (`lifecycle.py:434`) stores the `priority` argument **verbatim**. `render_backlog` groups specs by `PRIORITY_ORDER = ['p0','p1','p2']` (lowercase) via `d.get("priority","p1") == prio` (`render_backlog.py:~197`). When a caller passes an **uppercase** priority (`'P1'`), the spec matches no group and is **silently dropped from the rendered `ai/backlog.md`** — invisible in the human view, even though it is correctly `queued` in the lifecycle SoT and dispatchable.

This is not hypothetical: during the TECH-198/BUG-199 spec-first CAS claims (2026-06-13), a manual `create_initial(..., priority='P1', by='spark')` produced exactly this — both specs vanished from the backlog view until the priority was rewritten to lowercase. The orchestrator's own bootstrap path is immune because `orchestrator._parse_priority_kind` lowercases before calling create_initial (`orchestrator.py:482`, `.group(1).lower()`). The gap is for **any other caller** (spark CAS claim, operator helper, future tooling) that doesn't pre-lowercase.

Why it matters despite being cosmetic: the backlog view is the founder/operator's window into the queue. A spec that is queued-but-invisible reads as "lost" and invites a duplicate re-spec — the same silent-drift class TECH-195/ADR-026 closed for bootstrap status parsing. Defensive normalization at the single write primitive (`create_initial`) closes it structurally, instead of relying on every caller to remember case.

## Context

- `create_initial` signature (`lifecycle.py:434-479`): `priority: str` flows straight into `_build_yaml_content(..., priority=priority, ...)` → yaml. No validation, no normalization.
- `_parse_priority_kind` (`orchestrator.py:472-484`) already lowercases (`p1` default) — the orchestrator bootstrap path is correct; this spec aligns the primitive with that contract so all callers are safe.
- Valid priority enum is `p0`/`p1`/`p2` (lowercase) per `render_backlog.PRIORITY_ORDER` and existing lifecycle yamls (e.g. `TECH-197.yaml` → `priority: p1`).
- Related: ADR-027 (spec-first ID CAS via create_initial — the new multi-caller surface that exposed this), ADR-026 (silent-drift defensive-default principle).

---

## Scope

**In scope:**
- In `lifecycle.create_initial`, normalize `priority` to lowercase before building the yaml (e.g. `priority = (priority or "p1").strip().lower()`).
- Validate against the known enum `{p0,p1,p2}`; on an unknown value, default to `p1` and log a WARNING (mirror the safe-default + visibility pattern of ADR-026 / `BOOTSTRAP_UNPARSABLE`) rather than silently persisting garbage.
- Regression test: `create_initial(..., priority='P1')` yields `priority: p1` in HEAD yaml and the spec renders in the P1 group of `render_backlog`.

**Out of scope:**
- Changing `write_lifecycle` priority handling (it does not take priority — status writer only).
- Making `render_backlog` case-insensitive (defense-in-depth alternative; normalizing at the write primitive is the SSOT fix — do not split the contract across both).
- Backfilling any existing uppercase yamls (none known; TECH-198/BUG-199 already corrected).
- `kind` case normalization — separate concern; `kind` is rendered verbatim and not grouped, so no silent-drop. Note only.

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `lifecycle.create_initial` — callers: `orchestrator.bootstrap_new_specs` (`:436`, already lowercases), spark CAS claim (completion.md protocol, `by='spark'`), `recover_bootstrap_as_done.py` (no priority arg), operator tooling. ✓

### Step 2: DOWN — what depends on?
- `_build_yaml_content` (consumes normalized priority). No new deps; pure string normalization + logging.

### Step 3: BY TERM
- `priority=priority` → `lifecycle.py:475` (the verbatim passthrough being fixed).
- `PRIORITY_ORDER` → `render_backlog.py` (the consumer that requires lowercase).
- `.group(1).lower()` → `orchestrator.py:482` (the existing correct precedent to align with).

### Step 4: CHECKLIST
- Tests: `scripts/vps/tests/` (extend an existing lifecycle test module or add a focused case). ✓
- No migration / edge function. Docs: none required beyond test (behaviour-preserving for correct callers). ✓

### Step 5: DUAL SYSTEM
- Single source: priority is normalized at the write primitive; readers (`render_backlog`) keep their lowercase contract. No dual-write.

---

## Tasks

1. **Normalize + validate** (`lifecycle.py`): lowercase/strip `priority` in `create_initial`; default unknown values to `p1` with a WARNING log.
2. **Test** (`scripts/vps/tests/`): assert uppercase input → lowercase yaml in HEAD; assert unknown input → `p1` + warning; assert rendered backlog places the spec in the correct group.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/lifecycle.py` — Task 1: normalize+validate priority in create_initial (modify)
- `scripts/vps/tests/test_lifecycle_create_initial.py` — Task 2: normalization tests (create)

---

## Tests

1. **Uppercase normalized.** `create_initial(repo, 'TECH-XXX', priority='P0', kind='TECH', by='spark')` → HEAD yaml `priority: p0`.
2. **Mixed/whitespace normalized.** `' P2 '` → `p2`.
3. **Unknown defaults + warns.** `priority='urgent'` → yaml `priority: p1` AND a WARNING is logged (caplog).
4. **Renders in correct group.** After a `P1` create, `render_backlog.render_backlog(repo)` contains the spec id under the P1 table (regression for the original silent-drop).

---

## Blueprint Reference

Infrastructure robustness (DLD orchestrator lifecycle primitive). Defensive-default follow-up to ARCH-196/ADR-027 (spec-first CAS opened create_initial to multiple callers) in the spirit of ADR-026 (no silent drift; safe default + visible WARNING). Cosmetic-but-correctness: prevents queued-yet-invisible specs.
