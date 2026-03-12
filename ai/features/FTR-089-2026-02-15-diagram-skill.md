# Feature: [FTR-089] /diagram Skill — Professional Excalidraw Diagram Generation
**Status:** done | **Priority:** P1 | **Date:** 2026-02-15

## Why
Claude Code can generate Excalidraw JSON, but raw generation is:
- 800+ lines per diagram (3000+ tokens)
- Manual coordinate calculation (fragile, misaligned)
- Default Excalidraw font (Virgil/Excalifont) is hard to read
- No auto-layout — elements overlap or have inconsistent spacing
- No semantic color system — random colors per diagram

A dedicated skill with a converter script solves all of this: LLM generates ~30 lines of simplified JSON, a zero-dep Node.js script handles layout, bindings, and Excalidraw boilerplate.

## Context
- Research conducted Feb 15, 2026 (Exa + Sequential Thinking)
- 12 authoritative sources: IBM Carbon, ONS, WCAG 2.1, ISO 5807, GitHub Docs, cc-excalidraw-skill
- Existing solutions evaluated: excalidraw-mcp (2049★), excalidraw-cli, mermaid-to-excalidraw
- Decision: zero-dep custom converter (no npm dependencies for DLD template users)
- Excalidraw built-in fonts: 1=Excalifont (hand-drawn), **2=Nunito (sans-serif)**, 3=Comic Shanns (mono)

---

## Scope
**In scope:**
- Skill prompt (SKILL.md) with design system reference
- Zero-dep converter script (excalidraw-gen.mjs)
- Flowchart diagrams (TB/LR direction)
- Architecture diagrams (multi-tier, grouped layers)
- Two modes: from description + auto-analyze code
- Semantic color palette (8 colors, WCAG AA)
- BFS layered auto-layout algorithm
- Localization triggers (Russian)

**Out of scope:**
- Sequence diagrams (future FTR)
- ER diagrams (future FTR)
- Real-time Excalidraw preview (MCP server approach)
- Custom font injection (Nunito is built-in)

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- New skill, no existing callers

### Step 2: DOWN — what depends on?
- Node.js runtime (already required for hooks)
- Excalidraw JSON format (stable, version 2)

### Step 3: BY TERM — grep entire project
- `grep -rn "diagram" template/.claude/ .claude/` → no conflicts
- `grep -rn "excalidraw" .claude/` → only test/ files (our previous experiment)

### Step 4: CHECKLIST — mandatory folders
- [ ] `template/.claude/skills/` — new skill folder
- [ ] `template/.claude/tools/` — new tools folder (first tool!)
- [ ] `.claude/rules/localization.md` — add triggers (DLD-specific)
- [ ] `template/CLAUDE.md` — add to skills table

### Verification
- [ ] All found files added to Allowed Files
- [ ] No conflicts with existing skills

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `template/.claude/skills/diagram/SKILL.md` — skill prompt (create)
2. `template/.claude/tools/excalidraw-gen.mjs` — converter script (create)
3. `.claude/skills/diagram/SKILL.md` — synced copy (create)
4. `.claude/tools/excalidraw-gen.mjs` — synced copy (create)
5. `.claude/rules/localization.md` — add Russian triggers (modify)
6. `template/CLAUDE.md` — add skill to table (modify)

**New files allowed:**
- `template/.claude/skills/diagram/SKILL.md`
- `template/.claude/tools/excalidraw-gen.mjs`

**FORBIDDEN:** All other files.

---

## Environment
nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: Zero-dep converter + skill prompt (SELECTED)
**Source:** Research synthesis from 12 sources + cc-excalidraw-skill (GitHub)
**Summary:** LLM generates simplified JSON spec → Node.js script converts to .excalidraw
**Pros:** Zero dependencies, 15-30x token savings, auto-layout, semantic colors
**Cons:** Layout algorithm simpler than ELK.js (but sufficient for flowcharts)

### Approach 2: excalidraw-cli integration
**Source:** github.com/swiftlysingh/excalidraw-cli
**Summary:** Use external CLI with ELK.js layout engine
**Pros:** Better layout quality (ELK.js), established tool
**Cons:** npm dependency required, breaks DLD zero-dep template promise

### Selected: 1
**Rationale:** Zero dependencies is critical for DLD template. BFS layered layout is sufficient for flowcharts and architecture diagrams. Can upgrade to Approach 2 as optional enhancement later.

