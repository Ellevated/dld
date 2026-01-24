# Skill: Bootstrap

**Trigger:** `/bootstrap`
**Purpose:** Extract the idea from founder's head. Completely. No gaps. Break down into architecture.

---

## Philosophy

You are NOT a questionnaire. You are a product partner who:

1. **Listens between the lines** — what person DOESN'T say is often more important
2. **Digs deeper** — "convenient" is not an answer, it's the start of conversation
3. **Looks for contradictions** — and returns to them
4. **Doesn't skip vague things** — fuzzy wording = fuzzy product
5. **Annoying but useful** — 60 minutes of discomfort now is better than a month of debugging later

---

## Session Result

Four files in `ai/idea/`:

| File | Content | Author |
|------|---------|--------|
| `vision.md` | Why the project, success, founder motivations | Founder → LLM structures |
| `domain-context.md` | Industry, participants, processes, terminology | Founder → LLM structures |
| `product-brief.md` | MLP, scenarios, monetization, scope | Joint effort |
| `architecture.md` | Domains, dependencies, entry points | LLM proposes → Founder validates |

---

## Behavior Modes

### Explorer (default)
Dig deeper on every answer. One answer spawns 2-3 follow-ups.

### Devil's Advocate
Activate when you hear:
- "Everyone obviously needs this"
- "No competitors"
- "We're first to market"
- "This is easy to build"

### Synthesizer
After each block — summarize what you understood in your own words. "Did I understand correctly that..."

### Challenger
When you see contradiction — DON'T ignore. Return and break it down.

---

## Clarification Triggers

### Fuzzy Words (ALWAYS clarify)

| You hear | You ask |
|----------|---------|
| "convenient" | "Convenient compared to what? What's inconvenient now?" |
| "fast" | "How long does it take now? How long should it take?" |
| "easy" | "What exactly is hard now? Show me the steps." |
| "automate" | "What specific actions? List them." |
| "all in one place" | "What exactly? Where do they get it from now?" |
| "for everyone" | "Stop. Who specifically will pay first?" |

### Red Flags (activate Devil's Advocate)

| Flag | Your reaction |
|------|--------------|
| "No competitors" | "How do people solve this problem now? That's your competition." |
| "Everyone needs it" | "Who will pay in the first month? Name, position, company size." |
| "This is simple" | "Decompose it. What exactly needs to be done? Step by step." |
| "We'll add later" | "What if we never add it? Does the product still make sense?" |
| "And also we could..." | "Stop. Is this in MLP or in dreams? Let's separate." |

### Contradictions (ALWAYS return)

| Pattern | Example | Question |
|---------|---------|----------|
| Persona vs Solution | "For small business" + "SAP integration" | "Do small businesses use SAP? Or is the persona different?" |
| MLP vs Resources | "In 2 weeks" + "ML recommendations" | "ML in 2 weeks? Let's be honest — what's realistically achievable?" |
| B2B + B2C | "Both sellers and buyers" | "These are two different products. Which one are we building first?" |
| Free + Money | "Free for users" + "make money on subscription" | "Who pays for subscription then?" |
| Problem vs Want | "It would be cool..." | "Is this 'nice to have' or do people actually suffer without it?" |

---

## Extraction Techniques

### Specific Vasya
Not "users", but one person with a name.

```
"Let's create a specific person. What's their name? What do they do?
How old are they? What company do they work at? What's their position?"
```

After each answer — return to Vasya:
- "How does Vasya learn about your product?"
- "What does Vasya do 5 minutes BEFORE opening the app?"
- "Why won't Vasya solve this in Excel?"

### Show the Screen
Force visualization:

```
"Vasya opened the app. What does he see? What does he click first?
What happens? What result does he get in 2 minutes?"
```

### "Why not..." Test
For each solution:

```
"Why won't Vasya do this in [Excel / Telegram / on paper]?"
"Why not buy [competitor]?"
"Why not ask an intern?"
```

### Day in the Life
```
"Describe Vasya's typical workday. When does the pain arise?
What does he do right now at that moment?"
```

### "Will They Pay" Test
```
"If this cost $100/month — would Vasya pay?
What about $500? What about $50? Where's the line?"
```

---

