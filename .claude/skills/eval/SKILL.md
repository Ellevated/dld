# /eval — Agent Prompt Eval Suite

Evaluate DLD agent prompts against golden datasets using LLM-as-Judge scoring.

## Commands

- `/eval agents` — run evals for all agents with golden datasets
- `/eval agents {name}` — run evals for a specific agent (e.g., `devil`, `planner`, `coder`)
- `/eval report` — show last eval report

## Pre-flight

1. Verify `test/agents/` directory exists
2. Run `node .claude/scripts/eval-agents.mjs` to get task list
3. If empty → report "No golden datasets found in test/agents/"

## Flow

### `/eval agents` or `/eval agents {name}`

```
Step 1: Scan golden datasets
  node .claude/scripts/eval-agents.mjs [agent-name]
  → JSON array of eval tasks

Step 2: For each eval task
  a. Read agent prompt: {task.agent_path}
  b. Read golden input: {task.input_path}
  c. Dispatch agent with input:
     Task tool:
       subagent_type: {task.subagent_type}
       prompt: |
         {content of golden input file}
  d. Capture actual output from agent response
  e. Read rubric: {task.rubric_path}
  f. Dispatch eval-judge:
     Task tool:
       subagent_type: "eval-judge"
       prompt: |
         criterion_id: "{task.agent}-{task.golden_id}"
         input: "{golden input summary}"
         actual_output: |
           {captured agent output}
         rubric: |
           {rubric file content}
         threshold: {task.threshold}

Step 3: Aggregate results
  - Group scores by agent
  - Calculate average per dimension
  - Calculate overall pass/fail per agent

Step 4: Write report
  → test/agents/eval-report.md
```

### `/eval report`

Read and display `test/agents/eval-report.md`.
If not found → "No eval report found. Run `/eval agents` first."

## Report Format

```markdown
# Agent Eval Report — {date}

## Summary

| Agent | Golden Pairs | Avg Score | Pass Rate | Status |
|-------|-------------|-----------|-----------|--------|
| devil | 1/1 | 0.82 | 100% | PASS |
| planner | 1/1 | 0.75 | 100% | PASS |
| coder | 0/1 | 0.55 | 0% | FAIL |

## Detail: devil

### golden-001
- Score: 0.82 (threshold: 0.7) — PASS
- Completeness: 0.9 | Accuracy: 0.8 | Format: 0.8 | Relevance: 0.85 | Safety: 0.75
- Reasoning: "..."

## Detail: planner
...

## Detail: coder
...
```

## Rules

- Each agent eval is independent — one failure doesn't block others
- Report is overwritten on each run (not appended)
- Golden datasets are in `test/agents/{agent}/`
- Reference outputs (`golden-NNN.output.md`) are for human review, NOT for automated comparison
- Scoring uses rubric only (not output matching)
- Threshold defaults to 0.7 if not specified in config.json

## Adding Golden Datasets

To add a new golden pair for an agent:

1. Create `test/agents/{agent}/golden-NNN.input.md` — the task/prompt for the agent
2. Create `test/agents/{agent}/golden-NNN.output.md` — reference output (for humans)
3. Create `test/agents/{agent}/golden-NNN.rubric.md` — scoring rubric for eval-judge
4. Update `config.json` if needed

To add a new agent to eval:

1. Create `test/agents/{agent}/config.json` with agent metadata
2. Add at least one golden pair (golden-001)
3. Run `/eval agents {agent}` to verify
