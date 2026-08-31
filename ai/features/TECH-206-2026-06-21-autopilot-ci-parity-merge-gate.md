# Feature: [TECH-206] Autopilot CI-parity merge gate — stop merging into a red develop

**Priority:** P1 | **Date:** 2026-06-21 | **Risk:** R1 (cross-project, autopilot state machine)

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> **STATUS: draft — NOT in backlog.** Orphan spec by design: orchestrator
> `bootstrap_new_specs` skips spec.md without a backlog row (orchestrator.py:439).
> Founder review required before adding a `queued` backlog row to dispatch.

## Why

Observed live on **awardybot** (2026-06-21): autopilot merged a dense batch of
specs (FTR-1258…1266, BUG-1256/1267, ARCH-1262) into `develop` while the `CI`
workflow was **red on every push**, and each new spec opened with a `fix(...)`
of the *previous* spec's defect. Seven consecutive commits, same defect class:

| # | Commit | Broke |
|---|--------|-------|
| 1 | f75e1e25 | lint (cohort tests — unused imports / import sort) |
| 2 | c601c587 | EC-2 literal flow path (BUG-1254) |
| 3 | aa471c9a | stale fixtures `assigned_at` (BUG-1253) |
| 4 | 8fffa239 | lint (unused `pytest_asyncio`) |
| 5 | 56fc2033 | EC-2 literal flow path (FTR-1259) |
| 6 | b3add88a | SIM117 + EC-2 (FTR-1260) |
| 7 | 296ffe96 | file-size 400 LOC (FTR-1263) |

Evidence:
- `gh run list --branch develop` on awardybot: the `CI` job is `failure`/`cancelled`
  on essentially every recent push; only `Deploy Miniapp (DEV)` is green.
- Latest failure (run 27913467363) = step **"Validate spec compliance"**:
  `Files not in Allowed Files of FTR-1263`.
- `lifecycle(FTR-1260): force-done` was applied **on top of red CI**.
- `gh api .../branches/develop/protection` → `403 Upgrade to Pro`: branch
  protection / required status checks are **unavailable** on this private repo's
  plan. GitHub cannot block the merge — the pipeline must.

### Two root causes

**Root 1 — gate-parity gap.** Autopilot's final gate before merge is
`./test fast` (= lint + unit only). The CI workflow (`ci.yml`) runs **9 checks**.
Six of them are never run locally before merge:

| CI check | In `./test fast`? |
|----------|-------------------|
| ruff check | ✅ |
| unit tests | ✅ |
| validate spec compliance (Allowed Files) | ❌ |
| check file sizes (400 / 600) | ❌ |
| check import violations | ❌ |
| check zero-caller functions | ❌ |
| check transition rules sync | ❌ |
| check docs sync | ❌ |
| RPC coverage | ❌ |

Autopilot validates with a **subset** → sees green locally → merges → CI catches
the other six **post-merge, on an already-red develop**.

**Root 2 — CI-only redness is deliberately ignored.** `autopilot-git.md:65-80`
(PHASE 0 CI Health Check) treats `ci-status.sh` exit 0 as
*"Green **OR CI-only failures** → Continue"*. Only a deploy failure (exit 2)
blocks. So red lint/spec/file-size is, by design, an acceptable state to build
on and to merge into.

### Mechanism of the treadmill
Defect merges into red develop → next spec's worktree branches off
`origin/develop` (carries the red) → its coder trips over the red, fixes it
*in passing*, adds its own new red → repeat. The 7 commits above are this loop.

## Context

- Gate touchpoints today, all `./test fast`:
  - `autopilot-git.md:131-135` PHASE 0 baseline
  - `autopilot-git.md:199-204` (5.1) + `finishing.md:12` PHASE 3 final test
  - `finishing.md:174` Pre-Done Checklist
  - `escalation.md:11` `./test fast fail → STOP (5 retries)`
- Merge happens locally, `git merge --ff-only` + `git push origin develop`
  (`autopilot-git.md:255-291`, `finishing.md:43-50`). No CI-parity check sits
  between merge and push.
