# Project Template

This folder is a ready-to-use project template. Copy it to start a new project.

## Usage

```bash
# 1. Create new project
mkdir my-project && cd my-project

# 2. Copy template (from wherever you keep it)
cp -r /path/to/ai/principles/_template/* .
cp -r /path/to/ai/principles/_template/.claude .

# 3. Start Claude Code
claude

# 4. Run bootstrap to unpack your idea
> /bootstrap
```

## What's Included

```
.claude/
├── skills/                 # Ready-to-use skills v3.0
│   ├── bootstrap/          # /bootstrap — idea discovery (Day 0)
│   ├── spark/              # /spark — ideation → spec (auto-handoff)
│   ├── autopilot/          # /autopilot — execution (worktree + fresh subagents)
│   ├── plan/               # plan subagent inside autopilot
│   ├── council/            # /council — 5 experts review
│   ├── review/             # /review — architecture watchdog
│   ├── reflect/            # /reflect — diary → CLAUDE.md rules
│   ├── audit/              # /audit — READ-ONLY code analysis
│   └── claude-md-writer/   # CLAUDE.md optimization
├── agents/                 # Subagent prompts
│   ├── autopilot/          # coder, tester, debugger, documenter, spec_reviewer
│   ├── council/            # 5 expert personas (Winston, Viktor, Amelia, John, Oracle)
│   └── review/             # code quality reviewer
└── settings.json           # Permissions + model

ai/
├── idea/             # Created by /bootstrap
├── principles/       # Reference docs (copy separately if needed)
├── features/         # Feature specs (created by spark)
├── diary/            # Session learnings (v3.0) → /reflect syncs to CLAUDE.md
├── decisions/        # ADR
├── backlog.md        # Task queue
└── ARCHITECTURE.md   # Domain graph, tables

CLAUDE.md             # Project instructions for LLM
```

## Workflow v3.0

```
New project: /bootstrap → Day 1 structure → /spark first feature
Feature:     /spark → /autopilot (plan is subagent, auto-handoff)
Bug:         diagnose (5 Whys) → /spark → /autopilot
Complex:     /spark → /council → /autopilot
Hotfix:      <5 LOC → fix directly (no spark)
```

**Key changes in v3.0:**
- Spark auto-hands off to autopilot (no manual "plan" step)
- Autopilot always uses worktree (isolation)
- Fresh subagent per task (context stays clean)
- Model routing (opus for plan/debug, sonnet for coding)
- Diary captures learnings → /reflect synthesizes rules

## After Bootstrap

1. Update `CLAUDE.md` with your project details
2. Create `src/domains/` structure based on `ai/idea/architecture.md`
3. Create `.claude/contexts/` for each domain
4. Create `ai/backlog.md` for task queue
5. Run `/spark` for your first feature

## Reference

Full documentation: `ai/principles/` (copy separately if needed)
