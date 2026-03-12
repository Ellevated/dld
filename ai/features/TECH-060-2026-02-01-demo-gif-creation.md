# Tech: [TECH-060] Create Demo GIF for README

**Status:** draft | **Priority:** P0 | **Date:** 2026-02-01

## Why

README.md line 15 references `assets/demo/workflow.gif` that doesn't exist. First impression for GitHub visitors is a broken image. Critical blocker for launch.

## Context

Current state:
```
assets/demo/
└── .gitkeep  # Empty placeholder
```

README shows:
```markdown
![DLD Workflow Demo](assets/demo/workflow.gif)
```

Result: Broken image icon. Unprofessional.

---

## Scope

**In scope:**
- Record terminal session showing DLD workflow
- Convert to optimized GIF
- Show: /bootstrap → /spark → /autopilot flow
- Keep under 5MB for fast loading

**Out of scope:**
- Video with audio
- Multiple GIFs for each skill
- Animated diagrams

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `assets/demo/workflow.gif` | create | Main demo |
| 2 | `assets/demo/.gitkeep` | delete | No longer needed |

**New files allowed:**
| # | File | Reason |
|---|------|--------|
| 1 | `assets/demo/workflow.gif` | Demo animation |

---

## Design

### Demo Script (30-45 seconds)

```
Scene 1: Terminal opens (2s)
$ claude

Scene 2: Bootstrap (10s)
> /bootstrap
[Shows extraction of idea into ai/idea/*.md]
✓ Created ai/idea/vision.md
✓ Created ai/idea/architecture.md

Scene 3: Spark (15s)
> /spark Add user authentication
[Shows research + spec creation]
✓ Researched via Exa
✓ Created ai/features/FTR-001-auth.md
[Shows spec preview]

Scene 4: Autopilot (15s)
> /autopilot FTR-001
[Shows task execution]
✓ Task 1/3: Add User model — committed
✓ Task 2/3: Add auth service — committed
✓ Task 3/3: Add tests — committed
✓ All tasks complete!

Scene 5: Result (3s)
[Shows clean git log with 3 commits]
```

### Technical Specs

| Attribute | Value |
|-----------|-------|
| Resolution | 1200x800 (retina friendly) |
| Frame rate | 15 fps |
| Duration | 30-45 seconds |
| File size | < 5MB |
| Format | GIF (for GitHub compatibility) |
| Colors | 256 (optimized palette) |

### Tools

- **Recording:** asciinema or VHS (charmbracelet/vhs)
- **Conversion:** gifski or ffmpeg
- **Optimization:** gifsicle

---

## Implementation Plan

### Task 1: Write VHS script

**Files:**
- Create: `assets/demo/workflow.tape` (temporary)

**Steps:**
1. Install VHS: `brew install vhs`
2. Write tape file with demo script
3. Test locally

**Acceptance:**
- [ ] Script runs without errors

### Task 2: Record demo

**Steps:**
1. Run VHS to generate GIF
2. Review timing and clarity

**Acceptance:**
- [ ] Flow is clear
- [ ] Text is readable

### Task 3: Optimize GIF

**Steps:**
1. Run gifsicle optimization
2. Ensure < 5MB
3. Verify quality maintained

**Acceptance:**
- [ ] File size < 5MB
- [ ] Quality acceptable

### Task 4: Add to repo

**Files:**
- Create: `assets/demo/workflow.gif`
- Delete: `assets/demo/.gitkeep`

**Steps:**
1. Move optimized GIF to assets/demo/
2. Remove .gitkeep
3. Verify README displays correctly

**Acceptance:**
- [ ] GIF displays in README
- [ ] No broken image

### Execution Order

Task 1 → Task 2 → Task 3 → Task 4

---

## VHS Script Draft

```tape
Output workflow.gif

Set FontSize 14
Set Width 1200
Set Height 800
Set Theme "Dracula"

Type "claude"
Enter
Sleep 2s

Type "/bootstrap"
Enter
Sleep 3s

# Simulated output
Type "# Extracting idea from conversation..."
Sleep 2s

Type "✓ Created ai/idea/vision.md"
Enter
Type "✓ Created ai/idea/architecture.md"
Enter
Sleep 2s

Type "/spark Add user authentication with JWT"
Enter
Sleep 3s

Type "# Researching best practices..."
Sleep 2s
Type "✓ Found: JWT implementation patterns"
Enter
Type "✓ Created ai/features/FTR-001-user-auth.md"
Enter
Sleep 2s

Type "/autopilot FTR-001"
Enter
Sleep 2s

Type "Task 1/3: Add User model"
Enter
Type "  ✓ Coder: completed"
Enter
Type "  ✓ Tester: passed"
Enter
Type "  ✓ Committed: abc1234"
Enter
Sleep 1s

Type "Task 2/3: Add auth service"
Enter
Type "  ✓ Coder: completed"
Enter
Type "  ✓ Tester: passed"
Enter
Type "  ✓ Committed: def5678"
Enter
Sleep 1s

Type "Task 3/3: Add integration tests"
Enter
Type "  ✓ Coder: completed"
Enter
Type "  ✓ Tester: passed"
Enter
Type "  ✓ Committed: ghi9012"
Enter
Sleep 1s

Type ""
Enter
Type "✅ All tasks complete! Branch ready for review."
Sleep 3s
```

---

## Definition of Done

### Functional
- [ ] GIF shows complete /bootstrap → /spark → /autopilot flow
- [ ] Displays correctly in README on GitHub

### Technical
- [ ] File size < 5MB
- [ ] Resolution 1200x800
- [ ] Duration 30-45 seconds

### Quality
- [ ] Text readable at normal zoom
- [ ] Flow understandable without audio
- [ ] Professional appearance

---

## Autopilot Log

*(Filled by Autopilot during execution)*