- `./test` and `scripts/ci-status.sh` are **per-project** artifacts (awardybot
  has them; dld does not — dld `./test` is a directory). The autopilot skill is
  **universal** → both root `.claude/` and `template/.claude/` copies must change
  (template-sync rule).
- Branch protection unavailable (free plan) → local enforcement is the only lever.

---

## Scope

**In scope (Wave 1 — pipeline contract + enforcement, dld only):**
- Introduce a **`./test ci` contract**: a per-project command that mirrors the
  project's GitHub CI exactly. Document the contract in the autopilot skill.
- Autopilot PHASE 3 final gate: `./test fast` → **`./test ci`** (blocking).
- Autopilot PHASE 3 merge: after `git merge --ff-only` into develop and
  **before** `git push`, run `./test ci` on the merged tree; if red → **reset
  develop to origin (abort merge), do NOT push, emit `needs_review`**.
- `ci-status.sh` semantics in PHASE 0: CI-only redness must no longer be a silent
  "continue" — record the pre-existing red baseline so the merge gate can require
  *no new* failures (regression-only enforcement when develop is already red).
- `escalation.md`: add `./test ci fail → STOP`.
- **Graceful fallback:** if a project has no `./test ci` case, autopilot does NOT
  silently fall back to `./test fast` — it logs `CI_PARITY_UNAVAILABLE`, runs the
  fullest available target, and emits `needs_review` on any redness (no silent
  degradation).

**Out of scope (separate follow-ups):**
- Per-project implementation of `./test ci` (Wave 2 — one inbox item per project:
  awardybot, dowry, wb, …). This spec ships the contract + enforcement; projects
  adopt `./test ci` afterward.
- Activating `gate-daemon` Wave 2 as a post-merge backstop (Approach C — separate
  ARCH spec).
- Fixing the current red awardybot develop (one-shot cleanup — founder deferred).
- Any change to `callback.py` status writing (lifecycle SoT unchanged).

---

## Impact Tree Analysis

### Step 1: UP — who depends on the autopilot gate?
- Every VPS project's autopilot run (all projects in `projects.json`). Changing
  the final gate from `./test fast` to `./test ci` affects all of them →
  fallback path is mandatory to avoid breaking projects without `./test ci`.

### Step 2: DOWN — what does the gate depend on?
- Per-project `./test` script + `scripts/ci-status.sh`; `.github/workflows/ci.yml`
  (the source of truth `./test ci` must mirror).

### Step 3: BY TERM
- `grep -rn "./test fast" .claude/skills/autopilot template/.claude/skills/autopilot`
- `grep -rn "CI-only\|ci-status" .claude/skills/autopilot template/.claude/skills/autopilot`

### Step 4: CHECKLIST
- [ ] Both copies (root + template) of finishing.md, autopilot-git.md, escalation.md.
- [ ] No code/migration changes (prompt-only spec).
- [ ] Fallback path documented (no silent `./test fast` degradation).

### Step 5: DUAL SYSTEM
- The "source of truth" for CI is `ci.yml`; `./test ci` is a mirror. Drift between
  them is the residual risk (see Approaches A vs B).

