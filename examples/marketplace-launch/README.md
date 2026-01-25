# Marketplace Launch Automation

> Automated SKU launch pipeline for e-commerce marketplaces using DLD methodology

---

## The Problem

Launching products on marketplaces (Amazon, eBay, Ozon, Wildberries) requires:

- **Content preparation** — titles, descriptions, images for each platform
- **Price calculations** — considering fees, margins, competition
- **Compliance checks** — category rules, restricted words, image requirements
- **Multi-platform publishing** — API integrations with 4+ marketplaces

**Before DLD:**
- Manual process: 2-3 hours per SKU
- Error rate: 15-20% (compliance failures, price miscalculations)
- Knowledge silos: each marketplace had its own "expert"
- Scaling bottleneck: max 10-15 SKUs/day with 2 people

---

## The Solution

Automated pipeline using DLD principles:

1. **Spark** generates launch spec from product data
2. **Autopilot** executes: content → pricing → compliance → publish
3. **Human** reviews only flagged items (compliance warnings, price anomalies)

---

## DLD Principles Applied

### 1. Domain Isolation

Each marketplace = separate domain with clear API:

```
src/domains/
├── catalog/          # Product data management
│   ├── index.ts      # Public: getProduct, enrichProduct
│   ├── enricher.ts   # AI content enhancement
│   └── types.ts      # Product, Category, Attribute
│
├── pricing/          # Price calculation engine
│   ├── index.ts      # Public: calculatePrice
│   ├── calculator.ts # Margin, fees, competition
│   └── rules/        # Per-marketplace rules
│       ├── amazon.ts
│       └── ebay.ts
│
├── compliance/       # Marketplace rule validation
│   ├── index.ts      # Public: validateListing
│   ├── checker.ts    # Rule engine
│   └── rules/        # Category-specific rules
│
└── publishing/       # Multi-platform publishing
    ├── index.ts      # Public: publishListing
    └── adapters/     # Per-marketplace adapters
        ├── amazon.ts
        └── ebay.ts
```

**Key insight:** Domains don't share database models. Each has its own types. Integration happens through explicit protocols.

### 2. Spec-First Development

Every SKU launch starts with a spec:

```markdown
# Launch Spec: SKU-12345

## Product
- Name: Wireless Bluetooth Headphones
- Category: Electronics > Audio > Headphones
- Base price: $49.99

## Target Marketplaces
- [x] Amazon US
- [x] eBay US
- [ ] Walmart (blocked: category approval pending)

## Content Requirements
- Title: max 200 chars, keywords: wireless, bluetooth, noise-canceling
- Description: 2000+ chars, bullet points required
- Images: 5+, main image white background

## Price Rules
- Amazon: base + 15% fees, min margin 20%
- eBay: base + 12% fees, min margin 15%

## Compliance Checklist
- [ ] Battery certification uploaded
- [ ] FCC compliance documented
- [ ] No restricted keywords in title
```

Spec is **reviewed before coding**. Agent doesn't start until spec is approved.

### 3. Fresh Context Per Task

Each SKU is processed by a fresh agent instance:

- **No cross-contamination:** SKU-12345 context doesn't leak into SKU-12346
- **Predictable behavior:** same input → same output
- **Easy debugging:** if SKU-12345 fails, inspect its isolated worktree

### 4. File Size Limits

Every file < 400 LOC:

- `pricing/calculator.ts`: 120 lines (core logic)
- `pricing/rules/amazon.ts`: 80 lines (Amazon-specific)
- `pricing/rules/ebay.ts`: 65 lines (eBay-specific)

Complex logic is split, not crammed. AI stays oriented.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Launch Pipeline                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  /spark                                                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 1. Read product data from ERP                             │   │
│  │ 2. Research marketplace requirements (via Exa)            │   │
│  │ 3. Generate launch spec                                   │   │
│  │ 4. Human reviews and approves                             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  /autopilot                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │  catalog   │→ │  pricing   │→ │ compliance │→ │ publishing │ │
│  │  (enrich)  │  │ (calculate)│  │  (validate)│  │  (publish) │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
│                                         │                        │
│                                         ▼                        │
│                              ┌──────────────────┐               │
│                              │ Flagged for human│               │
│                              │ review if errors │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Time per SKU | 2-3 hours | 15 minutes | 8-12x faster |
| Error rate | 15-20% | 2-3% | 85% reduction |
| Daily throughput | 10-15 SKUs | 100+ SKUs | 7-10x increase |
| Staff required | 2 full-time | 0.5 (review only) | 75% reduction |

**Payback period:** 3 weeks (based on staff time savings)

---

## Lessons Learned

### 1. Domain boundaries matter more than you think

Initially, we had `marketplace` as one domain. Too big. Each marketplace has different rules, different APIs, different content requirements.

**Fix:** Split into `pricing/rules/amazon.ts`, `compliance/rules/amazon.ts`, etc. Each file focused on one thing.

### 2. Specs save debugging time

The temptation was to skip specs for "simple" SKUs. Mistake. Specs caught:
- Missing compliance documents
- Price calculation errors
- Category mismatches

**Lesson:** 5 minutes on spec review saves 30 minutes of debugging.

### 3. Fresh context is non-negotiable

Early version reused agent context for batches of SKUs. Result: "hallucinations" — agent confused SKU-100 with SKU-101.

**Fix:** Fresh worktree per SKU. Slightly slower, much more reliable.

### 4. File size limits enable LLM comprehension

When `calculator.ts` grew to 600 lines, agent started making mistakes. Split it into focused modules, problems disappeared.

**Lesson:** 400 LOC limit isn't arbitrary — it's about attention span.

---

## Try It Yourself

This example demonstrates DLD principles. To apply to your project:

1. Identify your domains (what are the bounded contexts?)
2. Define clear APIs between them (what can each domain do?)
3. Create specs before coding (what exactly needs to happen?)
4. Run each task in isolation (fresh context, worktree)

See [Migration Guide](/docs/13-migration.md) for step-by-step instructions.

---

## Tech Stack

- **Runtime:** Node.js + TypeScript
- **AI:** Claude Code + Claude Opus 4.5
- **Integrations:** Amazon SP-API, eBay API, internal ERP
- **Infrastructure:** Docker, PostgreSQL, Redis

---

*This example is based on a real project. Numbers are representative but anonymized.*
