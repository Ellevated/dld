# Content Factory

> Automated content generation pipeline with quality control using DLD methodology

---

## The Problem

Creating high-quality content at scale requires:

- **Research** — gathering facts, statistics, and sources
- **Structure** — organizing information into coherent narratives
- **Writing** — producing engaging, accurate content
- **Editing** — ensuring consistency, style, and brand alignment
- **Fact-checking** — verifying claims and avoiding hallucinations

**Before DLD:**
- Manual process: 4-6 hours per article
- Quality variance: 40% of drafts needed major rewrites
- Fact-checking bottleneck: 30% of articles had citation issues
- Inconsistent tone: each writer had different style
- Scaling problem: max 20 articles/month with 3 writers

**Common LLM pitfalls:**
- **Hallucinations** — making up statistics, quotes, or facts
- **Tone drift** — inconsistent voice across content
- **Surface-level content** — generic fluff without depth
- **Citation failures** — unsourced claims, broken links
- **Context collapse** — losing thread halfway through long articles

---

## The Solution

Multi-stage pipeline using DLD principles:

1. **Research agent** gathers verified facts and sources
2. **Outline agent** structures information logically
3. **Writer agent** produces first draft following style guide
4. **Editor agent** polishes for clarity and consistency
5. **Quality gates** validate between each stage

**Human oversight:** Reviews only flagged items (fact-check failures, style violations)

---

## DLD Principles Applied

### 1. Staged Processing

Each stage is isolated with clear responsibilities:

```
src/domains/
├── research/           # Fact gathering domain
│   ├── index.ts        # Public: gatherFacts, verifySources
│   ├── gatherer.ts     # External source research (Exa, web)
│   ├── validator.ts    # Source credibility checking
│   └── types.ts        # Fact, Source, Citation
│
├── structure/          # Content structure domain
│   ├── index.ts        # Public: createOutline
│   ├── outliner.ts     # Logical flow construction
│   ├── templates/      # Content templates by type
│   │   ├── blog.ts     # Blog post structure
│   │   ├── tutorial.ts # Tutorial structure
│   │   └── guide.ts    # Guide structure
│   └── types.ts        # Outline, Section, SubSection
│
├── writing/            # Content creation domain
│   ├── index.ts        # Public: generateDraft
│   ├── writer.ts       # Draft generation
│   ├── style-guide.ts  # Brand voice rules
│   └── glossary.ts     # Domain terminology
│
├── editing/            # Quality improvement domain
│   ├── index.ts        # Public: editContent
│   ├── editor.ts       # Content refinement
│   ├── checker.ts      # Style/grammar validation
│   └── enhancer.ts     # Readability optimization
│
└── publishing/         # Distribution domain
    ├── index.ts        # Public: publishContent
    ├── formatter.ts    # Platform-specific formatting
    └── adapters/       # Per-platform adapters
        ├── blog.ts     # WordPress, Ghost, etc.
        ├── docs.ts     # ReadTheDocs, GitBook
        └── social.ts   # LinkedIn, Twitter threads
```

**Key insight:** Each stage produces an artifact that's validated before the next stage begins. No stage can "fix" upstream problems.

### 2. Quality Gates

Between each stage, automated checks prevent bad data from flowing forward:

```typescript
// Quality gate example: research → outline

interface QualityGate {
  stage: string;
  checks: Check[];
  threshold: number; // Min score to pass
}

const researchGate: QualityGate = {
  stage: 'research → outline',
  checks: [
    {
      name: 'Source credibility',
      validate: (facts) => {
        // All sources must have credibility score > 70
        return facts.every(f => f.source.credibility > 70);
      }
    },
    {
      name: 'Fact count minimum',
      validate: (facts) => {
        // Must have at least 10 verified facts
        return facts.length >= 10;
      }
    },
    {
      name: 'Citation coverage',
      validate: (facts) => {
        // All claims must have citations
        return facts.every(f => f.citations.length > 0);
      }
    }
  ],
  threshold: 100 // All checks must pass
};
```

**Quality gates we implemented:**
- **Research → Outline:** Source credibility, fact count, citation coverage
- **Outline → Draft:** Logical flow, section balance, depth score
- **Draft → Edit:** Style consistency, readability score, fact accuracy
- **Edit → Publish:** Final review, SEO checks, legal compliance

### 3. Domain Knowledge Injection

Each content type has curated domain knowledge:

```markdown
# Example: Technical Blog Domain

## Glossary (glossary.md)
- API: Application Programming Interface (use this term, not "interface" alone)
- Webhook: Server-to-server HTTP callback (always explain on first use)
- JWT: JSON Web Token (spell out on first use)

## Style Guide (style-guide.md)
- Tone: Professional but conversational
- Person: Second person ("you") for tutorials, third person for analysis
- Code examples: Always include full context, not isolated snippets
- Length: 1500-2500 words for blog posts

## Example Articles (examples/)
- /examples/good-tutorial.md — Model structure
- /examples/good-analysis.md — Model depth
- /examples/bad-generic.md — What to avoid (anti-pattern)
```

