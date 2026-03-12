# TOC Experiment #1: CRT vs 5 Whys vs Code Audit

**Date:** 2026-02-13
**Status:** Complete
**Project:** Awardybot (BUG-477: Buyer flow breaks)

---

## Experiment Design

**Goal:** Compare three approaches to bug investigation on the same bug.

**Bug:** "Разрывы в User Flow байер-бота при переходах между шагами"

**Prompt (identical for all):** "У нас баг в User Flow в buyer agent, когда люди двигаются по шагам, скидывают скриншоты — видят разрывы. Поищи, выясни причину, оформи спецификацию."

### Three runs

| ID | File | When | Spark Config |
|----|------|------|-------------|
| A | `BUG-477-2026-02-12-buyer-flow-continuity.md` | Before TOC discussion | Vanilla Spark (feature-mode style) |
| B | `BUG-477-2026-02-13-buyer-flow-breaks (clear debug mode).md` | After rollback | Vanilla Spark (5 Whys bug-mode) |
| C | `BUG-477-2026-02-13-buyer-flow-breaks (toc).md` | After TOC-layer applied | TOC-enhanced Spark (CRT) |

---

## Raw Results

### Spec A — Original (code audit style)

**Methodology:** No explicit root cause method. Direct code scan + fix listing.

**Problems found (6):**
1. UGC_PUBLISHED — empty instructions in locales
2. search_flow.py — missing FTR-469 checks (has_pending_review)
3. search_flow.py — missing _send_to_moderation for max_attempts
4. manual_moderation — no navigation hint
5. Orphan channel_subscribe state (dead code)
6. FSM inconsistency (intermediate set_state + double DB write)

**Strengths:**
- Widest coverage (6 unique issues)
- Detailed code examples (before/after Python)
- Flow Coverage Matrix (every user step mapped to task)
- UI Event Completeness table
- Approaches comparison (2 approaches, selected simpler)

**Weaknesses:**
- Root cause: "7 проблем разной критичности" — flat list, no hierarchy
- No prioritization between issues
- No risk assessment / negative branches
- No conflict analysis

### Spec B — Vanilla (5 Whys)

**Methodology:** 5 Whys (linear chain per symptom)

**Problems found (5):**
1. Reply keyboard handlers lack state filter — break proof flow
2. manual_moderation dead-end — no handler
3. Redundant FSM write — race condition
4. No CTA hint on instructions screen
5. Stale callback in slot_proof — no guard

**Strengths:**
- Concrete reproduction steps (3 scenarios)
- Code examples in every fix
- Root cause attempt (5 Whys chain)

**Weaknesses:**
- Root cause = "Комплексная проблема" — 4 separate issues listed, not hierarchical
- No convergence analysis
- No risk assessment (0 NBR)
- No conflict analysis

### Spec C — TOC (CRT)

**Methodology:** Current Reality Tree with convergence analysis

**Problems found (3+1):**
1. Split-message pattern (double "Принято!" + instructions)
2. Screen flickering (delete-then-send timing)
3. Missing navigation keyboard (pending_review, rejection)
4. PICKUP substep loss on navigation back/forward
5. (bonus) Rejection messages without keyboard

**Strengths:**
- Convergence analysis: 2 clusters (UDE-1+2, UDE-3+5)
- 3 core problems with coverage % (40%+40%+20%)
- Evidence typing per link (all CODE — see caveat below)
- Fix Conflict analysis (proper vs safe → injection)
- Fix Validation: 6 NBR with safeguards
- Fix grouping by root cause (not flat list)

**Weaknesses:**
- Missed infrastructure issues (FSM race condition, state hijacking, orphan code)
- No code examples (descriptive only)
- No reproduction steps
- No Flow Coverage Matrix
- Evidence marking suspiciously clean (0 HYPOTHESIS — see analysis)

---

## Comparison Matrix

### Issues found (unique per approach)

