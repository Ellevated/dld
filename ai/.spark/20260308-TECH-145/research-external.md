# External Research — skill-creator (TECH-145)

## Best Practices (5 with sources)

### 1. Eval-Driven Iteration Loop is the Anthropic Standard
**Source:** [Improving skill-creator: Test, measure, and refine Agent Skills](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills) — Anthropic, March 3, 2026
**Summary:** Anthropic's official skill-creator now operates in four modes: Create, Eval, Improve, Benchmark. The iteration loop is: draft skill → write test prompts → run prompts through executor → grade with grader → compare with comparator → surface patterns with analyzer → rewrite → repeat. The loop exits when quality stabilizes.
**Why relevant:** This is the exact pattern we're importing. The DLD skill-creator should mirror this loop but adapted to DLD's agent model (Task tool dispatch, background fan-out).

### 2. Unvalidated Context is Useless — Tested Context is the Standard
**Source:** [Anthropic brings evals to skill-creator. Here's why that's a big deal](https://tessl.io/blog/anthropic-brings-evals-to-skill-creator-heres-why-thats-a-big-deal/) — Tessl, March 4, 2026; citing ETH Zurich arXiv:2602.11988
**Summary:** ETH Zurich found: LLM-generated context files reduce task success by ~3%, human-written ones improve by only ~4%, both increase inference cost >20%. Root cause: context without a feedback loop contains redundant or actively wrong instructions. The correct response is "minimal effective context" validated through evals — not less context or more context.
**Why relevant:** Justifies the eval loop as non-optional. DLD skill-creator must gate "done" on eval pass, not on "looks good to the author."

### 3. Description Optimization via Train/Test Split is the Trigger Accuracy Mechanism
**Source:** [AgentSkills.so — skill-creator entry](https://agentskills.so/skills/anthropics-skills-skill-creator); [hboon.com walkthrough](https://hboon.com/using-the-skill-creator-skill-to-improve-your-existing-skills/)
**Summary:** Anthropic's `improve_description.py` script generates ~20 test queries (positive triggers, negative triggers, edge cases), splits into train/test, runs each against the skill description, measures hit rate, iterates. The description update is validated on the held-out test set before accepting it. This prevents overfitting to the training queries.
**Why relevant:** The 20-query / train-test split is the specific mechanism for `improve_description`. DLD's `improve_description.mjs` should implement the same split to avoid description overfitting.

### 4. Progressive Disclosure: Metadata First, Body on Demand, Resources as Needed
**Source:** [What Are Agent Skills? — DataCamp](https://www.datacamp.com/blog/agent-skills); [Awesome Claude Skills — travisvn](https://github.com/travisvn/awesome-claude-skills); [Anthropic platform docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
**Summary:** The standard 3-level architecture: (1) metadata/frontmatter ~100 tokens — always loaded, used for discovery; (2) SKILL.md body <5K tokens — loaded when description matches; (3) bundled resources (scripts, references, assets) — loaded only on explicit agent request. Companies including Cloudflare, Anthropic, Vercel, Cursor independently converged on this pattern in 2025-2026. Skills stuffed into one file produce weaker results.
**Why relevant:** DLD currently collapses levels 2 and 3 into one file. Skill-creator should enforce the 3-level structure when creating new skills, and flag single-file skills that mix body + resources.

### 5. Blind A/B Comparison with Pairwise Scoring is More Reliable than Absolute Scoring
**Source:** [Preference Evaluation: Pairwise Comparisons & Elo Rankings — mbrenndoerfer.com](https://mbrenndoerfer.com/writing/preference-evaluation-pairwise-comparisons-elo-llm); [Anthropic benchmark mode description from issue #397](https://github.com/anthropics/skills/issues/397)
**Summary:** Humans (and LLMs acting as judges) are far more consistent on relative judgments ("which is better?") than absolute scoring ("rate 1-10"). Anthropic's comparator agent performs blind A/B comparisons: it receives two outputs with labels hidden and picks the better one. Benchmark mode runs multiple iterations to compute variance, not just a single score. Multiple runs collapse variance.
**Why relevant:** DLD's `comparator` agent should do blind A/B, not "score old vs score new." The `aggregate_benchmark.mjs` script should run N iterations and report mean ± std, same as Anthropic's pattern.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| anthropics/skills skill-creator | main (Feb 25 export) | Official Anthropic pattern, Apache 2.0, tested at scale | Python scripts (we need .mjs port), no DLD-specific patterns | Reference implementation for all 4 modes + 3 agents | [GitHub issue #397](https://github.com/anthropics/skills/issues/397) |
| DeepEval | 2.x | Production eval framework, rich metrics, RAGAS support | Overkill for skill-level evals, Python | Full eval pipeline for complex agents | [SupaSkills prompt-eval-framework](https://www.supaskills.ai/skills/prompt-evaluation-framework) |
| promptfoo | 0.x | Open source, JS-native, regression detection | Separate infra, not integrated into skill flow | CI-level regression testing | [SupaSkills prompt-eval-framework](https://www.supaskills.ai/skills/prompt-evaluation-framework) |
| Existing DLD /eval | in-tree | Already integrated, golden pairs, LLM-as-Judge, .mjs | Focused on agent prompts not skill quality | Reuse eval-judge agent for skill grading | [/eval SKILL.md](/.claude/skills/eval/SKILL.md) |

**Recommendation:** Port Anthropic's patterns from `anthropics/skills` skill-creator as .mjs scripts. Reuse the existing DLD `eval-judge` agent as the grader — it already implements LLM-as-Judge with rubric scoring. Do not add DeepEval or promptfoo; they solve a different (larger) problem.

---

## Production Patterns

### Pattern 1: Four-Agent Eval Pipeline (Executor → Grader → Comparator → Analyzer)
**Source:** [Anthropic claude-plugins-official SKILL.md](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md); [tessl.io analysis](https://tessl.io/blog/anthropic-brings-evals-to-skill-creator-heres-why-thats-a-big-deal/)
**Description:** Four composable sub-agents run in sequence: executor runs the skill against a test prompt and captures output; grader evaluates the output against defined expectations; comparator does blind A/B between old and new versions; analyzer surfaces patterns that aggregate metrics hide (e.g., "fails on edge cases with ambiguous input"). The agents are parallel where possible (multiple test prompts → parallel executor runs → grader per output).
**Real-world use:** Anthropic production skill-creator (Claude.ai, Cowork, Claude Code plugin, GitHub repo as of Feb 25 2026 PR #465).
**Fits us:** Yes — maps cleanly to DLD's Task tool dispatch with background fan-out (ADR-008/ADR-009). Executor = Task dispatch of skill under test. Grader = our existing eval-judge. Comparator = new blind-A/B agent. Analyzer = new pattern-surface agent.

### Pattern 2: Description Optimizer with Train/Test Split
**Source:** [Anthropic claude-plugins-official SKILL.md](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md); [hboon.com walkthrough](https://hboon.com/using-the-skill-creator-skill-to-improve-your-existing-skills/)
**Description:** Separate script (`improve_description.py`) generates N trigger queries (positive + negative), splits 70/30 train/test, iterates description against training set, validates on test set. Accepts new description only if test-set hit rate exceeds threshold. Runs separately from main eval loop — called after skill quality is confirmed.
**Real-world use:** Anthropic production skill-creator, described in March 3 blog post as "optionally optimize the skill's description so the agent triggers it more reliably."
**Fits us:** Yes — matches the feature request. DLD skills currently have no trigger accuracy measurement. Port to `improve_description.mjs`. The 20-query budget (10 positive, 5 negative, 5 edge case) is the observed Anthropic default.

### Pattern 3: Benchmark Mode with Variance Analysis
**Source:** [GitHub issue #397 description of PR #465](https://github.com/anthropics/skills/issues/397); [AI News article](https://www.ainews.com/p/anthropic-introduces-built-in-evaluation-and-benchmarking-for-claude-agent-skills-to-improve-enterpr)
**Description:** Separate benchmark mode runs the same eval suite multiple times (typically 3-5 runs) with temperature >0 to measure output variance, not just mean score. `aggregate_benchmark.py` collects per-run scores and reports mean, std deviation, and confidence interval. High variance = fragile skill (sensitive to model temperature / phrasing). Low mean + low variance = reliably bad. High mean + high variance = needs hardening.
**Real-world use:** Anthropic production skill-creator, enterprise teams use it to detect model-update regressions before deploying new Claude versions.
**Fits us:** Yes — DLD's ADR-012 already mandates structured eval criteria with repeatability. Benchmark mode is a natural extension. Implement as `aggregate_benchmark.mjs`.

### Pattern 4: Hybrid Frontmatter (project-agnostic + allowed-tools fields)
**Source:** [Skill authoring best practices — platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [Complete skill builder guide — gist.github.com/joyrexus](https://gist.github.com/joyrexus/ff71917b4fc0a2cbc84974212da34a4a)
**Description:** The official Agent Skills standard frontmatter has `name` and `description` as required fields. Additional optional fields used in production include: `project-agnostic: true` (marks skills that work across any codebase — enables cross-project discovery); `allowed-tools` (restricts which tools the skill can request — security + cost control); `compatibility` (environment requirements). DLD currently uses `model` (non-standard) and `tools` (non-standard).
**Real-world use:** Standard fields adopted across Claude.ai, Cursor, GitHub Copilot, VS Code, LM-Kit.NET (open standard per agentskills.io).
**Fits us:** Yes, with caveat. Keep DLD's `model` field (it's a DLD convention, not the open standard — agents need it for routing). Add `project-agnostic` and `allowed-tools` for portability. These fields are silently ignored by platforms that don't support them, so backward-compatible.

---

## Key Decisions Supported by Research

1. **Decision:** Rename from skill-writer to skill-creator
   **Evidence:** Anthropic's official upstream tool is named `skill-creator` (claude-plugins-official repo, anthropics/skills repo, all blog posts as of March 2026). The name signals the create-and-iterate lifecycle, not just "write a file."
   **Confidence:** High

2. **Decision:** Two modes (CREATE with eval loop, UPDATE with Three-Expert Gate) vs. four modes (Anthropic's Create/Eval/Improve/Benchmark)
   **Evidence:** Anthropic separates Eval and Benchmark as distinct modes. For DLD, collapsing Eval+Improve into CREATE loop and keeping UPDATE separate preserves DLD's Three-Expert Gate (which Anthropic doesn't have). Benchmark becomes a sub-command within UPDATE mode.
   **Confidence:** High

3. **Decision:** Port scripts as .mjs (not Python)
   **Evidence:** DLD hooks are all .mjs (ADR from Feb 8, 2026 hooks migration). Anthropic uses Python scripts (`run_eval.py`, `aggregate_benchmark.py`, `improve_description.py`). Porting to .mjs keeps DLD's single-runtime stack (Node.js 18+) and avoids Python dependency.
   **Confidence:** High

4. **Decision:** Three new agents (grader, comparator, analyzer) vs. reusing eval-judge
   **Evidence:** DLD already has `eval-judge` agent which implements LLM-as-Judge with rubric scoring — this covers grader functionality. Comparator and analyzer are genuinely new capabilities not in eval-judge. Create 2 new agents (comparator, analyzer), extend eval-judge as grader rather than duplicating it.
   **Confidence:** Medium (depends on whether eval-judge rubric format is compatible with skill evals)

5. **Decision:** 20 queries (10 positive, 5 negative, 5 edge case) with 70/30 train/test split for description optimization
   **Evidence:** Observed from Anthropic's improve_description behavior described in hboon.com walkthrough and AgentSkills.so skill-creator entry. The train/test split prevents overfitting to synthetic queries.
   **Confidence:** Medium (observed behavior, not documented spec)

6. **Decision:** Keep eval loop in skill-creator rather than delegating entirely to /eval skill
   **Evidence:** The /eval skill is designed for agent prompt golden-pair testing. Skill evals require running the skill under test in a sandboxed context, which needs different scaffolding (executor agent). The two systems share `eval-judge` as the scoring engine but operate on different artifacts.
   **Confidence:** High

---

## Research Sources

- [Improving skill-creator: Test, measure, and refine Agent Skills](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills) — Anthropic official blog, March 3, 2026. Four modes, three new agents, description optimizer confirmed.
- [Anthropic claude-plugins-official: skill-creator SKILL.md](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md) — Actual SKILL.md source for the upstream skill-creator. Confirmed: eval loop, eval-viewer, description improver.
- [anthropics/skills GitHub repo](https://github.com/anthropics/skills) — 87K stars, Apache 2.0. PR #465 (Feb 25, 2026) exported eval/benchmark capabilities including agents/analyzer.md, comparator.md, grader.md, scripts/run_eval.py, aggregate_benchmark.py, eval-viewer/.
- [GitHub issue #397: eval/benchmark modes in GitHub version](https://github.com/anthropics/skills/issues/397) — Confirms what agents and scripts were added in the Feb 25 export. Key source for implementation inventory.
- [Skill authoring best practices — platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — Official docs: frontmatter requirements, progressive disclosure architecture, token economics of skill loading.
- [Anthropic brings evals to skill-creator — tessl.io](https://tessl.io/blog/anthropic-brings-evals-to-skill-creator-heres-why-thats-a-big-deal/) — Best technical analysis of the four-agent pipeline (executor/grader/comparator/analyzer). ETH Zurich citation on unvalidated context failure rates.
- [Evaluating AGENTS.md — ETH Zurich (arXiv:2602.11988)](https://www.sri.inf.ethz.ch/publications/gloaguen2026agentsmd) — The primary research paper. Key number: human-written context files improve success rate by only 4%, LLM-generated reduce by 3%, both increase cost >20%. Justifies mandatory eval loop.
- [Using skill-creator on writing-voice skill — hboon.com](https://hboon.com/using-the-skill-creator-skill-to-improve-your-existing-skills/) — Real walkthrough of the new skill-creator. Best source for understanding the description optimizer behavior: generates test prompts, grades outputs, shows comparison in browser viewer.
- [Progressive Disclosure in AI Agent Skill Design — Towards AI](https://pub.towardsai.net/progressive-disclosure-in-ai-agent-skill-design-b49309b4bc07) — Three-level architecture: metadata (100t) → body (5K) → resources (on demand). Industry convergence on this pattern.
- [Awesome Claude Skills — travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) — Confirms progressive disclosure as the standard architectural pattern across Claude.ai, Cursor, Codex, VS Code, LM-Kit.NET.
- [Complete skill builder guide — gist.github.com/joyrexus](https://gist.github.com/joyrexus/ff71917b4fc0a2cbc84974212da34a4a) — Anthropic's official PDF converted to Markdown. Chapter 3 on testing and iteration, Reference B on YAML frontmatter. Confirms `project-agnostic` and `allowed-tools` as production frontmatter fields.
- [AI News: Anthropic adds evaluation and A/B testing](https://www.ainews.com/p/anthropic-introduces-built-in-evaluation-and-benchmarking-for-claude-agent-skills-to-improve-enterpr) — Enterprise angle: benchmark mode detects silent regressions across model updates. Real use case for `aggregate_benchmark`.
