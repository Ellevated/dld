# Escalation & Limits

When to escalate and how to handle failures.

## Limits

| Situation | Limit | After Limit |
|-----------|-------|-------------|
| Debug retry (code bug) | 3 | → Spark (BUG spec) |
| Debug retry (architecture) | 3 | → Council |
| ./test fast fail | 5 | → STOP (ask human) |
| ./test llm fail | 2 | → STOP (ask human) |
| Reviewer refactor | 2 | → Council |
| Heavy drift (planner) | 0 | → Council (immediate) |
| Out-of-scope failures | ∞ | skip |

## Decision Tree

After debug/refactor limits exhausted:

```
After 3 debug attempts:
├── Is it a CODE BUG in current scope?
│   └── YES → Spark (create BUG-XXX spec)
│       └── "Bug requires separate spec."
│
├── Is it an ARCHITECTURE question?
│   └── YES → Council (expert review)
│       └── "Architecture question."
│
├── Is it OUT OF SCOPE?
│   └── YES → Log + Continue
│       └── "Out-of-scope. Skipping."
│
└── UNCLEAR?
    └── STOP → Ask Human
        └── "Cannot determine. Need help."

Heavy drift detected by Planner:
├── Files/functions deleted?
│   └── YES → Council (immediate)
│       └── "Spec assumptions invalid."
│
├── API incompatible changes?
│   └── YES → Council (immediate)
│       └── "API changed since spec."
│
└── >50% of Allowed Files changed?
    └── YES → Council (immediate)
        └── "Major codebase changes."
```

## Spark Escalation (for bugs)

When code bug can't be fixed after 3 attempts:

```yaml
Skill tool:
  skill: "spark"
  args: |
    MODE: bug
    SYMPTOM: "{test failure or error}"
    ATTEMPTS: [list of what was tried]
    FILES: [files_changed]
```

**Spark will:**
1. Run 5 Whys analysis
2. Find root cause
3. Create BUG-XXX spec
4. Hand off to autopilot (fresh context)

## Council Escalation (for architecture)

When architecture decision needed:

```yaml
Skill tool:
  skill: "council"
  args: |
    escalation_type: debug_stuck | refactor_stuck | heavy_drift
    feature: "{TASK_ID}"
    task: "{N}/{M} — {name}"
    attempts:
      - attempt: 1
        action: "what did"
        result: "what got"
    current_error: "..."
    hypotheses_rejected:
      - hypothesis: "..."
        reason: "..."
    question: "Specific question"
```

### Heavy Drift Escalation Template

When Planner detects heavy drift:

```yaml
Skill tool:
  skill: "council"
  args: |
    escalation_type: heavy_drift
    spec_path: "{spec_path}"
    drift_report:
      deleted_files: [...]
      incompatible_apis: [...]
      removed_deps: [...]
      percent_changed: N%
    question: "Spec assumptions no longer valid. Should we: (a) rewrite spec, (b) adapt approach, (c) reject task?"
```

**Council returns:**
- `rewrite_spec` → Spark creates new spec, old one archived
- `adapt_approach` → Council provides adapted solution, Planner updates tasks
- `reject_task` → Status: blocked, reason logged

**Council returns:**
- `solution_found` → apply fix, continue
- `architecture_change` → update plan, restart task
- `needs_human` → status: blocked

## Debug Loop

```
TESTER fails:
├── In-scope? (related to files_changed)
│   └── YES → DEBUGGER → CODER fix → TESTER
│   └── NO → Log "out-of-scope" → Skip
│
├── retry_count > 1?
│   └── YES → DIARY RECORDER (test_retry trigger)
│
└── retry_count >= 3?
    └── YES → ESCALATE (see Decision Tree)
```

## Refactor Loop

```
CODE QUALITY REVIEWER returns needs_refactor:
├── refactor_count < 2?
│   └── YES → CODER fix → TESTER → REVIEWER
│
└── refactor_count >= 2?
    └── → Council escalation
```

## Diary Recording

**Triggers:**
- `bash_instead_of_tools` — used bash when tool exists
- `test_retry > 1` — needed multiple debug attempts
- `escalation_used` — escalated to Spark/Council

**When:** After DEBUG LOOP (if retry > 1) or after escalation.

```yaml
Task tool:
  subagent_type: "diary-recorder"
  prompt: |
    task_id: "{TASK_ID}"
    problem_type: {trigger}
    error_message: "{error}"
    files_changed: [...]
```

## Blocked Status

When to set status=blocked:

- Deploy validation failed
- Spec Reviewer loop > 2 iterations
- Unclear requirements
- Human decision needed
- Git conflicts

**Always update BOTH spec AND backlog!**
