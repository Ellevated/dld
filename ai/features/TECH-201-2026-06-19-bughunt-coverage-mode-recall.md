# Feature: [TECH-201] Bughunt/audit finding-stage coverage-mode (Opus 4.8 recall fix)

**Priority:** P1 | **Date:** 2026-06-19

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.

⚠️ **Size warning:** 16 allowed files (12 are identical mechanical edits across
6 personas × 2 copies). All edits are pure-markdown prompt changes, R2,
homogeneous. Kept as one spec because the edit pattern is uniform. If autopilot
struggles, the persona block and the coroner/review block split cleanly.

## Why

Official Anthropic Opus 4.8 prompting guide (Code review harnesses section,
saved in `memory/reference_opus-4-8-prompting-guide.md`) documents a harness
effect: when a finding-stage prompt says "only report high-severity",
"no speculative issues", "be conservative", **Opus 4.8 obeys it more literally
than 4.7** — it investigates just as deeply, finds the candidate bug, then
withholds it below the stated bar. Measured recall falls even though
bug-finding ability rose. The guide's fix: at the finding stage require
**coverage**, push filtering to a dedicated downstream stage.

DLD's bughunt personas are exactly a finding stage with a real downstream
filter (`bughunt-validator`, Step 4). Their `## Constraints` blocks currently
suppress uncertain findings ("Report ONLY concrete", "No speculative",
"No theoretical risks — only what's exploitable"). On 4.8 this silently drops
real bugs the validator can never recover. `audit/coroner.md` has the same
"triage ruthlessly / Dead code is noise" suppression in deep-mode (synthesizer
merges, does not re-triage). `review.md` is already hardened in root but the
template copy is stale (no Reviewer Discipline block).

## Context

- Audit 2026-06-19 (this session) mapped pipeline stages: bughunt personas
  (FINDING) → collector → assembler → **validator (TRIAGE)** → report-updater.
  Validator is the intended filter; personas must over-report by design.
- Verified: all 6 personas byte-identical root vs template; findings YAML
  schema has `severity` only, **no `confidence` field** (pure addition).
- `bughunt-validator.md` "ruthless triage" is INTENTIONAL — out of scope, do
  NOT touch.
- night-mode (no downstream filter) is handled separately in TECH-204.

---

## Scope
**In scope:**
- Rewrite `## Constraints` of 6 bughunt personas (root + template) from
  suppression to coverage-mode; add `confidence: high|medium|low` to each
  findings YAML schema so the validator can rank.
- `audit/coroner.md` (root + template): replace "triage ruthlessly" /
  "Dead code is noise" with "report all, label severity accurately".
- `review.md`: sync hardened root → template (Reviewer Discipline block +
  `checks_performed` + frontmatter `model: sonnet`/`effort: xhigh`); add one
  concrete report-bar line to both. (review.md frontmatter is synced HERE, not
  in TECH-203, to avoid a same-file collision — TECH-203 excludes review.md.)

**Out of scope:**
- `bughunt-validator.md` (intentional triage stage — keep filtering).
- night-mode coverage (TECH-204).
- Model/effort frontmatter of all agents EXCEPT review.md (TECH-203 owns the
  rest; review.md is fully owned here).
- Anti-hallucination rule "every finding must reference file:line + evidence"
  — KEEP it; coverage ≠ permission to invent.

---

## Impact Tree Analysis

### Step 1: UP — who consumes persona findings?
- `bughunt-findings-collector` (haiku, "Do NOT filter") → `spec-assembler` →
  `bughunt-validator` (the filter). Coverage increases validator input; the
  added `confidence` field gives it a ranking key.

### Step 2: DOWN — what do personas depend on?
- Shared findings YAML schema (per-persona, inline). Each schema edited to add
  `confidence`.

### Step 3: BY TERM
- `grep -rn "Report ONLY concrete" .claude template` → expect 0 after change.
- `grep -rn "No speculative\|No theoretical\|only what's exploitable" .claude template` → 0 after change.
- `grep -rn "triage ruthlessly\|Dead code is noise" .claude template` → 0 after change.

### Step 4: CHECKLIST
- [ ] No tests/migrations affected (pure prompt files).
- [ ] Both `.claude/` and `template/.claude/` copies edited (template-sync.md).

### Verification
- [ ] grep by old suppression terms = 0 across both trees.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts. -->

ONLY the files listed below may be modified during implementation.

