# Pattern Research — skill-creator (TECH-145)

## Context

Upgrading DLD's `skill-writer` to `skill-creator` pattern based on Anthropic's upstream (March 2026).

**Key changes being evaluated:**
- Eval-driven iteration loop (draft → test → grade → review → improve → repeat)
- Description optimization with trigger testing
- Progressive disclosure (3-level loading)
- 3 new agents: grader, comparator, analyzer
- Python scripts for eval automation
- Two modes: CREATE (eval loop) + UPDATE (Three-Expert Gate)

**Constraints:** DLD ADR-007 (caller-writes), ADR-008 (background fan-out), ADR-009 (background ALL), ADR-010 (orchestrator zero-read), ADR-011 (enforcement as code), ADR-012 (eval criteria).

---

## Approach 1: Full Anthropic Port

**Source:** [Anthropic skill-creator SKILL.md — anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md)

### Description

Take Anthropic's upstream skill-creator wholesale: 4 operating modes (Create, Eval, Improve, Benchmark), 4 composable subagents (executor, grader, comparator, analyzer), Python scripts for eval automation (`aggregate_benchmark.py`, `generate_review.py`), HTML eval-viewer, and workspace directory structure (`-workspace/iteration-N/eval-N/`). Minimal DLD-specific adaptation — only change paths and naming to match DLD conventions.

### Pros

- Exactly tracks Anthropic's latest thinking — no interpretation overhead
- All 4 subagents are purpose-built and battle-tested against the same use case
- Python scripts handle the deterministic work (aggregation, HTML viewer) — no LLM waste
- Eval loop is genuine: grade against assertions, compare versions blind, show variance
- Description optimizer solves the trigger precision problem (ETH Zurich study: unvalidated context = +20% cost, 0% gain)

### Cons

- **ADR violations throughout:** executor runs skills by spawning Claude sub-sessions; comparator reads output directly into orchestrator context (violates ADR-010); scripts assume Python env not guaranteed in DLD projects
- **No state.json enforcement** (ADR-011): progress tracked by workspace files, not JSON gates — LLM can skip steps
- **Python dependency:** `generate_review.py`, `aggregate_benchmark.py` require Python 3.x; DLD hooks are Node.js (mjs); mixed environments create ops burden
- **HTML viewer** is a browser-based artifact — doesn't fit DLD's markdown-first output culture
- `allowed-tools` frontmatter (new Anthropic field) not yet in DLD agent templates
- No adaptation for DLD's agent subagent_type routing (opus/sonnet/haiku effort levels, ADR-005)
- File limits: Anthropic SKILL.md regularly exceeds 500 LOC; DLD hard limit is 500

### Complexity

**Estimate:** Hard — 12-16 hours

**Why:** Surface-level porting is fast (2 hours), but then you hit a cascade of ADR conflicts. Each subagent needs rewrite to use `run_in_background: true` + file-gate pattern. Python scripts either get replaced with .mjs equivalents or a Python runtime assumption gets documented. HTML viewer is incompatible with DLD report format. Risk: builds something that looks done but fails at runtime due to silent ADR violations.

### Example Source

```markdown
# From Anthropic's SKILL.md (upstream):
## Running and evaluating test cases
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
...
Once all runs are done:
1. Grade each run — spawn grader subagent
2. Aggregate: python -m scripts.aggregate_benchmark <workspace>/iteration-N
3. Launch viewer: python <skill-creator-path>/eval-viewer/generate_review.py ...
```

The executor/grader fan-out is a direct foreground Task pattern — violates ADR-009/010 in DLD context.

---

## Approach 2: DLD-Native Rewrite

