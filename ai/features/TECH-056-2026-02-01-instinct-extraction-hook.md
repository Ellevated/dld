# Tech: [TECH-056] Instinct Extraction Hook (Auto-Learning)

**Status:** closed (duplicate) | **Priority:** — | **Date:** 2026-02-01

## Closure Note

**Closed:** 2026-02-02 | **Reason:** Duplicate of existing functionality

Система auto-learning уже реализована:
- `diary-recorder` agent — автозапись проблем/успехов во время Autopilot
- `ai/diary/` — хранилище записей
- `/reflect` — синтез diary → CLAUDE.md rules
- `session-end.sh` — напоминание при >5 pending entries

Предложенный подход (Claude API call на каждый коммит) — оверкил:
1. Дорого и медленно (API call на каждый коммит)
2. Claude анализирует свою же работу — бессмысленно
3. Дублирует diary в другом формате

**Альтернатива:** Если нужны улучшения — расширить триггеры в `diary-recorder`.

---

## Why (original)

Current `/reflect` requires manual diary reading and rule synthesis. Industry leaders (everything-claude-code) auto-extract patterns from git history. This makes learning continuous and reduces human effort.

## Context

Current flow:
- Problems captured in `ai/diary/`
- Human runs `/reflect` periodically
- Human writes rules to CLAUDE.md

Industry 2026:
- Git diff analyzed after each commit
- Patterns auto-extracted to `ai/instincts/`
- `/reflect` merges instincts → CLAUDE.md rules

---

## Scope

**In scope:**
- Post-commit hook that extracts patterns from git diff
- New `ai/instincts/` directory structure
- Pattern extraction prompt for hook
- Integration with existing `/reflect`

**Out of scope:**
- Auto-applying instincts to CLAUDE.md (human approval needed)
- Cross-project instinct sharing
- ML-based pattern recognition

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/hooks/post_commit.py` | create | New hook |
| 2 | `template/.claude/settings.json` | modify | Register hook |
| 3 | `template/.claude/skills/reflect/SKILL.md` | modify | Read instincts |
| 4 | `template/ai/instincts/.gitkeep` | create | Directory structure |

**New files allowed:**
| # | File | Reason |
|---|------|--------|
| 1 | `template/.claude/hooks/post_commit.py` | Extraction hook |
| 2 | `template/ai/instincts/.gitkeep` | Directory placeholder |

---

## Approaches

### Approach 1: Shell Script Hook

**Source:** Unix simplicity

**Summary:** Bash script that runs `git diff HEAD~1` and pipes to Claude API

**Pros:**
- Simple
- No Python dependency

**Cons:**
- Hard to parse complex diffs
- Can't use Claude Code tools

### Approach 2: Python Hook with LLM Analysis

**Source:** everything-claude-code pattern

**Summary:** Python hook runs after commit, sends diff to Claude for pattern extraction, saves to ai/instincts/

**Pros:**
- Can use sophisticated prompting
- Structured output
- Integration with existing Python hooks

**Cons:**
- Requires API call (cost)
- Slower

### Approach 3: Lightweight Heuristics Only

**Source:** Internal analysis

**Summary:** Python hook extracts patterns via regex/AST without LLM

**Pros:**
- Free, fast
- No API dependency

**Cons:**
- Limited pattern recognition
- Can't understand intent

### Selected: Approach 2

**Rationale:** The value is in understanding WHY something was done, not just WHAT. LLM analysis required for meaningful instincts.

---

## Design

### Instinct File Format

```markdown
# Instinct: {date}-{short-hash}

**Source:** Commit {hash} on {date}
**Task:** {TECH-XXX or description}

## Pattern Detected

{What the change did}

## Learning

{Why this pattern is important}

## Rule Candidate

```
{Proposed rule for CLAUDE.md}
```

## Confidence

{high/medium/low} — {reasoning}
```

### Directory Structure

```
ai/instincts/
├── 2026-02-01-abc1234.md
├── 2026-02-01-def5678.md
└── _archive/  # Old instincts after reflection
```

### Hook Trigger

```json
// settings.json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "bash -c 'if [[ \"$TOOL_INPUT\" == *\"git commit\"* ]]; then python3 .claude/hooks/post_commit.py; fi'",
          "timeout": 30000
        }
      ]
    }
  ]
}
```

---

## Implementation Plan

### Task 1: Create instincts directory

**Files:**
- Create: `template/ai/instincts/.gitkeep`

**Steps:**
1. Create directory structure
2. Add to template

**Acceptance:**
- [ ] Directory exists in template

### Task 2: Create post-commit hook

**Files:**
- Create: `template/.claude/hooks/post_commit.py`

**Steps:**
1. Detect git commit in Bash tool output
2. Run `git diff HEAD~1`
3. Send to Claude with extraction prompt
4. Save instinct to ai/instincts/

**Acceptance:**
- [ ] Hook extracts patterns from commits
- [ ] Instinct files created correctly

### Task 3: Register hook in settings

**Files:**
- Modify: `template/.claude/settings.json`

**Steps:**
1. Add PostToolUse hook for Bash
2. Filter for git commit commands

**Acceptance:**
- [ ] Hook triggers on git commit

### Task 4: Update reflect skill

**Files:**
- Modify: `template/.claude/skills/reflect/SKILL.md`

**Steps:**
1. Add step to read ai/instincts/
2. Merge instinct rule candidates with diary insights
3. Archive processed instincts

**Acceptance:**
- [ ] Reflect reads instincts
- [ ] Processed instincts archived

### Execution Order

Task 1 → Task 2 → Task 3 → Task 4

---

## Definition of Done

### Functional
- [ ] Commits trigger instinct extraction
- [ ] Instinct files have correct format
- [ ] Reflect incorporates instincts

### Technical
- [ ] Hook doesn't block commit (async or fast)
- [ ] Graceful failure if API unavailable

### Documentation
- [ ] Instinct format documented
- [ ] Hook purpose documented

---

## Autopilot Log

*(Filled by Autopilot during execution)*