| Issue | A | B | C |
|-------|---|---|---|
| UGC_PUBLISHED empty instructions | + | | |
| FTR-469 checks missing in search_flow | + | | |
| _send_to_moderation missing | + | | |
| Orphan channel_subscribe state | + | | |
| Reply keyboard hijacking (no state filter) | | + | |
| CTA hint missing on instructions | | + | |
| Stale callback guard missing | | + | |
| Split-message pattern (double messages) | | | + |
| Screen flickering (delete-then-send) | | | + |
| PICKUP substep loss on navigation | | | + |
| Rejection without keyboard | | | + |
| FSM inconsistency / race condition | + | + | |
| manual_moderation dead-end | + | + | + |
| pending_review keyboard missing | | ~ | + |

**Overlap: ~15%.** Each approach found 3-4 UNIQUE issues.

### Metrics

| Metric | A (Original) | B (Vanilla) | C (TOC) |
|--------|-------------|-------------|---------|
| Symptoms collected | 7 | 4 | 5 |
| Root cause structure | Flat list | Linear (5 Whys) | Tree (CRT) |
| Root causes identified | "7 проблем" | "1 комплексная" | 3 with coverage % |
| Convergence | No | No | Yes (2 clusters) |
| Evidence per link | File refs | file:line | file:line + type |
| HYPOTHESIS marking | No | No | Yes (but see caveat) |
| Conflict analysis | Approaches section | None | EC-lite (injection) |
| NBR count | 0 | 0 | 6 |
| Safeguards | 0 | 0 | 6 |
| Code examples | Detailed Python | Detailed Python | None (descriptive) |
| Reproduction steps | None | 3 scenarios | None |
| Flow Coverage Matrix | Yes | No | No |
| UI Event Completeness | Yes | No | No |
| Fix grouping | By execution order | Flat | By root cause |

---

## Key Insights

### 1. Three Different Lenses

Each approach sees through its own paradigm:

| Approach | Lens | Finds | Misses |
|----------|------|-------|--------|
| A (code audit) | Code structure | Infrastructure, dead code, gaps | Causality, risk |
| B (5 Whys) | Symptom → cause chain | State bugs, interaction gaps | Systemic patterns |
| C (CRT) | User symptoms → system | UX patterns, convergence, risk | Infrastructure, code-level |

**Conclusion:** These are complementary, not competing approaches.

### 2. TOC CRT works for LLM — with caveats

**What works well:**
- UDE collection ("bugs travel in packs" — found 5 vs user-reported 1-2)
- Convergence (found 2 clusters — genuine insight)
- Coverage % quantification
- Fix grouping by root cause
- EC conflict resolution (injection, not compromise)
- NBR (6 real risks with safeguards)

**What doesn't work:**
- Self-validation of causal links (anchoring bias — see below)
- Evidence typing honesty (all marked CODE, 0 HYPOTHESIS — suspicious)
- Doesn't look at code infrastructure (stays at user-visible symptom level)

### 3. LLM Cannot Self-Validate (Critical Finding)

**The anchoring problem:** When LLM writes chain A←B←C, then is asked "Can A happen WITHOUT B?" — it confirms its own output ~90% of the time.

**Evidence from experiment:** TOC spec has 0 HYPOTHESIS links. Every link marked CODE. This is suspiciously clean — some links are likely interpretations labeled as verified facts.

**Implication:** Self-validation questions in the prompt (Q1, Q2 per link) are largely performative. The LLM goes through the motion but doesn't genuinely challenge itself.

**Solution:** Validation must come from a DIFFERENT agent (no anchoring to the tree). This is the core argument for the two-teammate architecture.

### 4. One Good Counter-Example > 120 Checkboxes

Instead of 8 CLR checks × 15 links = 120 verifications (which LLM will do superficially), one counter-example prompt works better:

> "Describe a realistic scenario where your core problem is FIXED, but the symptoms STILL exist."

LLMs are good at generating scenarios (their strength). They're bad at systematically verifying logic (their weakness). Play to strengths.

### 5. TOC starts from user symptoms → misses code infrastructure

CRT methodology: collect observable negative effects → trace down to causes. This naturally leads to USER-VISIBLE issues (double messages, flickering, dead-ends). It STOPS when it reaches code that explains the visible symptom.

It doesn't go further to ask: "What ELSE is wrong in this code area?" — which is where Code Auditor finds race conditions, orphan states, missing guards.

