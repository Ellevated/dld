# MLP Scope - Day 1 Launch

## Constraints

- **Time:** 20 hours over 1 week (~3 hours/day)
- **Team:** Solo operation
- **Deadline:** 1 week (motivation drops after)

## MUST HAVE (Day 1 blockers)

### 1. English Translation
- All 20+ docs translated
- Complete replacement (Russian → .gitignore)
- README fully in English

**Estimate:** 6-8 hours (with Claude help)

### 2. Hero README
- Comparison prompt prominently placed
- "90% vs 6%" statistic in hero section
- Clear Quick Start (3 steps)
- Before/After examples

**Estimate:** 2 hours

### 3. Clean Template (no hardcode)
- Remove MCP-specific instructions
- Remove personal hooks config
- Universal out-of-the-box setup

**Estimate:** 3-4 hours

### 4. Refactor autopilot.md
- Currently 1000+ lines
- Must follow own principles (max 400 LOC)
- Split into logical sections

**Estimate:** 2-3 hours

### 5. Real-World Examples (2-3 projects)

| Project | Description |
|---------|-------------|
| marketplace-launch | New SKU launch for marketplaces |
| ai-autonomous-company | Autonomous company with AI agents |
| content-factory | Content workflow + portfolio site |

Each needs:
- README with story (what/why/results)
- DLD structure showcase
- Before/After if possible

**Estimate:** 4-5 hours

### 6. Code Review & Consistency
- Check all docs follow same format
- Verify links work
- Consistent terminology

**Estimate:** 2-3 hours

---

**Total Estimate:** ~20-25 hours - tight but realistic

## NICE TO HAVE (Day 2+)

- Video demo
- GitHub Discussions setup
- Starter templates for other stacks
- GLOSSARY.md (detailed terminology)
- COMPARISON.md (DLD vs alternatives)
- FAQ.md

## ANTI-SCOPE (Not Day 1)

- Product Hunt launch
- Bilingual structure (ru/ + en/)
- Multiple stack templates
- Community Discord/Slack

## Work Domains

### Domain 1: content
All written content
- Translate 20 docs
- Hero README
- Launch posts (HN, Reddit, Twitter, LinkedIn)

### Domain 2: structure
Code quality of repository
- Clean hardcode (MCP, hooks)
- Refactor autopilot.md
- Code review consistency
- GitHub templates (issues, PR)

### Domain 3: examples
Real-world demonstration
- 3 projects with descriptions
- Before/After if possible
- README for each example

### Domain 4: branding
Visual assets
- Comparison table as image
- Workflow diagram
- Badges for README
- (Optional) Logo

## Dependencies

```
structure (cleanup)
    ↓
content (docs translation) + examples (projects)
    ↓
branding (visuals for README)
    ↓
LAUNCH
```

## Repository Structure (Target)

```
dld/
├── README.md              # Hero: comparison prompt + stats + examples
├── LICENSE                # MIT
├── CONTRIBUTING.md        # How to contribute
├── CODE_OF_CONDUCT.md     # Community rules
│
├── docs/                  # 20 files (EN translated)
│   ├── foundation/
│   │   ├── 00-why.md
│   │   ├── 01-double-loop.md
│   │   └── 02-agent-roles.md
│   ├── 00-bootstrap.md
│   ├── 01-principles.md
│   └── ...
│
├── examples/              # Real-world projects
│   ├── marketplace-launch/
│   ├── ai-autonomous-company/
│   └── content-factory/
│
├── template/              # Ready to copy
│   ├── .claude/
│   │   ├── skills/
│   │   └── agents/
│   ├── ai/
│   ├── CLAUDE.md
│   └── README.md
│
└── .github/
    ├── ISSUE_TEMPLATE/
    └── PULL_REQUEST_TEMPLATE.md
```
