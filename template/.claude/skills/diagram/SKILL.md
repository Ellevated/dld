---
name: diagram
description: Professional Excalidraw diagram generation from natural language or code analysis.
---

# /diagram — Professional Excalidraw Diagrams

Generates .excalidraw files from description or code analysis using a simplified JSON spec + Node.js converter.

**Activation:**
- `/diagram {description}` — generate from description
- `/diagram analyze {path}` — analyze code and generate architecture diagram
- `diagram {description}` — implicit activation

## When to Use

- Visualize architecture, flows, pipelines
- Document component relationships
- Create decision trees, state machines
- Illustrate before/after refactoring

**Don't use:** For mockups, UI wireframes, or pixel-precise layouts.

## Principles

1. **Professional output** — clean lines (roughness: 0), Nunito font, semantic colors
2. **Token-efficient** — LLM generates ~20 lines of JSON spec, converter handles 500+ lines of Excalidraw format
3. **Zero dependencies** — pure Node.js, no npm install needed
4. **Two modes** — from description (creative) or from code (analytical)

---

## Mode Detection

| Trigger | Mode |
|---------|------|
| `/diagram analyze src/...` or "analyze" in args | **Analyze Mode** |
| Everything else | **Description Mode** |

---

## Mode 1: Description (default)

User describes what they want. You generate the JSON spec.

**Steps:**
1. Understand what the user wants to visualize
2. If needed, read relevant project files for context
3. Generate JSON spec (see format below)
4. Run converter:
   ```bash
   echo '<JSON_SPEC>' | node template/.claude/tools/excalidraw-gen.mjs ai/diagrams/{name}.excalidraw
   ```
5. Report file path to user

**Examples:**
- "diagram spark workflow" — reads spark SKILL.md, generates flow
- "diagram the autopilot pipeline" — reads autopilot skill, generates pipeline
- "нарисуй схему доменов" — reads architecture, generates domain diagram

## Mode 2: Analyze

Reads source code and generates architecture diagram automatically.

**Steps:**
1. Read files in target path (imports, exports, structure)
2. Build dependency graph from actual code
3. Generate JSON spec representing real architecture
4. Run converter (same as Mode 1)

**Example:**
- `diagram analyze src/domains/` — reads all domains, maps dependencies

---

## JSON Spec Format

The LLM generates this simplified format. The converter handles all Excalidraw complexity.

```json
{
  "title": "Diagram Title",
  "direction": "TB",
  "nodes": [
    {"id": "start", "label": "Entry Point", "shape": "ellipse", "color": "orange"},
    {"id": "process", "label": "Process Step\nSubtitle", "shape": "rect", "color": "blue"},
    {"id": "decision", "label": "Condition?", "shape": "diamond", "color": "yellow"},
    {"id": "result", "label": "Output", "shape": "rect", "color": "green"}
  ],
  "edges": [
    {"from": "start", "to": "process"},
    {"from": "process", "to": "decision", "label": "check"},
    {"from": "decision", "to": "result", "label": "yes", "style": "solid"},
    {"from": "decision", "to": "process", "label": "no", "style": "dashed"}
  ],
  "groups": [
    {"id": "g1", "label": "Phase 1", "nodes": ["start", "process"], "color": "purple"}
  ]
}
```

### Direction

| Value | Meaning |
|-------|---------|
| `TB` | Top to Bottom (default) |
| `LR` | Left to Right |

### Shapes

| Shape | Excalidraw Type | Use For |
|-------|----------------|---------|
| `rect` | rectangle | Process, service, step |
| `diamond` | diamond | Decision, condition |
| `ellipse` | ellipse | Start/end terminal |
| `rounded` | rectangle (rounded) | Soft element, card, UI |
| `database` | rectangle + "DB:" prefix | Database, storage |
| `external` | rectangle (dashed stroke) | External system |

### Semantic Colors

| Color | Background | Stroke | Use For |
|-------|-----------|--------|---------|
| `orange` | #ffc078 | #e8590c | Trigger, start, entry point |
| `blue` | #a5d8ff | #1971c2 | Process, service, information |
| `yellow` | #ffec99 | #f08c00 | Decision, warning, branch |
| `green` | #b2f2bb | #2f9e44 | Success, output, result |
| `red` | #ffc9c9 | #e03131 | Error, danger, critical |
| `purple` | #d0bfff | #9c36b5 | External, storage, database |
| `gray` | #e9ecef | #868e96 | Neutral, default, disabled |
| `teal` | #96f2d7 | #0c8599 | Secondary, note, async |

### Typography

| Element | Size | Automatic |
|---------|------|-----------|
| Title | 28px | From `title` field |
| Group label | 24px | From `groups[].label` |
| Node label | 20px | From `nodes[].label` |
| Edge label | 14px | From `edges[].label` |

### Edge Styles

| Style | Rendering |
|-------|-----------|
| `solid` | Solid line (default) |
| `dashed` | Dashed line |

### Multi-line Labels

Use `\n` in label text for multi-line node labels:
```json
{"id": "srv", "label": "Auth Service\nJWT + OAuth", "shape": "rect", "color": "blue"}
```

### Groups

Groups render as labeled background rectangles encompassing specified nodes:
```json
{"id": "g1", "label": "Backend Services", "nodes": ["auth", "billing", "users"], "color": "purple"}
```

---

## Output

- **Path:** `ai/diagrams/{name}.excalidraw`
- **Naming:** kebab-case, descriptive (e.g., `spark-workflow.excalidraw`, `domain-architecture.excalidraw`)
- **Format:** Excalidraw v2 JSON, opens in excalidraw.com or VS Code plugin

### Converter Command

```bash
echo '{...json spec...}' | node template/.claude/tools/excalidraw-gen.mjs ai/diagrams/{name}.excalidraw
```

Or with file:
```bash
node template/.claude/tools/excalidraw-gen.mjs ai/diagrams/{name}.excalidraw < spec.json
```

---

## Rules

1. **Always use semantic colors** — don't default everything to blue
2. **Keep diagrams focused** — 5-15 nodes is ideal, max ~25
3. **Use groups** for logical clustering when >8 nodes
4. **Label edges** when relationship isn't obvious
5. **Title every diagram** — mandatory `title` field
6. **Output to ai/diagrams/** — diagrams are local artifacts (gitignored)
7. **Create ai/diagrams/ directory** if it doesn't exist before writing