**This is not a bug in TOC — it's a scope difference.** TOC solves "what the user sees." Code audit finds "what will break next."

---

## Architecture Decision: Two Teammates, Not One Hybrid

### Why not merge into one prompt

Merging strengths of all three approaches into one prompt would:
- Overload the agent (checklist + CRT + code examples + reproduction + NBR)
- Dilute each approach's focus
- Violate TOC itself: don't make one resource do everything

### Two-teammate design

```
Teammate 1: Code Auditor          Teammate 2: TOC Analyst
Focus: CODE                       Focus: SYSTEM
├─ Universal checklist:           ├─ CRT: UDE → chains → convergence
│  control flow, data flow,       ├─ EC: conflict → injection
│  interface, code hygiene        ├─ FRT: NBR + safeguards
├─ Reproduction steps             ├─ Evidence typing (honest)
├─ Code examples (before/after)   ├─ Coverage %
├─ Grep-driven search             ├─ Counter-example self-check
└─ CLR validation of CRT links    └─ Fix grouping by root cause
```

### Three-phase protocol

**Phase 1 (parallel):** Both investigate independently.
**Phase 2 (cross-pollination):** Exchange findings via mailbox.
  - Auditor sends issues → Analyst incorporates into CRT
  - Analyst sends CRT → Auditor uses to guide deeper investigation
**Phase 3 (adversarial):** Each challenges the other's conclusions.
  - Auditor validates CRT links by code (CLR #5, #6, #7)
  - Analyst challenges Auditor's fixes for systemic impact

### Why adversarial phase matters

LLM can't self-validate (anchoring bias). But it CAN validate SOMEONE ELSE'S work (no anchoring). The adversarial phase IS the CLR check — but done by an agent who didn't write the tree.

---

## Prompt Design Insights (for LLM)

### What to put IN the prompt

1. **Evidence marking** — LLM CAN do this honestly (knows if it read a file)
2. **Convergence search** — LLM CAN do this (pattern matching is its strength)
3. **Coverage counting** — LLM CAN count
4. **Counter-example generation** — LLM CAN generate scenarios
5. **Quantitative thresholds** — "70% coverage", "<50% go deeper" prevent premature stopping

### What to REMOVE from the prompt

1. **Self-validation of causal links** — doesn't work (anchoring bias)
2. **Multiple checks per link** — becomes checkbox ticking
3. **Full 8 CLR** — overloads context, most checks done superficially

### What to DELEGATE to other agent

1. **Cause-Effect Reversal (#6)** — Auditor checks by code: does B→A make more sense?
2. **Additional Cause (#5)** — Auditor greps: who ELSE calls this function?
3. **Predicted Effect (#7)** — Auditor checks: if root cause is X, do OTHER places show same pattern?

### Universal prompt principles

- Examples in prompts should be generic (API, not aiogram-specific)
- Domain-specific hints belong in project CLAUDE.md, not in TOC prompt
- Checklist categories are universal: control flow, data flow, interface, code hygiene

---

## Next Steps

- [ ] Write refined prompts for both teammates (incorporating insights above)
- [ ] Design mailbox message protocol (typed messages, not free text)
- [ ] Experiment #2: Run sequential simulation (Analyst → Auditor → Analyst) on same BUG-477
- [ ] Compare experiment #2 output with all three single-agent specs
- [ ] Decide: wait for Agent Teams GA or implement via sequential subagents
- [ ] Write Spark v2 architecture spec (when experiments validate approach)

---

## Cost & Token Analysis

| Spec | Estimated Cost | Quality |
|------|---------------|---------|
| A (original) | ~$2-3 | Widest coverage, no depth |
| B (vanilla) | ~$2-3 | Medium coverage, some depth |
| C (TOC) | ~$3-4 | Best structure, missed infrastructure |
| Two teammates (projected) | ~$6-10 | Full coverage + depth + validation |

Two teammates ~2-3x cost of single agent. Justified if quality delta prevents even one rework loop (which costs $5-15 in coder+tester+debugger time).

---

*Experiment conducted by human + Claude Opus 4.6 on Awardybot project.*
*Three specs produced independently, compared side-by-side.*
