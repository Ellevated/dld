# Step 0: Bootstrap

## Philosophy

These principles are the result of hundreds of hours of trial and error. They work because:

1. **LLM understands structure** — colocation, flat, self-describing names
2. **Guardrails prevent chaos** — CI checks, immutable tests
3. **Skills provide workflow** — no need to think "what to do next"

But principles are useless without understanding **what you're building**.

---

## Order of launching a new project

```
Step 0: Read this file (5 min)
     ↓
Step 1: /bootstrap — unpacking the idea with Claude (60-90 min)
     ↓
     → ai/idea/vision.md
     → ai/idea/domain-context.md
     → ai/idea/product-brief.md
     → ai/idea/architecture.md
     ↓
Day 1: Project structure (09-onboarding.md)
     ↓
Day 2+: /spark for the first feature
```

---

## Checklist "Ready for /bootstrap"

- [ ] Have an idea (even a vague one)
- [ ] Created an empty project folder
- [ ] Ran `npx create-dld` or installed DLD manually
- [ ] Launched Claude Code in the project folder
- [ ] Ready to spend 60-90 minutes on an honest conversation

---

## What /bootstrap does

**This is NOT a questionnaire.** This is an interactive session with a product partner.

| Phase | What happens | Who leads |
|-------|--------------|-----------|
| 0. Founder | Motivations, experience, constraints | Claude asks |
| 1-4. Idea | Persona, pain, solution | Claude digs deeper |
| 5-6. Business | Money, competitors, advantage | Jointly |
| 7-8. Scope | MLP, terminology dictionary | Claude cuts excess |
| 9. Synthesis | Understanding check | Claude summarizes |
| 10. Architecture | Domains, dependencies | **Claude proposes** |
| 11. Documentation | 4 files | Claude creates |

**Key point:** Claude will be "annoying" — clarifying vague points, returning to contradictions, not skipping "details".

---

## Result of /bootstrap

```
ai/idea/
├── vision.md           # Why the project, founder, success
├── domain-context.md   # Industry, persona, dictionary
├── product-brief.md    # MLP, scope, monetization, assumptions
└── architecture.md     # Domains, dependencies, entry points
```

---

## Checklist "Ready for Day 1"

After `/bootstrap` you should have:

- [ ] **vision.md** — clear why we're doing this
- [ ] **domain-context.md** — clear understanding of the world and persona
- [ ] **product-brief.md** — clear MLP scope (3-5 features)
- [ ] **architecture.md** — clear domains (3-5 of them)
- [ ] North Star metric defined
- [ ] Assumptions documented
- [ ] Yellow flags recorded

**Not ready if:**
- "For everyone" — no specific persona
- "Everything is needed" — no prioritization
- "We'll figure it out later" — critical unknowns not documented

---

## After bootstrap: Day 1

```bash
# 1. Create structure based on architecture.md
mkdir -p src/domains/{domain1,domain2,domain3}
mkdir -p src/{shared,infra,api}
mkdir -p .claude/{contexts,skills}
mkdir -p tests/{integration,contracts,regression}

# 2. Create CLAUDE.md from ai/idea/* files
# (Claude will help based on 04-claude-md-template.md)

# 3. Create backlog
touch ai/backlog.md

# 4. First feature
/spark {first feature from architecture.md}
```

---

## Minimal set for copying to a new project

```
ai/
├── idea/               # Created by /bootstrap
│   ├── vision.md
│   ├── domain-context.md
│   ├── product-brief.md
│   └── architecture.md
└── backlog.md          # Task queue

.claude/
├── skills/             # Installed by create-dld
│   └── bootstrap/SKILL.md
└── settings.json       # Configure
```

---

## What to read

**Before /bootstrap (5 min):**
- This file

**After /bootstrap, before Day 1 (15 min):**
- `docs/01-principles.md` -- understand the philosophy
- `docs/03-project-structure.md` -- understand the structure

**As needed:**
- Other documents in `docs/` -- reference material
