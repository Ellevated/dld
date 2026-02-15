# /triz — System-Level Diagnostics with TOC + TRIZ

System health analysis using Theory of Constraints + TRIZ at the architecture level.

**Activation:**
- `/triz` — direct command
- `/triz src/domains/` — analyze specific path
- `/triz src/ "why do deploys break?"` — with specific question

## When to Use

- System feels "sick" — bugs keep recurring in the same area
- Need to find architectural bottleneck, not individual bugs
- Want to understand hidden coupling between modules
- Planning major refactoring — where to start?
- Monthly health check

**Don't use:** For individual bugs (use `/spark` or `/spark bug-hunt`).

## Principles

1. **STRATEGIC, not tactical** — output is "extract module X", not "fix null check in line 42"
2. **DATA-DRIVEN** — git history, churn metrics, co-change patterns as input
3. **SEQUENTIAL** — TRIZ reads TOC output (not parallel), for informed contradictions
4. **READ-ONLY** — produces report only, no code changes
5. **FULLY AUTOMATIC** — no confirmations, no AskUserQuestion

## Pipeline

```
/triz [target_path] [question]
  │
  Phase 1: DATA COLLECTION (sonnet)
  ├── git log → file change frequency (6 months)
  ├── co-change analysis → files that change together
  ├── LOC per module/directory
  ├── architecture.md, CLAUDE.md, dependency maps
  ├── test coverage per module
  └── Output: metrics YAML
  │
  Phase 2: TOC ANALYST (opus, sequential)
  ├── Input: Phase 1 metrics
  ├── Module-level UDEs
  ├── Current Reality Tree
  ├── Core constraint (physical/policy/paradigm)
  ├── Evaporating Clouds
  └── Exploitation/Elevation strategy
  │
  Phase 3: TRIZ ANALYST (opus, sequential after TOC)
  ├── Input: Phase 1 metrics + Phase 2 TOC output
  ├── Ideal Final Result
  ├── Technical & physical contradictions
  ├── Separation principles → architecture patterns
  └── 40 inventive principles → concrete suggestions
  │
  Phase 4: SYNTHESIZER (opus)
  ├── Merge TOC constraint + TRIZ resolutions
  ├── Prioritize by leverage (Meadows' leverage points)
  └── Output: system health report markdown
```

## Execution

### Parse Arguments

```
/triz                          → TARGET = project root, QUESTION = "system health"
/triz src/domains/billing      → TARGET = src/domains/billing, QUESTION = "system health"
/triz src/ "why do deploys?"   → TARGET = src/, QUESTION = "why do deploys break?"
```

### Phase 1: Data Collection

```yaml
Task:
  subagent_type: triz-data-collector
  description: "/triz: collect system metrics"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    OUTPUT_FILE: ai/.triz/{YYYYMMDD}-{target_basename}/metrics.yaml
```

### Phase 2: TOC Analysis

```yaml
Task:
  subagent_type: triz-toc-analyst
  description: "/triz: TOC constraint analysis"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    METRICS_FILE: ai/.triz/{session}/metrics.yaml
    OUTPUT_FILE: ai/.triz/{session}/toc-analysis.yaml
```

### Phase 3: TRIZ Analysis (AFTER Phase 2)

```yaml
Task:
  subagent_type: triz-triz-analyst
  description: "/triz: TRIZ contradiction analysis"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    METRICS_FILE: ai/.triz/{session}/metrics.yaml
    TOC_FILE: ai/.triz/{session}/toc-analysis.yaml
    OUTPUT_FILE: ai/.triz/{session}/triz-analysis.yaml
```

### Phase 4: Synthesis

```yaml
Task:
  subagent_type: triz-synthesizer
  description: "/triz: synthesize recommendations"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    METRICS_FILE: ai/.triz/{session}/metrics.yaml
    TOC_FILE: ai/.triz/{session}/toc-analysis.yaml
    TRIZ_FILE: ai/.triz/{session}/triz-analysis.yaml
    OUTPUT_FILE: ai/.triz/{session}/report.md
```

### Present Results

After Phase 4, read the report at OUTPUT_FILE and present to user.

Suggest next steps:
- `/spark` spec for top recommendation
- `/council` debate on controversial recommendation
- `/spark bug-hunt {module}` for tactical fixes in constrained module

## Output Format

The synthesizer writes a markdown report. See `synthesizer.md` for format.

## Rules

- **READ-ONLY** — no code modifications
- **No backlog entries** — report is informational, user decides what to do
- **No commits** — report stays in ai/.triz/ (gitignored)
- **Fully automatic** — no AskUserQuestion, no confirmation prompts
- Session data: `ai/.triz/{YYYYMMDD}-{target_basename}/`
