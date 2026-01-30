# Tech: [TECH-052] Expand cspell dictionary

**Status:** done | **Priority:** P2 | **Date:** 2026-01-30

## Problem

`cspell.json` has only 5 words in its dictionary:
```json
"words": ["autopilot", "subagent", "worktree", "codebase", "DLD"]
```

The project uses many more technical terms that will trigger false positives:
- supabase, postgres, redis
- middleware, webhook, webhook
- typescript, fastapi, pydantic
- mermaid, markdownlint
- etc.

## Solution

Add common technical terms used in the project to cspell dictionary.

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `cspell.json` | modify | Expand word list |

## Tasks

### Task 1: Scan for technical terms

**Steps:**
1. Run cspell to see what words are flagged
2. Identify legitimate technical terms

### Task 2: Update cspell.json

**Files:** `cspell.json`

**Steps:**
1. Add technical terms commonly used in project:
   ```json
   "words": [
     "autopilot", "subagent", "worktree", "codebase", "DLD",
     "supabase", "postgres", "redis", "fastapi", "pydantic",
     "typescript", "middleware", "webhook", "mermaid",
     "markdownlint", "yamllint", "cspell", "ruff",
     "anthropic", "claude", "LLM", "LLMs",
     "async", "dataclass", "docstring",
     "backlog", "onboarding", "rollback",
     "Ellevated", "SSOT", "DAG"
   ]
   ```
2. Add ignorePaths for generated/external content if needed

**Acceptance:**
- [ ] Common terms don't trigger warnings
- [ ] No false negatives (real typos still caught)

## DoD

- [ ] CI spell-check passes
- [ ] Dictionary covers project vocabulary