- `.claude/agents/bug-hunt/code-reviewer.md` — Constraints → coverage + confidence field (modify)
- `.claude/agents/bug-hunt/security-auditor.md` — Constraints → coverage + confidence field (modify)
- `.claude/agents/bug-hunt/qa-engineer.md` — Constraints → coverage + confidence field (modify)
- `.claude/agents/bug-hunt/junior-developer.md` — Constraints → coverage + confidence field (modify)
- `.claude/agents/bug-hunt/software-architect.md` — Constraints → coverage + confidence field (modify)
- `.claude/agents/bug-hunt/ux-analyst.md` — Constraints → coverage + confidence field (modify)
- `template/.claude/agents/bug-hunt/code-reviewer.md` — sync (modify)
- `template/.claude/agents/bug-hunt/security-auditor.md` — sync (modify)
- `template/.claude/agents/bug-hunt/qa-engineer.md` — sync (modify)
- `template/.claude/agents/bug-hunt/junior-developer.md` — sync (modify)
- `template/.claude/agents/bug-hunt/software-architect.md` — sync (modify)
- `template/.claude/agents/bug-hunt/ux-analyst.md` — sync (modify)
- `.claude/agents/audit/coroner.md` — report all, label severity (modify)
- `template/.claude/agents/audit/coroner.md` — sync (modify)
- `.claude/agents/review.md` — add concrete report-bar line (modify)
- `template/.claude/agents/review.md` — sync Reviewer Discipline block + report-bar (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD meta (agent/skill prompts — no src domain).
**Cross-cutting:** none.
**Data model:** none (prompt-only).

---

## Historical Risks

<!-- lessons-binding v1 -->

none (no `ai/lessons/` bank for the meta/prompts domain).

---

## Approaches

### Approach 1: Coverage-mode at finding stage, confidence field for ranking (SELECTED)
**Source:** Anthropic Opus 4.8 guide — "Code review harnesses".
**Summary:** Personas report every candidate incl. low-confidence, tagged with
`confidence`; validator ranks/drops downstream.
**Pros:** Restores recall; aligns with documented 4.8 behavior; validator
already exists to filter.
**Cons:** More raw findings reach validator (mitigated — see devil note below).

### Approach 2: Leave personas, only fix prompts qualitatively
**Summary:** Soften wording without a confidence field.
**Cons:** Validator gets no ranking key; harder to manage volume.

### Selected: 1
**Rationale:** Matches guide; confidence field turns volume into rankable signal.

**Devil note (A-1, this session):** coverage raises validator input volume.
Mitigation baked into rewrite: coverage means "do not suppress uncertain REAL
candidate issues", NOT "report trivial nits". Keep the file:line+evidence
requirement. Validator's `< 3 relevant` reject is a floor, unaffected. If
volume becomes a problem in practice, a validator-side cap is a follow-up
(out of scope here).

---

## Design

### Persona `## Constraints` rewrite (apply to all 6, both copies)
Replace the suppression bullets with:

```
## Constraints

- READ-ONLY on the target codebase — never modify analyzed source.
- Every finding MUST reference file:line and cite the code evidence you saw
  (anti-hallucination — coverage does not mean inventing).
- Report EVERY issue you find, including uncertain or low-severity ones. Do
  NOT filter for importance, confidence, or exploitability at this stage — the
  validator (Step 4) ranks and drops findings downstream. Withholding an
  uncertain real finding here is unrecoverable.
- For each finding set `severity` and `confidence` so the validator can rank.
- If you suspect an issue but cannot fully confirm it, emit it with
  `confidence: low` and state what you could not verify.
```
(Adapt the persona noun: "vulnerabilities" for security-auditor, "architectural
issues" for software-architect, "UX issues" for ux-analyst, etc.)

### Findings schema addition (all 6)
Next to `severity: critical | high | medium | low` add:
```
confidence: high | medium | low   # high=confirmed, low=suspected/unverified
```

### coroner.md
- "Priority-aware: ... you triage ruthlessly" → "Priority-aware: report all
  debt; label severity accurately so the synthesizer can rank."
- "Dead code is noise — flag it but don't overweight it" → "Dead code still
  counts — flag every instance with file:line; mark it low severity rather
  than omitting it."

### review.md report-bar (both copies) + template discipline sync
- Add to `## Rules`: "Report bar: flag any issue that could cause incorrect
  behavior, a test failure, a security/data-loss risk, or a duplication/
  architecture violation per the checklists. Only omit pure cosmetic
  preferences. When unsure → report as needs_discussion, never silently pass."
- Copy the `## Reviewer Discipline (READ FIRST)` block and the mandatory
  `checks_performed` requirement from root `review.md` into template copy.
- Sync template `review.md` frontmatter to root: `model: opus`/`effort: high`
  → `model: sonnet`/`effort: xhigh` (ADR-019 rebalance; matches root SSOT).
  This is the ONLY agent-frontmatter change in TECH-201 (rest in TECH-203).

---

## Implementation Plan

### Task 1: Bughunt personas coverage-mode (12 files)
**Type:** code
**Files:** modify the 6 personas in `.claude/agents/bug-hunt/` and the 6 in
`template/.claude/agents/bug-hunt/`.
**Acceptance:** every persona's `## Constraints` matches the coverage rewrite;
every findings schema has a `confidence` field; suppression terms gone.

### Task 2: coroner.md report-all (2 files)
**Type:** code
**Files:** modify `.claude/agents/audit/coroner.md`, `template/.claude/agents/audit/coroner.md`.
**Acceptance:** "triage ruthlessly" and "Dead code is noise" replaced.

### Task 3: review.md report-bar + template discipline sync (2 files)
**Type:** code
**Files:** modify `.claude/agents/review.md`, `template/.claude/agents/review.md`.
**Acceptance:** both have the report-bar line; template has Reviewer Discipline
block + `checks_performed`.

### Execution Order
1 → 2 → 3

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Suppression removed (personas) | `grep -rn "Report ONLY concrete\|No speculative\|No theoretical\|only what's exploitable" .claude/agents/bug-hunt template/.claude/agents/bug-hunt` | 0 matches | deterministic | guide | P0 |
| EC-2 | Confidence field added | `grep -lc "confidence: high" .claude/agents/bug-hunt/{code-reviewer,security-auditor,qa-engineer,junior-developer,software-architect,ux-analyst}.md` | all 6 ≥1 | deterministic | design | P0 |
| EC-3 | Coverage language present | `grep -rl "Report EVERY issue" .claude/agents/bug-hunt template/.claude/agents/bug-hunt` | 12 files | deterministic | design | P0 |
| EC-4 | coroner suppression gone | `grep -rn "triage ruthlessly\|Dead code is noise" .claude template` | 0 matches | deterministic | guide | P0 |
| EC-5 | review template hardened | `grep -c "Reviewer Discipline\|checks_performed" template/.claude/agents/review.md` | ≥2 | deterministic | M3 | P1 |
| EC-6 | validator untouched | `git diff --name-only` does NOT include `validator.md` | true | deterministic | scope guard | P1 |
| EC-7 | review template frontmatter synced | `grep -E "model: sonnet" template/.claude/agents/review.md` | present | deterministic | ADR-019 | P1 |

### Coverage Summary
- Deterministic: 7 | Integration: 0 | LLM-Judge: 0 | Total: 7 (min 3) ✓

### TDD Order
1. EC-1/EC-4 (removal) → edit → pass
2. EC-2/EC-3 (additions) → edit → pass
3. EC-5 (template sync) → edit → pass

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | personas valid markdown frontmatter | `head -8 .claude/agents/bug-hunt/code-reviewer.md` | frontmatter intact | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | no suppression terms anywhere | repo root | grep EC-1 + EC-4 commands | 0 matches |
| AV-F2 | confidence field in all personas | repo root | EC-2 command | all 6 hit |

### Verify Command

```bash
# Removal
grep -rn "Report ONLY concrete\|No speculative\|No theoretical\|only what's exploitable\|triage ruthlessly\|Dead code is noise" .claude template/.claude || echo "OK: no suppression terms"
# Additions
grep -rl "Report EVERY issue" .claude/agents/bug-hunt template/.claude/agents/bug-hunt | wc -l   # expect 12
grep -l "confidence: high" .claude/agents/bug-hunt/*.md | wc -l                                   # expect 6
# Template discipline
grep -c "checks_performed" template/.claude/agents/review.md                                      # expect ≥1
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] All 6 personas (×2) in coverage-mode with `confidence` field
- [ ] coroner reports all, labels severity
- [ ] review template synced + report-bar in both copies

### Tests
- [ ] All EC-1..EC-6 pass
- [ ] validator.md NOT in the diff

### Technical
- [ ] root and template parity for personas + coroner
- [ ] No frontmatter model/effort changes (deferred to TECH-203)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
