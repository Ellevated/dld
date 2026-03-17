# Devil's Advocate — TECH-152: AI-First Economic Model

## Verdict: Caution

Proceed with the *mindset shift*, but NOT with the proposed scope of "switch all skills and agents." The proposal correctly identifies a real problem (human effort estimates distorting AI prioritization) but prescribes invasive surgery where a bandaid suffices. The ratio of files touched to value delivered is terrible — which, ironically, is exactly the kind of over-engineering Amelia the Pragmatist would reject.

---

## Critical Risks

### 1. Priority Inflation is Real and Unaddressed

The proposal removes the only friction filter in the system. Currently, effort acts as a natural brake: "this is P2 because it's 3 weeks of work" keeps low-value items from competing with high-value ones. Remove effort, and the backlog collapses into a flat list where everything is "high impact, zero cost."

**Evidence from the actual backlog** (`ai/backlog.md`): The INTERNAL section already uses P0-P3 without effort estimates. Yet sequencing still works because the founder manually groups tasks into LAUNCH BLOCKERS / GROWTH / INTERNAL sections. The real prioritization is categorical (must-have vs nice-to-have), not numeric. Removing effort from P-scores doesn't change this — the categorical judgment is what matters.

**The real risk:** If autopilot reads `P0 first` (line 135 of `autopilot/SKILL.md`) and everything is P1 because there's no effort to differentiate, the system degenerates to FIFO ordering. That's not prioritization — that's a queue.

### 2. Hidden Costs Are 10-100x the Compute Cost

The "$1 per task" framing is dangerously misleading. The actual cost structure:

| Cost type | Per-task estimate | Who pays |
|-----------|------------------|----------|
| Compute (API tokens) | $1-5 | API bill |
| Human review | 5-15 min = $17-50 at $200/hr | Founder |
| Context switching | 2-5 min per review notification | Founder |
| Debugging AI mistakes | 15-60 min per failed task | Founder |
| Tech debt accumulation | Deferred, compounds | Future founder |
| Merge conflicts (5 parallel slots) | 10-30 min per conflict | Founder + AI retry |

The founder's review time IS the bottleneck, not compute cost. Making compute cheaper doesn't make review cheaper. If anything, more cheap tasks = more review load = founder drowns.

### 3. The 5-Slot Parallelism Problem is Unsolved

5 parallel agents touching the same codebase is already risky. The proposal implicitly encourages "do everything since it's cheap," which means more tasks queued, more parallel execution, more merge conflicts. The `orchestrator.sh` already manages slot contention (`try_acquire_slot()`), but slot availability != safe parallelism. Two tasks modifying `telegram-bot.py` simultaneously will conflict regardless of slot availability.

### 4. WSJF/RICE Don't Actually Collapse — They Transform

The claim "WSJF/RICE collapse when effort is constant" is mathematically true but practically wrong. WSJF = (Business Value + Time Criticality + Risk Reduction) / Job Size. If Job Size = constant, WSJF = numerator only. That's not "collapse" — that's simplification. The numerator still differentiates tasks perfectly well. The problem isn't the formula — it's that agents write "effort: 3 weeks" when they should write "effort: $5."

The fix is to teach agents the correct effort scale, not to remove effort from the model entirely.

---

## Edge Cases

### Tasks Where Effort DOES Matter for AI

1. **Multi-spec refactoring chains.** TECH-129 (Multi-Agent ADR Migration) touched 20+ files across the entire `.claude/` tree. Even at $5/task, the total was $50+ and required careful sequencing. "Near-zero effort" is a lie for such tasks.

2. **Tasks requiring human-in-the-loop.** The council skill (`/council`) already takes 9 agents + human decision. Cost: $3-8 compute + 15-30 min human time. The human time dominates, and it scales with task complexity — not linearly.

3. **External dependency waits.** Tasks blocked on "deploy to production and verify" or "wait for DNS propagation" have effort that's 100% wall-clock time, not compute. Marking these as "$1" hides that they block a slot for hours.

