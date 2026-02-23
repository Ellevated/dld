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

TARGET_PATH must be ABSOLUTE (e.g., `/Users/foo/dev/myapp/src/`). If user gives relative path, resolve it from project root.

### Compute Session Directory

Before launching any phase, compute SESSION_DIR once:

```
SESSION_DIR = ai/.triz/{YYYYMMDD}-{target_basename}
```

Where:
- `{YYYYMMDD}` = current date (e.g., `20260215`)
- `{target_basename}` = last path component of TARGET_PATH (e.g., `src`)

Example: TARGET `/Users/foo/dev/myapp/src` → SESSION_DIR `ai/.triz/20260215-src`

All file paths below use SESSION_DIR. Compute it ONCE, substitute into every prompt.

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store agent responses in orchestrator variables
⛔ NEVER pass full agent output in another agent's prompt
⛔ NEVER use TaskOutput to read agent results

✅ ALL Task calls use run_in_background: true
✅ Agents WRITE output to SESSION_DIR files
✅ File gates (Glob) verify completion between phases
✅ Orchestrator reads ONLY final report.md at the end
```

---

### Cost Estimate

Before launching Phase 1, inform user (non-blocking):

```
"TRIZ diagnostics: {TARGET} — 4 agents (1 sonnet + 3 opus), est. ~$1-3. Running..."
```

### Phase 1: Data Collection

```yaml
Task:
  subagent_type: triz-data-collector
  run_in_background: true
  description: "/triz: collect system metrics"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    OUTPUT_FILE: {SESSION_DIR}/metrics.yaml
```

**⏳ FILE GATE:** Wait for completion notification, then verify:
```
Glob("{SESSION_DIR}/metrics.yaml") → must exist
If missing: retry once, then abort.
```

### Phase 2: TOC Analysis

```yaml
Task:
  subagent_type: triz-toc-analyst
  run_in_background: true
  description: "/triz: TOC constraint analysis"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    METRICS_FILE: {SESSION_DIR}/metrics.yaml
    OUTPUT_FILE: {SESSION_DIR}/toc-analysis.yaml
```

**⏳ FILE GATE:** Wait for completion notification, then verify:
```
Glob("{SESSION_DIR}/toc-analysis.yaml") → must exist
If missing: retry once. If still failed, skip TOC — launch Phase 3 with TOC_FILE: UNAVAILABLE (degraded mode).
```

### Phase 3: TRIZ Analysis (AFTER Phase 2)

```yaml
Task:
  subagent_type: triz-triz-analyst
  run_in_background: true
  description: "/triz: TRIZ contradiction analysis"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    METRICS_FILE: {SESSION_DIR}/metrics.yaml
    TOC_FILE: {SESSION_DIR}/toc-analysis.yaml
    OUTPUT_FILE: {SESSION_DIR}/triz-analysis.yaml
```

**⏳ FILE GATE:** Wait for completion notification, then verify:
```
Glob("{SESSION_DIR}/triz-analysis.yaml") → must exist
If missing: retry once. If still failed, launch Phase 4 with only available inputs (degraded mode).
```

### Phase 4: Synthesis

```yaml
Task:
  subagent_type: triz-synthesizer
  run_in_background: true
  description: "/triz: synthesize recommendations"
  prompt: |
    TARGET: {TARGET_PATH}
    QUESTION: {QUESTION}
    METRICS_FILE: {SESSION_DIR}/metrics.yaml
    TOC_FILE: {SESSION_DIR}/toc-analysis.yaml
    TRIZ_FILE: {SESSION_DIR}/triz-analysis.yaml
    OUTPUT_FILE: {SESSION_DIR}/report.md
```

### Degraded Mode

If intermediate phases fail, continue with available data:

| Failed Phase | Action | Report Impact |
|-------------|--------|---------------|
| Phase 2 (TOC) | Launch Phase 3 with `TOC_FILE: UNAVAILABLE` | Report omits TOC section, notes "TOC analysis unavailable" |
| Phase 3 (TRIZ) | Launch Phase 4 with `TRIZ_FILE: UNAVAILABLE` | Report omits TRIZ section, recommendations from TOC only |
| Phase 2 + 3 | Launch Phase 4 with only metrics | Report = metrics summary + "Manual analysis recommended" |
| Phase 4 (Synth) | Read toc/triz YAML directly, present raw findings | No formatted report, show available analysis |

Synthesizer handles missing inputs: reads what exists, marks missing sections as `[UNAVAILABLE — Phase N failed]`.

### Present Results

After Phase 4, verify report exists with Glob `{SESSION_DIR}/report.md`, then read and present to user.
If report file is missing, present available partial results from earlier phases (see Degraded Mode).

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
- Session data: `{SESSION_DIR}/` (computed once before Phase 1, see "Compute Session Directory")