---

## Design

### Simplified JSON Spec Format (LLM generates this)

```json
{
  "title": "Spark Feature Flow",
  "direction": "TB",
  "style": "professional",
  "nodes": [
    {"id": "start", "label": "/spark", "shape": "ellipse", "color": "orange"},
    {"id": "detect", "label": "SKILL.md\nMode Detection", "shape": "rect", "color": "blue"},
    {"id": "decision", "label": "Complex?", "shape": "diamond", "color": "yellow"}
  ],
  "edges": [
    {"from": "start", "to": "detect"},
    {"from": "detect", "to": "decision", "label": "feature"},
    {"from": "decision", "to": "autopilot", "label": "simple", "style": "solid"},
    {"from": "decision", "to": "council", "label": "complex", "style": "dashed"}
  ],
  "groups": [
    {"id": "g1", "label": "Spark Phase", "nodes": ["detect", "socratic"], "color": "purple"}
  ]
}
```

### Design System (from research)

**Global defaults:**
```
roughness: 0         (clean lines, no hand-drawn wobble)
fontFamily: 2        (Nunito — sans-serif, readable)
strokeWidth: 2       (standard line weight)
fillStyle: "solid"   (solid fills)
opacity: 100         (full opacity)
```

**Semantic Color Palette:**
| Name | Background | Stroke | Semantic |
|------|-----------|--------|----------|
| orange | #ffc078 | #e8590c | Trigger, start, entry point |
| blue | #a5d8ff | #1971c2 | Process, service, information |
| yellow | #ffec99 | #f08c00 | Decision, warning, branch |
| green | #b2f2bb | #2f9e44 | Success, output, result |
| red | #ffc9c9 | #e03131 | Error, danger, critical |
| purple | #d0bfff | #9c36b5 | External, storage, database |
| gray | #e9ecef | #868e96 | Neutral, default, disabled |
| teal | #96f2d7 | #0c8599 | Secondary, note, async |

**Typography Scale:**
| Element | fontSize | Use |
|---------|---------|-----|
| Diagram title | 28 | Free text at top |
| Section/group label | 24 | Group headers |
| Node label | 20 | Primary text in boxes |
| Node sublabel | 16 | Secondary text (2nd line) |
| Edge label | 14 | Arrow descriptions |
| Annotation | 14 | Side notes (gray) |

**Shape Mapping:**
| Shape | Excalidraw type | roundness | Use |
|-------|----------------|-----------|-----|
| rect | rectangle | {type:3} | Process, service, step |
| diamond | diamond | {type:2} | Decision, condition |
| ellipse | ellipse | null | Start/end terminal |
| rounded | rectangle | {type:3} | Soft element, card, UI |
| database | rectangle | {type:3} | DB (purple, prefixed "DB:") |
| external | rectangle | {type:3}, strokeStyle:"dashed" | External system |

**Layout Grid:**
```
nodeWidth:     auto (based on text, min 150, max 320)
nodeHeight:    auto (based on lines, min 60, max 100)
horizontalGap: 80px
verticalGap:   50px
padding:       20px (text inside shapes)
gridSnap:      50px (all positions rounded to 50)
```

### excalidraw-gen.mjs Architecture

```
Input (stdin or file) → Parse JSON spec
  → Build adjacency graph
  → BFS assign layers (Y positions)
  → Distribute nodes per layer (X positions)
  → Handle groups (background rectangles)
  → Generate Excalidraw elements:
      - Rectangle/Diamond/Ellipse per node
      - Bound text per node
      - Arrow per edge with bindings
      - Label text per edge (if present)
      - Group rectangles (if groups defined)
      - Title text (if title present)
  → Wrap in Excalidraw file format (version 2)
  → Write to output file
```

### Skill Workflow

**Mode 1: From description (default)**
```
User: "нарисуй схему автопилота"
  → Skill reads relevant files (spark SKILL.md, etc.)
  → LLM generates JSON spec
  → Bash: node template/.claude/tools/excalidraw-gen.mjs < spec.json > output.excalidraw
  → Return file path
```

**Mode 2: Auto-analyze code**
```
User: "diagram analyze src/domains/"
  → Skill reads source files, imports, structure
  → LLM builds architecture understanding
  → LLM generates JSON spec representing actual code architecture
  → Bash: node excalidraw-gen.mjs < spec.json > output.excalidraw
  → Return file path
```