**Why this matters:** Without domain knowledge, LLMs default to generic content. Glossary + style guide + examples = consistent brand voice.

### 4. Fresh Context Per Article

Each article is generated in isolated context:

- **No cross-contamination:** Article A facts don't leak into Article B
- **Predictable output:** Same topic + same sources = same quality
- **Easy debugging:** If Article failed, inspect its isolated worktree

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       Content Pipeline                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  /spark                                                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 1. Analyze content brief (topic, audience, angle)        │   │
│  │ 2. Research requirements (sources needed, depth)         │   │
│  │ 3. Generate content spec                                 │   │
│  │ 4. Human reviews and approves                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Research                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Research Agent:                                           │   │
│  │ - Gather facts from credible sources (Exa search)        │   │
│  │ - Verify statistics and claims                           │   │
│  │ - Build citation database                                │   │
│  │ Output: research-facts.json                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                         │                        │
│                                         ▼                        │
│                              ┌──────────────────┐               │
│                              │ Quality Gate 1    │               │
│                              │ ✓ Source check    │               │
│                              │ ✓ Fact count      │               │
│                              │ ✓ Citations       │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: Outline                                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Outline Agent:                                            │   │
│  │ - Create logical structure from facts                     │   │
│  │ - Apply content template (blog/tutorial/guide)           │   │
│  │ - Ensure balanced sections                               │   │
│  │ Output: content-outline.md                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                         │                        │
│                                         ▼                        │
│                              ┌──────────────────┐               │
│                              │ Quality Gate 2    │               │
│                              │ ✓ Logical flow    │               │
│                              │ ✓ Section balance │               │
│                              │ ✓ Depth score     │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: Writing                                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Writer Agent:                                             │   │
│  │ - Generate draft following outline                        │   │
│  │ - Apply style guide and glossary                          │   │
│  │ - Insert citations inline                                 │   │
│  │ Output: draft.md                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                         │                        │
│                                         ▼                        │
│                              ┌──────────────────┐               │
│                              │ Quality Gate 3    │               │
│                              │ ✓ Style check     │               │
│                              │ ✓ Readability     │               │
│                              │ ✓ Fact accuracy   │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4: Editing                                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Editor Agent:                                             │   │
│  │ - Polish for clarity and flow                             │   │
│  │ - Check consistency (terminology, tone)                   │   │
│  │ - Optimize readability (Flesch score > 60)               │   │
│  │ Output: final.md                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                         │                        │
│                                         ▼                        │
│                              ┌──────────────────┐               │
│                              │ Quality Gate 4    │               │
│                              │ ✓ Final review    │               │
│                              │ ✓ SEO checks      │               │
│                              │ ✓ Legal/brand     │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Publishing                                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ - Format for target platform                             │   │
│  │ - Schedule publication                                    │   │
│  │ - Distribute (blog, docs, social)                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Time per article | 4-6 hours | 45 minutes | 5-8x faster |
| Quality (editor score) | 6.5/10 avg | 8.5/10 avg | +31% improvement |
| Fact-check failures | 30% | 3% | 90% reduction |
| Revision rounds | 2-3 | 0-1 | 67% fewer revisions |
| Monthly output | 20 articles | 150+ articles | 7.5x increase |
| Writer headcount | 3 full-time | 1 (review only) | 67% reduction |

**Quality breakdown (human evaluation):**
- Accuracy: 95% (vs. 70% before)
- Tone consistency: 92% (vs. 60% before)
- Depth of analysis: 85% (vs. 55% before)
- Readability: 90% (vs. 75% before)

**Payback period:** 6 weeks (based on writer time savings)

---

## Workflow Example

### Input: Content Brief

```markdown
# Content Brief: API Authentication Tutorial

**Topic:** JWT authentication in Express.js
**Audience:** Mid-level developers (2-3 years experience)
**Angle:** Security-first approach with best practices
**Length:** 2000-2500 words
**Required sections:** Theory, implementation, testing, security considerations
```

### Stage 1: Research Agent Output

```json
{
  "facts": [
    {
      "claim": "JWT tokens should expire within 15 minutes for high-security applications",
      "source": "OWASP Authentication Cheat Sheet",
      "credibility": 95,
      "citations": ["https://cheatsheetseries.owasp.org/..."],
      "verified": true
    },
    {
      "claim": "65% of API breaches involve compromised authentication",
      "source": "Verizon DBIR 2024",
      "credibility": 90,
      "citations": ["https://verizon.com/dbir/2024"],
      "verified": true
    }
    // ... 15 more facts
  ],
  "quality_score": 92
}
```

### Stage 2: Outline Agent Output