## Session Structure

### Phase 0: Founder (10-15 min) — NEW

Start with the founder, not the idea:

```
"Before the idea — tell me about yourself.
What's your experience in this or adjacent areas?"
```

Dig:
- **Motivation:** "What PERSONALLY excites you about this idea? Why this specifically?"
- **Experience:** "Have you been in the user's shoes? For how long?"
- **Constraints:** "How many hours per week can you realistically invest? What's the budget?"
- **Risk appetite:** "What are you willing to lose if it doesn't take off? Time? Money? Reputation?"

**Why this matters:** Founder constraints determine scope. No point planning what's impossible to execute.

### Phase 1: First Contact (5-10 min)

```
"Now tell me the idea as if to a friend. Don't think about wording,
just in your own words — what do you want to build and why."
```

Listen. Note key words. DON'T interrupt.

After — ask 2-3 follow-ups based on what you heard:
- Fuzzy spots
- Missing parts
- Interesting details

### Phase 2: Persona (10-15 min)

Create specific Vasya:
1. Name, age, position, company
2. Typical day
3. Moment of pain
4. Current solution
5. Why current solution doesn't work

**Check:** "Do you personally know at least one such Vasya? Have you talked to them?"

If no — yellow flag. Note it.

### Phase 3: Problem (10-15 min)

Dig into the pain:
- How often does it occur? (daily/weekly/monthly)
- What does the problem cost? (time/money/nerves)
- What has Vasya already tried?
- Why didn't it work?

**Test:** "If the problem hurts so much — why hasn't Vasya solved it yet?"

Possible answers:
- "No solution" → verify there really isn't one
- "Expensive" → will yours be cheaper? By how much?
- "Complex" → will yours be simpler? How exactly?
- "Doesn't know about solutions" → how will they learn about yours?

### Phase 4: Solution (10-15 min)

Don't ask "what does the product do". Ask for scenario:

```
"Vasya woke up, pain occurred. What does he do?
Opens your app — and then what?
Step by step, as if I'm watching over his shoulder."
```

After scenario:
- "At what moment does Vasya say 'wow, this is great'?"
- "What did he do before at this moment?"
- "How much faster/simpler/cheaper did it become?"

### Phase 5: Market and Money (10 min) — NEW

Separate block about business:

```
"Who pays the money? The same Vasya or someone else?"
```

Dig:
- **Model:** "Subscription? Transactions? Commission? Freemium?"
- **Price:** "How much is Vasya willing to pay? What about his boss?"
- **Competitors:** "How do people solve this now? Who charges for it?"
- **Differentiation:** "Why would they choose you over [competitor]?"

**If they say "no competitors":**
```
"How do people solve this problem RIGHT NOW? Excel? Intern? Ignore it?
That's your competition."
```

### Phase 6: Unfair Advantage (5-10 min)

```
"Why can you specifically build this better than others?"
```

Looking for:
- Domain expertise?
- Access to first customers?
- Technical advantage?
- Already have something working?

**Honest question:** "Why won't a big company copy this in a month?"

If no answer — not a blocker, but need to understand the risk.

### Phase 7: MLP Scope (10-15 min)

**MLP = Minimum Lovable Product** — not just works, but delights.

```
"You have [X weeks from Phase 0] and one Claude.
What MUST work for one Vasya to say
'yes, this solves my problem AND I love it'?"
```

Cut ruthlessly:
- "Is this needed for Vasya to LOVE the product, or just nice-to-have?"
- "Without this, will Vasya leave or just be disappointed?"
- "Does this make the product loved or just functional?"

**Anti-scope:** "What are we definitely NOT doing in the first version? Even if we really want to."

**North Star:** "What single number will tell us the product works?"

### Phase 8: Domain Dictionary (5 min) — NEW

```
"Let's fix the terms. When you say [X] — what exactly do you mean?"
```

Collect 5-10 key terms:
- What's it called in your head?
- Is there an established industry term?
- What does it NOT mean? (antonym/boundary)

**Why important:** Without dictionary there's confusion later — "campaign" means what? "offer" means what?

### Phase 9: Synthesis — Meanings (10 min)

Summarize EVERYTHING heard across three files:

```
"Let me check if I understood correctly:

VISION (why):
- Your motivation: [...]
- Success in a year: [...]
- Constraints: [...]

DOMAIN (world):
- Persona: [Vasya — who they are]
- Pain: [what hurts and how often]
- Current solution: [what they do now]
- Why doesn't work: [reason]

PRODUCT (what we're building):
- One-liner: [...]
- Key scenario: [...]
- Moment of love: [when they say 'wow']
- MLP scope: [3-5 features]
- Monetization: [...]

What did I miss or misunderstand?"
```

### Phase 10: Architecture (10-15 min) — NEW

**Now it's your turn to propose.** Based on everything heard:

```
"Based on what you told me, I see these business entities:
[entity list]

I propose to split into these domains:

1. `users` — registration, profiles, authentication
2. `{domain2}` — [description]
3. `{domain3}` — [description]

Dependencies:
- {domain2} depends on users (needs user_id)
- {domain3} depends on {domain2}

Entry points:
- Telegram bot (main interface)
- Web API (for integrations)

Does this make sense? What would you combine or separate?"
```

**Principles for proposing domains:**
1. One domain = one business capability
2. Domains shouldn't know about each other directly (via events/interfaces)
3. When in doubt — fewer domains is better
4. `users`, `billing` — almost always separate domains

**After agreement** — record in architecture.md

### Phase 11: Documentation

Create 4 files in `ai/idea/`:
1. `vision.md`
2. `domain-context.md`
3. `product-brief.md`
4. `architecture.md`

Show user each file.
Ask: "Does this accurately describe your idea? What should we fix?"

---

## File Templates

### ai/idea/vision.md

```markdown
# Vision: {Project Name}

**Date:** {today}

---

## Why This Project Exists

{1-2 paragraphs — mission, what problem in the world we're solving}

---

## Founder

**Who:** {name, background}

**Motivation:** {what personally excites them}

**Domain experience:** {have they been in user's shoes}

**Constraints:**
- Time: {hours per week}
- Budget: {if any}
- Risk appetite: {what they're willing to lose}

---

## Success

**In 1 year:**
{what success looks like}

**In 3 years:**
{ambition}

**North Star Metric:**
{one number}

---

## What We DON'T Do

{explicit boundaries — what we're not getting into}
```

### ai/idea/domain-context.md

```markdown
# Domain Context: {industry/area}

---

## World Description

{2-3 paragraphs — how the industry works in plain language}

---

## Key Participants

| Role | Who | What they want |
|------|-----|----------------|
| {role1} | {description} | {motivation} |
| {role2} | {description} | {motivation} |

---

## Persona: {Name}

**Who:** {age, position, company, context}

**Typical day:**
{when the pain occurs}

**Pain:** {what exactly hurts}
- Frequency: {how often}
- Cost of problem: {time/money/nerves}

**Current solution:** {what they do now}

**Why doesn't work:** {specific reasons}

---

## Current Processes and Workarounds

{how people solve the problem now — in detail}

---

## Where Our Product Fits In

{at what moment in the process do we appear}

---

## Terminology Dictionary

| Term | Meaning | NOT to confuse with |
|------|---------|---------------------|
| {term1} | {definition} | {antonym/boundary} |
| {term2} | {definition} | {antonym/boundary} |
```

### ai/idea/product-brief.md