---

## UI Event Completeness
N/A — no UI elements, CLI skill only.

---

## Implementation Plan

### Research Sources
- [cc-excalidraw-skill best-practices](https://github.com/rnjn/cc-excalidraw-skill/blob/main/best-practices.md) — proven Excalidraw generation patterns
- [ExcalidrawElementSkeleton API](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/excalidraw-element-skeleton) — minimal attribute reference
- [ISO 5807 Guide](https://www.useworkspace.dk/en/blog/iso-5807-flowchart-symbols-guide) — standard flowchart symbols
- [IBM Carbon Technical Diagrams](https://www.ibm.com/design/language/infographics/technical-diagrams/design/) — enterprise design system
- [ONS Chart Typography](https://service-manual.ons.gov.uk/data-visualisation/build-specifications/typography) — font sizes, accessibility
- [GitHub Diagram Guidelines](https://docs.github.com/en/contributing/writing-for-github-docs/creating-diagrams-for-github-docs) — labeling, color rules

### Task 1: Create excalidraw-gen.mjs converter
**Type:** code
**Files:**
  - create: `template/.claude/tools/excalidraw-gen.mjs`
**Pattern:** [cc-excalidraw-skill](https://github.com/rnjn/cc-excalidraw-skill)
**Acceptance:**
  - Script reads JSON spec from stdin or file argument
  - Outputs valid .excalidraw file that opens in Excalidraw
  - BFS layered layout positions nodes correctly (no overlaps)
  - Bound text centered in shapes
  - Arrows connect with proper bindings
  - Supports: rect, diamond, ellipse, rounded, dashed shapes
  - Supports: TB and LR directions
  - Supports: groups (background rectangles)
  - fontFamily: 2, roughness: 0, semantic colors
  - < 400 LOC (architecture limit)
  - Zero npm dependencies

### Task 2: Create SKILL.md prompt
**Type:** code
**Files:**
  - create: `template/.claude/skills/diagram/SKILL.md`
**Pattern:** Follows existing skill structure (see scout, audit)
**Acceptance:**
  - Frontmatter: name, description
  - Activation triggers documented
  - JSON spec format reference with examples
  - Color palette reference table
  - Shape mapping reference table
  - Typography scale reference
  - Two modes documented: description + analyze
  - Rules: output path, file naming
  - < 400 LOC

### Task 3: Sync to .claude/
**Type:** code
**Files:**
  - create: `.claude/skills/diagram/SKILL.md`
  - create: `.claude/tools/excalidraw-gen.mjs`
**Acceptance:**
  - Files identical to template/ versions

### Task 4: Add localization triggers
**Type:** code
**Files:**
  - modify: `.claude/rules/localization.md`
**Acceptance:**
  - Russian triggers added: "диаграмма", "нарисуй схему", "схема"

### Task 5: Update template CLAUDE.md
**Type:** code
**Files:**
  - modify: `template/CLAUDE.md`
**Acceptance:**
  - Skill added to skills table
  - Trigger examples updated

### Execution Order
1 → 2 → 3 → 4 → 5

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User triggers /diagram or "нарисуй схему" | Task 2, 4 | new |
| 2 | Skill reads context (files or description) | Task 2 | new |
| 3 | LLM generates JSON spec | Task 2 | new |
| 4 | excalidraw-gen.mjs converts to .excalidraw | Task 1 | new |
| 5 | File saved to ai/diagrams/ | Task 1, 2 | new |
| 6 | User opens file in Excalidraw | - | external (user action) |

**GAPS:** None.

---

## Definition of Done

### Functional
- [ ] `/diagram` skill generates .excalidraw files from natural language
- [ ] `diagram analyze src/` mode reads code and generates architecture diagram
- [ ] Output opens correctly in excalidraw.com
- [ ] Font is Nunito (fontFamily: 2), not Virgil
- [ ] Lines are clean (roughness: 0)
- [ ] Colors follow semantic palette
- [ ] Auto-layout: no overlaps, consistent spacing
- [ ] Groups render as labeled background rectangles

### Technical
- [ ] excalidraw-gen.mjs < 400 LOC, zero dependencies
- [ ] SKILL.md follows existing skill structure
- [ ] Files synced template/ → .claude/
- [ ] Localization triggers work

---

## Autopilot Log
[Auto-populated by autopilot during execution]
