# Audit Night Mode

Automated nightly project scan triggered by `night-reviewer.sh`.
Faster than Deep mode: 2-3 personas, no Phase 0 inventory, JSON output.

**Trigger:** `/audit night`, cron via `night-reviewer.sh`
**Duration:** 10-20 min per project (vs 30-60 for deep mode)
**Output:** JSON array of findings (NOT prose report)

---

## Scope

Night mode uses 2-3 lightweight personas:

| Persona | Focus | Agent |
|---------|-------|-------|
| Coroner | Code bugs, tech debt, TODO/FIXME, dead code | `audit-coroner` |
| Scout | External integrations, security, API misuse | `audit-scout` |
| Archaeologist | Pattern violations, convention conflicts | `audit-archaeologist` (optional) |

**Skip:** Phase 0 inventory (too heavy for nightly), Geologist, Accountant, Cartographer.

---

## Self-Debate Pattern

For each potential finding, the persona must argue BOTH sides:

```
FINDING CANDIDATE: {description}
FOR: {why this is a real issue}
AGAINST: {why this might be false positive}
VERDICT: include (confidence: high) | include (confidence: medium) | exclude
```

**Rule:** Only include findings with confidence >= medium.

---

## Output Format

Each persona outputs a JSON array. The orchestrator (night-reviewer.sh) collects all arrays.

```json
[
  {
    "severity": "high",
    "confidence": "high",
    "file": "src/billing/service.py",
    "line": "42-48",
    "issue_type": "sql_injection",
    "description": "f-string in SQL query allows injection",
    "suggestion": "Use parameterized query with ? placeholders"
  }
]
```

### Field Rules

| Field | Values | Notes |
|-------|--------|-------|
| severity | `critical`, `high`, `medium`, `low` | Based on impact |
| confidence | `high`, `medium` | Low confidence = excluded by self-debate |
| file | relative path | From project root |
| line | `"42"` or `"42-48"` | Single line or range |
| issue_type | snake_case category | e.g., `sql_injection`, `dead_code`, `missing_error_handling` |
| description | 1-2 sentences | What the issue IS |
| suggestion | 1-2 sentences | How to fix it |

---

## ADR Compliance

- **ADR-007:** Personas return JSON in response, caller (night-reviewer.sh) writes to DB
- **ADR-008/009:** Personas run via `run_in_background: true` if invoked from Claude
- **ADR-010:** Night-reviewer.sh reads persona output directly (it's the orchestrator, not a Claude agent)

---

## Integration with Night Reviewer

```
night-reviewer.sh
  └─ claude --cwd {project} -p "/audit night" --output-format json --max-turns 30
      └─ Skill activates night-mode.md
      └─ 2-3 personas scan project
      └─ Output: JSON array to stdout
  └─ Parse JSON array
  └─ For each finding: db.py save-finding (INSERT OR IGNORE)
  └─ New findings → OpenClaw via event_writer.py
```

---

## Prompt for Personas

When dispatching personas in night mode, prepend this context:

```
MODE: night (automated nightly scan)
OUTPUT: JSON array ONLY — no prose, no markdown report
SELF-DEBATE: For each finding, argue for AND against before including
CONFIDENCE: Only include if confidence >= medium
DURATION: Keep scan focused, 5-10 min per persona
```