### Verification
- [ ] `grep "./test fast"` in PHASE 3 final-gate context = 0 (replaced by `./test ci`).
- [ ] Merge gate (post-merge, pre-push `./test ci` + rollback) present in both copies.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `.claude/skills/autopilot/autopilot-git.md` — PHASE 0 ci-status semantics + PHASE 3 final gate `./test ci` + post-merge/pre-push gate with rollback (modify)
- `.claude/skills/autopilot/finishing.md` — Flow step 1 + merge step 8 + Pre-Done Checklist: `./test ci` (modify)
- `.claude/skills/autopilot/escalation.md` — add `./test ci fail → STOP` (modify)
- `template/.claude/skills/autopilot/autopilot-git.md` — sync (modify)
- `template/.claude/skills/autopilot/finishing.md` — sync (modify)
- `template/.claude/skills/autopilot/escalation.md` — sync (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.
In particular: do NOT edit `callback.py`, `orchestrator.py`, `gate-daemon.py`,
per-project `./test` / `ci.yml` (those are Wave 2 / separate specs).

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** autopilot skill (`.claude/skills/autopilot/`) + template mirror.
**Cross-cutting:** CI parity, merge safety, template-sync rule.
**Data model:** none (prompt-only).

---

## Historical Risks

<!-- lessons-binding v1 -->

- **ADR-020** — no headless loop wrapper; autopilot runs as native session. The
  gate change must stay inside the skill prompt, not a wrapper script.
- **TECH-197** — PUSH GUARD already emits `needs_review` on push failure; the new
  merge gate reuses that exact signal path (no new mechanism).
- **template-sync.md** — autopilot skill is universal: edit `template/` then sync
  root (or keep both identical in one task). CI "Check documentation sync" /
  parity is part of why root drifted before.
- **awardybot TECH-1063** (autopilot-git.md:117) — worktree base must be
  `origin/develop`; do not regress that during PHASE 0 edits.

---

## Approaches

### Approach A: Local `./test ci` parity gate + post-merge rollback (SELECTED)
**Summary:** Autopilot runs `./test ci` (mirror of GitHub CI) as the blocking
final gate, and again on the merged develop tree before push; red → reset develop
to origin, no push, `needs_review`.
**Pros:** Fast (no waiting on remote CI); deterministic; independent of GitHub
plan/branch-protection; direct control; reuses TECH-197 push-guard signal.
**Cons:** `./test ci` can drift from `ci.yml` (must be kept in sync per project);
requires Wave 2 per-project adoption (graceful fallback bridges the gap).

### Approach B: Wait for real GitHub CI green on the feature branch before merge
**Summary:** Push feature branch → poll `gh run` for that ref → merge into develop
only if the real CI is green.
**Pros:** Zero parity drift (literally the same CI); no per-project `./test ci`
needed → works for all projects immediately; a true replacement for the
unavailable required-status-checks.
**Cons:** +3–5 min wall-clock per spec; depends on `ci.yml` triggering on
feature-branch pushes (must verify the `on:` triggers); double CI run
(feature + develop); a develop-side race can still surface post-merge.
**→ A vs B is the key architectural decision for review.** AI-First economics make
B's time cost cheap; B's zero-drift property is attractive. A is shipped as the
default because it is self-contained and immediate; B can supersede it if CI
triggers on feature branches.

### Approach C: gate-daemon Wave 2 as post-merge reverter
**Cons:** Post-merge (red already landed) — a backstop, not a pre-merge gate.
Complementary to A/B, not a substitute. Separate ARCH spec.

### Selected: A (with B flagged for architect review)
**Rationale:** A stops the bleeding without remote dependencies and reuses the
existing `needs_review` path. B is the cleaner long-term parity guarantee and
should be evaluated once `ci.yml` branch triggers are confirmed.

---

## Design

### autopilot-git.md
- **PHASE 0 CI Health Check (`:65-80`):** keep `ci-status.sh` call, but change the
  exit-0 semantics table: "Green OR CI-only failures → Continue" becomes
  "Green → continue; **CI-only red → record baseline red set, continue in
  REGRESSION-ONLY mode** (merge gate must show no NEW failures vs baseline);
  Deploy failure (exit 2) → DEPLOY ERROR PROTOCOL (unchanged)."
- **PHASE 0 baseline (`:131-135`):** `./test fast` baseline → note that the
  authoritative parity baseline is `./test ci` (fast kept as a quick smoke).
- **5.1 Final Test (`:199-204`):** `./test fast` → `./test ci` (blocking).
- **5.4 Merge to Develop (`:255-291`):** after `git merge --ff-only` and BEFORE
  `git push origin develop`, insert:
  ```bash
  # CI-parity merge gate (TECH-206): merged develop must be green (or no worse
  # than the PHASE-0 baseline red set in regression-only mode).
  if ! ./test ci; then
    git reset --hard origin/develop      # abort the local merge, develop untouched on origin
    echo "BLOCKED: ./test ci red on merged develop — emitting needs_review"
    # Autopilot MUST set task_status="needs_review" in final JSON. Do NOT push.
    # (If ./test ci case is absent: log CI_PARITY_UNAVAILABLE, run fullest target,
    #  needs_review on any red — never silent ./test fast fallback.)
  fi
  ```
  Reuses TECH-197 push-guard `needs_review` semantics.

### finishing.md
- **Flow step 1 (`:12`):** `./test fast` → `./test ci` (must pass).
- **Flow step 8 (`:43-50`):** add the post-merge/pre-push `./test ci` gate with
  `git reset --hard origin/develop` rollback + `needs_review` on red.
- **Pre-Done Checklist (`:174`):** `./test fast` → `./test ci`.

### escalation.md
- Retry table (`:11`): add row `./test ci fail | 5 | → STOP (ask human)` (or
  replace the `./test fast` row, keeping fast as the per-task quick gate and `ci`
  as the finishing gate — clarify both rows).

### Fallback contract (both files)
Document explicitly: a project with no `./test ci` case → autopilot logs
`CI_PARITY_UNAVAILABLE`, runs the fullest available target (`./test` full), and
emits `needs_review` on any redness. **Never** silently degrade to `./test fast`.

### Root/template parity
All six files end identical to their counterpart except pre-existing intentional
diffs. CI "Check documentation sync" should pass.

---

## Drift Log

**Checked:** 2026-06-21 UTC
**Result:** no_drift (line refs captured from current HEAD this session)

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `.claude/skills/autopilot/finishing.md` | none | — |
| `.claude/skills/autopilot/autopilot-git.md` | none | — |
| `.claude/skills/autopilot/escalation.md` | none | — |
| `template/.claude/skills/autopilot/*` | none | — |

---

## Detailed Implementation Plan

### Task 1: autopilot-git.md — PHASE 0 semantics + PHASE 3 gates (root + template)
**Files:**
- Modify: `.claude/skills/autopilot/autopilot-git.md:65-80,131-135,199-291`
- Modify: `template/.claude/skills/autopilot/autopilot-git.md` (same edits)

**Steps:**
1. Rewrite the CI Health Check table (exit-0 row) per Design (regression-only mode
   on CI-only red; deploy failure unchanged).
2. Replace 5.1 `./test fast` with `./test ci`.
3. Insert the post-merge/pre-push `./test ci` gate with `git reset --hard
   origin/develop` rollback + `needs_review` (the bash block in Design).
4. Add the fallback paragraph (`CI_PARITY_UNAVAILABLE`).
5. Apply identical edits to the template copy.

**Acceptance:**
- [ ] `grep -n "./test ci" .claude/skills/autopilot/autopilot-git.md` ≥ 2
- [ ] `grep -n "git reset --hard origin/develop" .claude/skills/autopilot/autopilot-git.md` ≥ 1
- [ ] `grep -n "CI-only red" .claude/skills/autopilot/autopilot-git.md` present
- [ ] root vs template diff = pre-existing intentional diffs only

### Task 2: finishing.md — Flow + merge step + Pre-Done Checklist (root + template)
**Files:**
- Modify: `.claude/skills/autopilot/finishing.md:12,43-50,174`
- Modify: `template/.claude/skills/autopilot/finishing.md`

**Steps:**
1. Flow step 1: `./test fast` → `./test ci`.
2. Flow step 8 (merge): add post-merge/pre-push `./test ci` gate + rollback +
   `needs_review` note.
3. Pre-Done Checklist Code Quality item: `./test fast` → `./test ci`.
4. Apply identical edits to template copy.

**Acceptance:**
- [ ] `grep -n "./test ci" .claude/skills/autopilot/finishing.md` ≥ 2
- [ ] Pre-Done Checklist references `./test ci`
- [ ] root vs template diff = intentional diffs only

### Task 3: escalation.md — `./test ci fail → STOP` (root + template)
**Files:**
- Modify: `.claude/skills/autopilot/escalation.md:11`
- Modify: `template/.claude/skills/autopilot/escalation.md`

**Steps:**
1. Add/clarify retry rows: `./test fast` (per-task quick gate) and `./test ci`
   (finishing gate) → both STOP after their retry budgets.
2. Apply to template copy.

**Acceptance:**
- [ ] `grep -n "./test ci" .claude/skills/autopilot/escalation.md` ≥ 1
- [ ] root vs template diff = intentional diffs only

### Execution Order
Task 1 → Task 2 → Task 3 (independent; ordered for review clarity). Each task
edits root + template together to keep parity in one commit.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions
| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | final gate is CI-parity | `grep -rn "./test ci" .claude/skills/autopilot template/.claude/skills/autopilot` | ≥ 6 matches | deterministic | Root 1 | P0 |
| EC-2 | merge rollback present | `grep -rn "git reset --hard origin/develop" .claude/skills/autopilot template/.claude/skills/autopilot` | ≥ 2 | deterministic | design | P0 |
| EC-3 | CI-only red no longer silent-continue | `grep -rn "CI-only red\|regression-only" .claude/skills/autopilot template/.claude/skills/autopilot` | present | deterministic | Root 2 | P0 |
| EC-4 | escalation gate | `grep -rn "./test ci" .claude/skills/autopilot/escalation.md template/.claude/skills/autopilot/escalation.md` | ≥ 2 | deterministic | design | P1 |
| EC-5 | no silent fast fallback | `grep -rn "CI_PARITY_UNAVAILABLE" .claude/skills/autopilot template/.claude/skills/autopilot` | ≥ 2 | deterministic | fallback | P1 |
| EC-6 | root/template parity | `diff <(...) <(...)` for each of the 3 files | intentional diffs only | deterministic | template-sync | P1 |

### Integration Assertions
| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-7 | a project with `./test ci` returning non-zero | dry-read the PHASE 3 prompt logic | merge aborted, develop reset, `needs_review` emitted, no push | integration (manual/dry) | design | P0 |

### Coverage Summary
- Deterministic: 6 | Integration: 1 | LLM-Judge: 0 | Total: 7 (min 3) ✓

### TDD Order
1. Apply edits → run EC-1..EC-6 grep/diff checks → pass.
2. EC-7 reviewed by spec-reviewer (prompt-logic walk-through; no runtime).

---

## Acceptance Verification (MANDATORY)

### Smoke Checks
| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | gate replaced | `grep -rn "./test ci" .claude/skills/autopilot` | ≥ 3 | 10s |
| AV-S2 | rollback present | `grep -rn "reset --hard origin/develop" .claude/skills/autopilot` | ≥ 1 | 10s |
| AV-S3 | parity | `diff .claude/skills/autopilot/finishing.md template/.claude/skills/autopilot/finishing.md` | intentional diffs only | 10s |

### Verify Command
```bash
grep -rn "./test ci" .claude/skills/autopilot template/.claude/skills/autopilot | wc -l   # ≥ 6
grep -rn "git reset --hard origin/develop" .claude/skills/autopilot template/.claude/skills/autopilot
grep -rn "CI_PARITY_UNAVAILABLE" .claude/skills/autopilot template/.claude/skills/autopilot
for f in finishing autopilot-git escalation; do
  echo "== $f =="; diff ".claude/skills/autopilot/$f.md" "template/.claude/skills/autopilot/$f.md" || true
done
```

### Post-Deploy URL
```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Autopilot final gate before merge is `./test ci` (CI-parity), not `./test fast`.
- [ ] Post-merge/pre-push `./test ci` gate aborts merge (reset to origin) + emits
      `needs_review` on red; never pushes a red develop.
- [ ] CI-only redness no longer a silent "continue"; regression-only mode documented.
- [ ] No-`./test ci` projects → `CI_PARITY_UNAVAILABLE` + `needs_review`, no silent
      `./test fast` fallback.

### Tests
- [ ] EC-1..EC-7 pass.

### Technical
- [ ] root/template parity for all 3 files (template-sync rule).
- [ ] No code, no migration, no lifecycle/callback changes.
- [ ] Reuses TECH-197 `needs_review` push-guard signal (no new status mechanism).

### Follow-ups (NOT in this spec — create as inbox items)
- [ ] Wave 2: per-project `./test ci` implementation (awardybot, dowry, wb, …).
- [ ] One-shot: fix current red awardybot develop to green.
- [ ] Evaluate Approach B (wait-for-real-CI) once `ci.yml` branch triggers confirmed.
- [ ] Consider gate-daemon Wave 2 as a post-merge backstop (Approach C).

---

## Autopilot Log
[Auto-populated by autopilot during execution]
