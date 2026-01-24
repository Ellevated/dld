---
name: tester
description: Run tests with Smart Testing and Scope Protection
agent: .claude/agents/tester.md
---

# Tester Skill (Wrapper)

Invokes tester subagent for running tests with Smart Testing logic.

> **Architecture:** This skill is a WRAPPER over `.claude/agents/tester.md`.
> The agent file is the source of truth for the tester prompt.

## When to Use

**Internal:** Called by autopilot after coder completes task

**Standalone:** Manual testing of specific changes

## Invocation

```yaml
Task tool:
  description: "Test changes"
  subagent_type: "tester"
  prompt: |
    FILES CHANGED: {list}

    Run Smart Testing based on file types.
    Return: test results with ACTUAL OUTPUT.
```

## Smart Testing

**SSOT:** `.claude/agents/tester.md#smart-testing`

## Output

```yaml
status: passed | failed
test_output: "Actual pytest output"
in_scope_failures: [list]
out_of_scope_failures: [list]
```

## Notes

- Tester uses Scope Protection — only fails for in-scope tests
- Out-of-scope failures are logged but don't block commit
