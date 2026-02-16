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

1. **Professional output** — clean lines (roughness: 0), Helvetica font, semantic colors
2. **LLM does layout** — you place nodes with explicit x,y coordinates
3. **Converter does rendering** — shapes, bound text, arrows, Excalidraw JSON boilerplate
4. **Zero dependencies** — pure Node.js, no npm install needed

---

## Mode Detection

| Trigger | Mode |
|---------|------|
| `/diagram analyze src/...` or "analyze" in args | **Analyze Mode** |
| Everything else | **Description Mode** |

---

## Mode 1: Description (default)

User describes what they want. You generate the JSON spec with coordinates.

**Steps:**
1. Understand what the user wants to visualize
2. If needed, read relevant project files for context
3. Plan the layout mentally — what goes where
4. Generate JSON spec with x,y coordinates for every node
5. Run converter:
   ```bash
   echo '<JSON_SPEC>' | node template/.claude/tools/excalidraw-gen.mjs ai/diagrams/{name}.excalidraw
   ```
6. Report file path to user

## Mode 2: Analyze

Reads source code and generates architecture diagram automatically.

**Steps:**
1. Read files in target path (imports, exports, structure)
2. Build dependency graph from actual code
3. Generate JSON spec with coordinates representing real architecture
4. Run converter (same as Mode 1)

---

## JSON Spec Format

**IMPORTANT: Always provide x,y coordinates for every node.** You are the layout engine.
The converter only renders — it does NOT do good auto-layout.

**x,y = CENTER of the node** (not top-left corner). This means nodes with the same x are perfectly center-aligned regardless of width.

```json
{
  "title": "Diagram Title",
  "nodes": [
    {"id": "start",    "x": 400, "y": 50,  "label": "Entry Point", "shape": "ellipse", "color": "orange"},
    {"id": "process",  "x": 400, "y": 180, "label": "Process Step\nSubtitle", "shape": "rect", "color": "blue"},
    {"id": "decision", "x": 400, "y": 320, "label": "Condition?", "shape": "diamond", "color": "yellow"},
    {"id": "result",   "x": 400, "y": 460, "label": "Output", "shape": "rect", "color": "green"},
    {"id": "alt",      "x": 650, "y": 320, "label": "Alternative", "shape": "rect", "color": "gray"}
  ],
  "edges": [
    {"from": "start", "to": "process"},
    {"from": "process", "to": "decision", "label": "check"},
    {"from": "decision", "to": "result", "label": "yes"},
    {"from": "decision", "to": "alt", "label": "no", "style": "dashed"}
  ],
  "groups": [
    {"id": "g1", "label": "Main Flow", "nodes": ["start", "process", "decision"], "color": "blue"}
  ]
}
```

### Layout Guidelines

**Grid:** Use multiples of 50 for all coordinates.

**Coordinates = CENTER of node.** Same x = perfect vertical alignment.

**Vertical spacing:**
- Between sequential nodes: 130-150px
- Between node and IPC file: 100px
- Fan-out items: same Y, spread X evenly

**Horizontal spacing:**
- Between parallel nodes: 150-200px center-to-center
- Center main flow at x=400

**Sizing (auto-calculated from text, override with w,h):**
- `w` — explicit width (default: auto from text + padding)
- `h` — explicit height (default: auto from text + padding)
- Min size: 120×60

**Fan-out pattern** (e.g., 6 parallel items):
```json
{"id": "a", "x": 50,  "y": 500, "label": "Item A", ...},
{"id": "b", "x": 250, "y": 500, "label": "Item B", ...},
{"id": "c", "x": 450, "y": 500, "label": "Item C", ...},
{"id": "d", "x": 650, "y": 500, "label": "Item D", ...}
```

### Shapes

| Shape | Excalidraw Type | Use For |
|-------|----------------|---------|
| `rect` | rectangle | Process, service, step |
| `diamond` | diamond | Decision, condition |
| `ellipse` | ellipse | Start/end terminal |
| `rounded` | rectangle (rounded) | Soft element, card, UI |
| `database` | rectangle (dashed) | Database, storage, IPC file |
| `external` | rectangle (dashed) | External system |

### Semantic Colors

| Color | Use For |
|-------|---------|
| `orange` | Trigger, start, entry point |
| `blue` | Process, service, information |
| `yellow` | Decision, warning, branch |
| `green` | Success, output, result |
| `red` | Error, danger, critical |
| `purple` | Storage, database, IPC file |
| `gray` | Neutral, default, disabled |
| `teal` | Secondary, note, async |

### Edge Styles

| Style | Rendering |
|-------|-----------|
| `solid` | Solid line (default) |
| `dashed` | Dashed line |

### Edge Routing (elbow)

For side-connections (error paths, secondary outputs), use elbowed routing to avoid diagonal lines crossing other elements:

| Elbow | Routing | Use For |
|-------|---------|---------|
| _(none)_ | Straight line (default) | Main flow, fan-out |
| `"h"` | Horizontal first, then vertical | Side exit → turn down/up |
| `"v"` | Vertical first, then horizontal | Up/down exit → turn sideways |
| `"loop-right"` | U-shape via right side (3 segments) | Feedback loop going right |
| `"loop-left"` | U-shape via left side (3 segments) | Feedback loop going left |

**L-shape (h/v):**
```json
{"from": "ok", "to": "retry", "label": "rejected", "style": "dashed", "elbow": "h"},
{"from": "retry", "to": "step3", "label": "re-run", "style": "dashed", "elbow": "v"}
```

**U-shape (loop) — for back-edges / feedback:**
```json
{"from": "users", "to": "backlog", "label": "feedback", "style": "dashed", "elbow": "loop-left"}
```

### Routing Gotchas

1. **Same-Y nodes** — don't use elbow, use straight (horizontal line is correct)
2. **loop-right** — check that no side nodes (Scout, etc.) sit in the path. If right side is occupied, use `loop-left`
3. **Labels on elbows** — placed on first segment midpoint, offset away from line
4. **Labels on straight vertical arrows** — offset right (+8px) to avoid overlapping the line

### Multi-line Labels

Use `\n` for multi-line. Keep labels short — 2-4 words per line max:
```json
{"id": "srv", "x": 300, "y": 200, "label": "Auth Service\nJWT + OAuth", "shape": "rect", "color": "blue"}
```

### Groups

Groups render as labeled background rectangles encompassing specified nodes:
```json
{"id": "g1", "label": "Backend Services", "nodes": ["auth", "billing", "users"], "color": "blue"}
```

---

## Output

- **Path:** `ai/diagrams/{name}.excalidraw`
- **Naming:** kebab-case, descriptive (e.g., `spark-workflow.excalidraw`)
- **Format:** Excalidraw v2 JSON, opens in excalidraw.com or VS Code plugin

### Converter Command

```bash
echo '<JSON_SPEC>' | node template/.claude/tools/excalidraw-gen.mjs ai/diagrams/{name}.excalidraw
```

---

## Rules

1. **ALWAYS provide x,y** for every node — you are the layout engine
2. **Always use semantic colors** — don't default everything to blue
3. **Keep labels short** — 2-4 words per line, max 3 lines
4. **Keep diagrams focused** — 5-15 nodes is ideal, max ~25
5. **Use groups** for logical clustering when >8 nodes
6. **Label edges** when relationship isn't obvious
7. **Title every diagram** — mandatory `title` field
8. **Output to ai/diagrams/** — diagrams are local artifacts (gitignored)
9. **Create ai/diagrams/ directory** if it doesn't exist before writing