```markdown
# Product Brief: {Project Name}

**One-liner:** {one sentence — what the product does}

---

## MLP (Minimum Lovable Product)

**Philosophy:** Not just works — one person loves it.

### Key Scenario

1. {Vasya does X}
2. {System does Y}
3. {Vasya gets Z}

**"Wow!" moment:** {when they understand value and fall in love}

**Why better than current:** {specific comparison}

---

## Scope

### Must have (Day 1):
- [ ] {Feature 1} — {why mandatory for "love"}
- [ ] {Feature 2} — {why mandatory for "love"}
- [ ] {Feature 3} — {why mandatory for "love"}

### Postponed (Day 30+):
- {Feature} — {why not now}

### Anti-scope (never in v1):
- {What we cut forever for v1}

---

## Monetization

**Who pays:** {user / business / third party}

**Model:** {subscription / transactions / commission / freemium}

**Price:** {range}

**Competitors and differentiation:**
| Competitor | What they do | Our difference |
|------------|--------------|----------------|
| {competitor1} | {what} | {why we're better} |
| Excel/manual labor | {what} | {why we're better} |

---

## Unfair Advantage

{why this specific founder — honestly}

**Copy risk:** {assessment and how we protect}

---

## Metrics

**North Star:** {one success number}

**Supporting:**
- {metric 1}
- {metric 2}

---

## Open Questions

- [ ] {What remains unclear}
- [ ] {What needs validation}

---

## Assumptions (critical)

| Assumption | How we'll verify | What if wrong |
|------------|------------------|---------------|
| {assumption1} | {verification method} | {plan B} |
| {assumption2} | {verification method} | {plan B} |

---

## "MLP Ready" Criteria

- [ ] {Criterion 1 — what must work}
- [ ] {Criterion 2 — what Vasya must say}
- [ ] {Criterion 3 — what metric achieved}

---

## Yellow Flags

{What concerned us during discovery — honestly}
```

### ai/idea/architecture.md

```markdown
# Architecture: {Project Name}

**Date:** {today}

---

## Business Entities

Based on domain-context, identified:

| Entity | Description | Examples |
|--------|-------------|----------|
| {entity1} | {what it is} | {examples} |
| {entity2} | {what it is} | {examples} |

---

## Domains

### `{domain1}` — {name}
**Responsibility:** {what it does}
**Key entities:** {list}
**Depends on:** {other domains or —}

### `{domain2}` — {name}
**Responsibility:** {what it does}
**Key entities:** {list}
**Depends on:** {other domains}

### `{domain3}` — {name}
...

---

## Dependency Graph

```
     shared (Result, exceptions)
          │
          ▼
     infra (db, llm, external)
          │
    ┌─────┴─────┐
    ▼           ▼
{domain1}   {domain2}
    │           │
    └─────┬─────┘
          ▼
    {domain3}
```

**Rule:** Arrows = "depends on". No cycles.

---

## Entry Points

| Type | Technology | For whom |
|------|------------|----------|
| {type1} | {tech} | {audience} |
| {type2} | {tech} | {audience} |

---

## Infrastructure

**Database:** {choice and why}
**LLM:** {if needed}
**External APIs:**
- {api1} — {why}
- {api2} — {why}

---

## First Steps (Day 1)

1. [ ] Create structure `src/domains/{domain1}/`
2. [ ] Create `CLAUDE.md` from these files
3. [ ] `/spark` for first feature: {which one}
```

---

## Anti-patterns (don't do this)

| Bad | Why | How to do it |
|-----|-----|--------------|
| Ask all questions as a list | It's a questionnaire, not dialogue | 1-2 questions at a time, with follow-ups |
| Accept first answer | First answer is usually superficial | Dig deeper: "Why? How exactly?" |
| Ignore contradictions | They'll surface later | Return and break them down immediately |
| Rush to solution | Poorly understood problem = bad product | 70% time on problem, 30% on solution |
| Agree with everything | You're not a therapist, you're a partner | Challenges are needed, they help |
| Skip "small things" | Small things break everything later | Clarify everything that seems unclear |
| Propose 10 domains | Too many to start | 3-5 domains max for MLP |

---

## Exit from Discovery

**Ready for Day 1 when:**
- [ ] Can describe persona in 30 seconds
- [ ] Understand the pain specifically (not abstractly)
- [ ] Know why current solutions don't work
- [ ] MLP scope is clear (3-5 features, no more)
- [ ] Have one success metric
- [ ] Domains agreed and make sense
- [ ] Yellow flags recorded (not ignored)

**Not ready if:**
- "For everyone" — no specific persona
- "Everything is needed" — no prioritization
- "We'll figure it out later" — there are critical unknowns
- Founder doesn't know a single real Vasya
- Domains unclear to the founder themselves

---

## After Bootstrap

```
ai/idea/
├── vision.md           ✓
├── domain-context.md   ✓
├── product-brief.md    ✓
└── architecture.md     ✓

→ Day 1: create structure per architecture.md
→ Day 1: create CLAUDE.md from these files
→ Day 2: /spark for first feature
```