4. **Retry spirals.** When autopilot's debugger loop hits max retries (3 rounds per `escalation.md`), a "$1 task" becomes a $15-20 task that still fails and gets `blocked`. The expected cost is not the compute cost — it's the expected compute cost weighted by failure probability.

### Priority Inflation Scenario

Today: 30 tasks in backlog, 10 are P1, 5 are P0.
After change: 30 tasks, effort filter removed, founder thinks "everything is cheap" and marks 20 as P1, 8 as P0.
Result: Autopilot processes P0s in FIFO order. The actual important P0 (a production bug) sits behind 7 "P0" refactoring tasks because they were queued first.

### Backward Compatibility Break

The DLD template (`template/.claude/`) is designed for ANY team using it — not just solo founders. A human team of 3 developers using DLD will get agents that say "effort is irrelevant" when effort is very much relevant for them. The proposal conflates the DLD author's use case (solo + AI) with the template's intended audience (any team).

---

## Simpler Alternative?

**Yes, overwhelmingly yes.**

Instead of modifying 23 skills + unknown number of agents, add ONE paragraph to `CLAUDE.md`:

```markdown
## AI-First Effort Model

Implementation effort is near-zero for AI agents (~$1-5 per task).
Never deprioritize a task based on implementation effort alone.
Prioritize purely by Impact and Cost of Delay:
- P0: Blocking revenue or users NOW
- P1: High impact, should be done this week
- P2: Nice to have, do when slots are free

When estimating complexity, use dollar cost ($1/$5/$10), not human time.
```

**Why this works:**
- All agents read `CLAUDE.md` before every session
- Council pragmatist already has `LLM-Native Mindset` section with cost references
- Spark facilitator's Question Bank already asks "How urgent is this? P0/P1/P2?"
- The pragmatist agent (`council/pragmatist.md`) already uses $ cost estimates

**What it doesn't require:**
- Modifying 23 skill files
- Changing the spec template format
- Breaking backward compatibility for template users
- Removing the effort field from anywhere

**Cost:** 1 file edit, 5 minutes, ~$0.50.

### Even Simpler: Do Nothing

The system already works this way in practice. Look at the evidence:
- Backlog uses categorical sections (LAUNCH BLOCKERS / GROWTH / INTERNAL), not WSJF scores
- Autopilot picks `P0 first` — effort never enters the selection algorithm
- Council pragmatist already thinks in $ terms
- No agent currently runs a WSJF calculation before prioritizing

The "problem" may be theoretical, not practical.

---

## Mitigation Recommendations

If you proceed despite the above:

1. **Start with CLAUDE.md rule only.** Measure for 2 weeks whether agent behavior actually changes. If it does — you're done. If not, then investigate which specific skills need modification.

2. **Keep effort field in spec template.** Just change its semantics from "human weeks" to "AI cost estimate: $1/$5/$10/$50." This preserves the information (some tasks ARE more expensive even for AI) without the distorting effect of human time estimates.

3. **Add a review-load estimate.** The real bottleneck is founder review time, not compute. Add a field: `Review burden: low (glance) / medium (10 min) / high (30+ min)`. This captures the ACTUAL cost that matters.

4. **Don't touch template/.claude/.** Per `template-sync.md`, universal changes go to template first. But this change is DLD-specific (solo founder assumption). Put it in `.claude/` only and explicitly document "DLD-specific: solo-founder AI-first cost model."

5. **Gate priority inflation.** Add a rule: "Maximum 5 P0 tasks at any time. If adding a new P0, demote the least urgent existing P0 to P1." This prevents the "everything is P0" failure mode regardless of whether effort exists.

6. **Measure before changing.** Run `/audit` on the last 20 completed specs. How many were deprioritized due to effort? If the answer is zero — the problem doesn't exist and TECH-152 is solving a phantom issue.