**Source:** [Tessl — Anthropic brings evals to skill-creator](https://tessl.io/blog/anthropic-brings-evals-to-skill-creator-heres-why-thats-a-big-deal/) + [Hwee-Boon Yar — Using skill-creator to improve skills](https://hboon.com/using-the-skill-creator-skill-to-improve-your-existing-skills/)

### Description

Take Anthropic's *concepts* (eval loop, 4-mode structure, description optimizer, grader/comparator/analyzer agents) but rewrite entirely in DLD idioms. Agents use `subagent_type` routing with effort levels per ADR-005. Grader/comparator/analyzer run as background agents per ADR-008/009. Orchestrator reads only collector summary per ADR-010. State tracked in `state.json` with HARD-GATE enforcement per ADR-011. Output is DLD-native markdown (not HTML). Scripts are `.mjs` (Node.js), not Python. Progressive disclosure (3-level loading) is added to agent templates. `allowed-tools` added to frontmatter spec per user choice.

### Pros

- Zero ADR violations — built to spec from scratch
- Full DLD idiom consistency (state.json gates, background fan-out, collector pattern, mjs scripts)
- Eval loop maps cleanly to existing DLD eval skill (ADR-012 criteria format)
- `allowed-tools` + `project-agnostic` frontmatter additions are straightforward
- Maintenance: DLD team owns every line — no upstream drift surprises
- Template-sync compliant (template/.claude/ gets clean version, .claude/ gets it too)

### Cons

- High upfront investment to rewrite 4 agents + SKILL.md + scripts in DLD idioms
- Risk of missing nuance in Anthropic's eval design (e.g., blind A/B comparison logic, variance analysis)
- `.mjs` eval scripts are less ergonomic than Python for data aggregation (JSON, stats)
- No HTML viewer alternative — eval results stay in markdown; less visual comparison
- Grader, comparator, analyzer agents don't exist in DLD yet — 3 new agent files needed
- Description optimizer requires actually running sub-Claude sessions with a mock skill to test trigger accuracy — architectural challenge in Claude Code context

### Complexity

**Estimate:** Hard — 16-20 hours

**Why:** 4 new/rewritten agents, 1 new SKILL.md (~400 LOC), 2-3 .mjs scripts, state.json schema, collector pattern, background fan-out wiring. Risk: underestimating the description optimizer — testing "does this description trigger correctly?" requires a live eval environment that's hard to simulate inside a DLD agent task.

### Example Source

```javascript
// DLD-native .mjs equivalent of aggregate_benchmark.py
import { readFileSync, writeFileSync } from 'fs'
import { glob } from 'glob'

const runs = await glob(`${workspace}/iteration-${n}/eval-*/grading.json`)
const results = runs.map(f => JSON.parse(readFileSync(f)))
const passRate = results.filter(r => r.passed).length / results.length
writeFileSync(`${workspace}/iteration-${n}/benchmark.json`, JSON.stringify({ passRate, mean, stddev }))
```

Pattern: DLD scripts stay .mjs, use Node.js stdlib + existing npm deps, write markdown reports not HTML.

---

## Approach 3: Minimal Viable — SKILL.md + Agents Only (No Scripts)

**Source:** [mager.co — Claude Code: How to Write, Eval, and Iterate on a Skill](https://www.mager.co/blog/2026-03-08-claude-code-eval-loop/) + [Anthropic Engineering — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Description

Update `SKILL.md` with the eval-driven loop described in natural language, add `allowed-tools` + `project-agnostic` to frontmatter, add 3 new agent `.md` files (grader, comparator, analyzer) as lightweight LLM-judge subagents. No Python or .mjs scripts — the LLM does the aggregation inline. No HTML viewer — results in markdown. No state.json — loop driven by SKILL.md instructions. Eval cases stored in `evals/evals.json` as per Anthropic's format. This ships the concept immediately with minimal infrastructure.

### Pros

- **Fastest time-to-value:** 4-6 hours, shippable in one session
- No new infrastructure: no scripts, no ADR-014 needed for new state schema
- Grader/comparator/analyzer agents are straightforward LLM-judge prompts — DLD already has eval-judge agent pattern
- SKILL.md update adopts Anthropic's 4-mode structure + progressive disclosure guidance
- Frontmatter additions (allowed-tools, project-agnostic) are 2-line changes
- Easily iterable: if eval loop proves valuable → scripts added as TECH-146 later
- ADR compliant by omission: no scripts = no Python/mjs question; agent dispatch follows existing patterns

### Cons

- **No deterministic aggregation:** LLM does pass/fail math inline — error-prone, not repeatable
- **No variance analysis:** benchmark.json with mean ± stddev requires scripted computation
- **No description optimizer:** the trigger-testing component is the hardest part — skipping it leaves a known gap
- Eval cases in `evals/evals.json` are generated but not run deterministically
- Without state.json enforcement (ADR-011), the loop is only as reliable as LLM memory — will drift
- "Minimal" risks becoming "permanent minimal" — tech debt crystallizes
- Comparator without blind A/B is just reading two outputs sequentially — loses the blind evaluation benefit

### Complexity

**Estimate:** Easy — 4-6 hours

**Why:** SKILL.md rewrite (~300-400 LOC), 3 agent files (~100 LOC each), frontmatter additions (10 LOC). No new infrastructure. Main risk is the grader agent prompt getting the rubric format right.

### Example Source

From Anthropic's engineering blog pattern — deterministic + LLM-as-judge combined:
```
Grade each run — spawn a grader subagent that evaluates each assertion
against the outputs. Each assertion is either:
  - Code-based: exact match, substring, regex
  - Model-based: LLM grades against rubric (0.0-1.0)
Save results to grading.json in each run directory.
```

DLD already has `eval-judge` agent with rubric-based scoring (0.0-1.0). The minimal approach uses it directly without a Python aggregator.

---

## Approach 4: Phased — SKILL.md + Agents First, Scripts as TECH-146

**Source:** [ainews.com — Anthropic Adds Evaluation and A/B Testing to Claude Agent Skills](https://www.ainews.com/p/anthropic-introduces-built-in-evaluation-and-benchmarking-for-claude-agent-skills-to-improve-enterpr) + [Improving skill-creator: Test, measure, and refine Agent Skills — Anthropic Blog](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)

### Description

Ship Approach 3 now (SKILL.md + 3 agents + frontmatter updates), then separately plan the eval automation scripts as a follow-on TECH task. The split is explicit in the backlog, not an accident. This is a structured phased delivery: the concept ships this sprint, the infrastructure follows in the next. DLD's `eval` skill already handles golden-dataset evaluation — `skill-creator` can delegate to it for the scripted component until native scripts are ready.

### Pros

- **Best time-to-value ratio:** concept ships today, infrastructure follows with proper ADR design
- The eval delegation to existing DLD `/eval` skill is architecturally clean — reuse over reinvent
- Scripts can be designed ADR-compliant from the start (not retrofitted)
- Explicit TECH-146 in backlog = no forgotten tech debt; commitment is tracked
- Matches DLD's own "finish first" rule — ship something real, then layer on
- Template-sync is simpler: SKILL.md + agents go to both template/ and .claude/ now; scripts go later
- Progressive disclosure (3-level) and `allowed-tools` ship immediately — high value, low risk

### Cons

- Two-sprint delivery means the full Anthropic eval loop isn't live until TECH-146 done
- Risk: TECH-146 gets deprioritized if TECH-145 "feels done" — common pattern (CLAUDE.md anti-pattern #1: starts many, finishes few)
- Eval delegation to `/eval` is a workaround, not the designed solution
- Description optimizer still missing in Phase 1 (same as Approach 3)

### Complexity

**Estimate:** Medium — 6-8 hours (Phase 1) + 8-12 hours (Phase 2, TECH-146)

**Why:** Phase 1 is Approach 3 + explicit TECH-146 spec. Phase 2 is the DLD-native scripts from Approach 2 but with cleaner ADR design upfront. Total complexity ~same as Approach 2, but risk is distributed across two tasks with natural checkpoints.

### Example Source

Phase 1 delivers this agent pattern (reusing eval-judge):
```yaml
# grader.md (new agent)
name: skill-creator-grader
description: Grade skill eval outputs against assertion rubrics
model: sonnet
effort: high
tools: Read
```

Phase 2 delivers:
```javascript
// scripts/aggregate_benchmark.mjs (TECH-146)
// Reads iteration-N/eval-*/grading.json
// Computes pass_rate, mean ± stddev
// Writes benchmark.json + benchmark.md
```

---

## Comparison Matrix

| Criteria | Approach 1 (Full Port) | Approach 2 (DLD-Native) | Approach 3 (Minimal MVP) | Approach 4 (Phased) |
|----------|----------------------|------------------------|------------------------|---------------------|
| ADR Compliance | Low | High | High | High |
| Time-to-Value | Low (12-16h, risky) | Low (16-20h) | High (4-6h) | High now, builds later |
| Feature Completeness | High (all 4 modes) | High (all 4 modes) | Medium (no scripts, no optimizer) | Medium → High (phased) |
| Maintenance Burden | High (upstream drift) | Low (DLD owns) | Low | Low |
| Script Infrastructure | Python (incompatible) | .mjs (native) | None needed | None → .mjs (TECH-146) |
| Eval Loop Quality | High (blind A/B, variance) | High (same concepts) | Medium (no deterministic agg) | Medium → High |
| Template-Sync Risk | High (LOC limit breach) | Medium | Low | Low |
| Description Optimizer | Yes (upstream) | Yes (rewritten) | No | No → TECH-146 |
| Iteration Risk | High | Medium | Low | Low |
| Dependencies | Python 3.x, HTML viewer | Node.js (existing) | None new | None now |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 4 (Phased — SKILL.md + Agents first, Scripts as TECH-146)

### Rationale

The feature breaks cleanly into two tiers of value. The first tier — eval-driven *thinking* (grader/comparator/analyzer as LLM agents, 4-mode structure, frontmatter additions, progressive disclosure guidance) — ships within one session and is immediately useful. The second tier — deterministic *infrastructure* (aggregation scripts, variance analysis, description optimizer) — requires a separate design session to do ADR-correctly, and none of it is blocking for the first tier.

Approach 1 fails on ADR compliance. Anthropic's executor runs skills as foreground sessions feeding output back into the orchestrator context — a direct ADR-010 violation. The Python scripts assume a Python runtime DLD doesn't guarantee. Porting this correctly would take longer than a DLD-native rewrite and still produce a maintenance burden as upstream evolves.

Approach 2 is the right architecture but wrong timing. Writing 4 agents + SKILL.md + 3 scripts + state.json schema in one task, all ADR-correctly, is a 16-20 hour scope. The "CRITICAL: Underestimates complexity" anti-pattern applies here exactly.

Approach 3 is tempting but introduces silent failure modes. Without deterministic aggregation, the eval loop is as reliable as LLM math — which isn't. The description optimizer is the most genuinely novel part of the upstream update; skipping it in MVP and never revisiting it is the likely outcome.

Key factors:
1. **YAGNI on scripts now:** DLD's existing `/eval` skill can delegate until native scripts are ready; we're not flying blind
2. **ADR-011 risk deferred explicitly:** state.json enforcement design belongs in TECH-146 where it gets proper attention, not retrofitted
3. **Backlog discipline:** explicit TECH-146 entry prevents the "felt done" trap; the commitment is tracked

### Trade-off Accepted

Approach 4 ships without the description optimizer (trigger precision testing) and without deterministic benchmark variance analysis. These are the most statistically rigorous parts of Anthropic's design. We accept lower precision on trigger testing in Phase 1 — the Three-Expert Gate in UPDATE mode partially compensates because description quality is one of the gate criteria. Phase 2 closes this gap when scripts are designed ADR-correctly.

We also accept that the Phase 1 eval loop is LLM-driven for aggregation (not scripted). This means variance analysis and pass-rate calculations can have rounding errors. This is acceptable for an internal DLD meta-tool where the author is reviewing outputs manually anyway.

---

## Research Sources

- [Anthropic skill-creator GitHub (claude-plugins-official)](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md) — upstream SKILL.md structure, 4 modes, subagent architecture
- [Anthropic Blog — Improving skill-creator: Test, measure, and refine Agent Skills](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills) — official description of eval loop additions
- [Tessl — Anthropic brings evals to skill-creator](https://tessl.io/blog/anthropic-brings-evals-to-skill-creator-heres-why-thats-a-big-deal/) — analysis of what Anthropic shipped, ETH Zurich study on unvalidated context
- [Hwee-Boon Yar — Using skill-creator to improve existing skills](https://hboon.com/using-the-skill-creator-skill-to-improve-your-existing-skills/) — real-world run with writing-voice skill, eval viewer behavior
- [mager.co — Claude Code: How to Write, Eval, and Iterate on a Skill](https://www.mager.co/blog/2026-03-08-claude-code-eval-loop/) — trigger precision vs output quality distinction, full tutorial
- [Anthropic Engineering — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — eval structure, deterministic + LLM-judge grader types
- [ainews.com — Anthropic Adds Evaluation and A/B Testing to Claude Agent Skills](https://www.ainews.com/p/anthropic-introduces-built-in-evaluation-and-benchmarking-for-claude-agent-skills-to-improve-enterpr) — 4-mode overview, Comparator blind A/B pattern
- [Complete guide to building Skills for Claude (Anthropic PDF → gist)](https://gist.github.com/joyrexus/ff71917b4fc0a2cbc84974212da34a4a) — progressive disclosure 3-level spec, frontmatter reference including allowed-tools
- [Dotzlaw Consulting — Claude Code Skills progressive disclosure](https://www.dotzlaw.com/insights/claude-skills/) — token budget analysis, 3-tier loading mechanics