```markdown
# JWT Authentication in Express.js: A Security-First Guide

## Introduction (200 words)
- Hook: API breach statistics
- Why JWT matters
- What you'll learn

## 1. Understanding JWT (400 words)
- What is JWT (structure: header.payload.signature)
- Why use JWT vs. sessions
- Security properties

## 2. Implementation (800 words)
- Setup Express project
- Install dependencies (jsonwebtoken, bcrypt)
- Create auth middleware
- Code examples with security annotations

## 3. Testing Your Implementation (400 words)
- Unit tests for token generation
- Integration tests for protected routes
- Security test cases (expired tokens, tampered tokens)

## 4. Security Best Practices (400 words)
- Token expiration strategy
- Refresh token pattern
- Secret key management
- Common vulnerabilities to avoid

## Conclusion (200 words)
- Recap
- Next steps
- Additional resources
```

### Stage 3: Writer Agent Output

```markdown
# JWT Authentication in Express.js: A Security-First Guide

API security breaches cost companies an average of $4.24 million per incident,
with 65% involving compromised authentication (Verizon DBIR 2024). If you're
building APIs with Express.js, implementing robust authentication isn't
optional—it's critical.

In this guide, you'll learn how to implement JWT (JSON Web Token) authentication
with a security-first mindset. We'll cover not just the "how," but the "why"
behind each decision...

[Full draft continues with inline citations, code examples, etc.]
```

### Stage 4: Editor Agent Output

```markdown
[Polished version with improved transitions, consistency checks,
readability optimization, and final fact verification]

Final metrics:
- Flesch Reading Ease: 62 (target: 60+)
- Style consistency: 94%
- Citation coverage: 100%
- Word count: 2,347
```

---

## Lessons Learned

### 1. Research quality determines final quality

**Problem:** Early versions allowed writer to "research on the fly." Result: hallucinations, weak sources.

**Fix:** Mandatory research stage with verification. Writer gets only verified facts. Can't make up statistics.

**Lesson:** Forcing separation between research and writing eliminates 90% of hallucinations.

### 2. Style guides prevent tone drift

**Problem:** Without explicit style guide, each article had different voice. Some too technical, some too casual.

**Fix:** Created detailed style guide with examples:
```markdown
✅ Good: "You'll need to configure your Express middleware."
❌ Bad: "One must configure the Express middleware."
❌ Bad: "Just throw some middleware in there lol"
```

**Lesson:** LLMs follow patterns. Give them good patterns.

### 3. Quality gates catch problems early

**Problem:** Bad outlines led to bad drafts. Fixing at editing stage was expensive (rewrites).

**Fix:** Validate outline before writing. If structure is wrong, stop pipeline.

**Lesson:** 5 minutes validating outline saves 30 minutes rewriting draft.

### 4. Domain knowledge > prompt engineering

**Problem:** Spent weeks tweaking prompts to get "the right tone." Results were inconsistent.

**Fix:** Created glossary + example articles. Agent learns from examples, not from prompt instructions.

**Lesson:** Show, don't tell. Examples are more reliable than instructions.

### 5. Human review still essential for sensitive topics

**Problem:** Automated pipeline published article with legal compliance gap.

**Fix:** Flagging system for sensitive topics:
- Legal advice → human review
- Financial guidance → human review
- Medical information → human review
- Controversial topics → human review

**Lesson:** Automation ≠ zero oversight. Define escalation boundaries.

### 6. File size limits enable better content

**Problem:** When `style-guide.md` grew to 1000+ lines, agent couldn't follow it effectively.

**Fix:** Split into focused guides:
- `style-guide.md`: 200 lines (core principles)
- `blog-style.md`: 150 lines (blog-specific)
- `tutorial-style.md`: 180 lines (tutorial-specific)

**Lesson:** DLD's 400 LOC limit applies to knowledge files too. Smaller = more attention.

---

## When to Use This Pattern

**Good fit:**
- High-volume content needs (100+ articles/month)
- Standardized content types (tutorials, guides, reviews)
- Clear quality criteria (fact-based, structured)
- Repetitive research patterns

**Not a good fit:**
- Highly creative content (opinion pieces, storytelling)
- Novel topics (no prior examples or research)
- Content requiring deep expertise (medical, legal)
- Low-volume, high-touch content (executive thought leadership)

---

## Try It Yourself

To apply this pattern to your content needs:

1. **Define your stages** — What are the distinct phases? (research, writing, editing, etc.)
2. **Set quality gates** — What must be true before moving to next stage?
3. **Build domain knowledge** — Create glossary, style guide, example content
4. **Start with one content type** — Blog posts, tutorials, or documentation
5. **Measure quality** — Track fact-check failures, revision rounds, human ratings
6. **Iterate** — Refine gates and knowledge based on failures

See [Migration Guide](/docs/13-migration.md) for step-by-step DLD setup instructions.

---

## Tech Stack

- **Runtime:** Node.js + TypeScript
- **AI:** Claude Code + Claude Opus 4.5
- **Research:** Exa API for web search
- **Quality checks:** Custom validators + readability-score library
- **Publishing:** WordPress API, Ghost API, markdown export
- **Monitoring:** Quality metrics dashboard (fact accuracy, style scores)

---

*This example is based on real content pipeline projects. Metrics are representative but anonymized.*
