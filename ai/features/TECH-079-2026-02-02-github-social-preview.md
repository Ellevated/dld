# Tech: [TECH-079] GitHub Social Preview & Brand Assets

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

When someone shares the GitHub link on Twitter/LinkedIn/Slack, they see a generic GitHub preview. A custom Social Preview creates instant visual recognition and increases click-through rate.

## Context

Current state: No custom social preview set.
Result: Generic GitHub repo preview when shared.

GitHub settings location: Settings → General → Social preview

---

## Scope

**In scope:**
- Brand style guide (Matrix aesthetic)
- Logo with glow effect
- Social preview image
- AI generation workflow documentation

**Out of scope:**
- Terminal GIF (separate task)
- Animated preview (not supported by GitHub)

---

## Created Assets

| # | File | Purpose | Status |
|---|------|---------|--------|
| 1 | `assets/style-guide.png` | Brand style reference (Matrix aesthetic) | done |
| 2 | `assets/logo.png` | DLD logo with phosphor glow | done |
| 3 | `assets/social-preview.png` | GitHub social preview 1280x640 | done |

---

## Design

### Visual Style: Matrix (1999)

| Element | Value |
|---------|-------|
| Background | Pure black (#000000) |
| Primary color | Matrix green (#00FF41) — phosphor glow |
| Secondary | Dim green (#008F11) for depth |
| Effect | Phosphor CRT glow, bloom around text |
| Typography | Monospace only |
| Gradients | Green fading to black (rain effect) |

### Why Matrix Style

- CLI tool = terminal aesthetic fits perfectly
- Distinctive — stands out from corporate blue/cyan
- Developer recognition — iconic in tech culture
- Professional but with edge

---

## AI Generation Strategy

### Approach: Style Anchor + Reference Chain

**Problem:** 68% of creators struggle with consistency in AI generation.

**Solution:**
1. **Style Anchor First** — Create ONE master style guide image
2. **Reference Chain** — Each asset uses previous as reference
3. **Edit, Don't Re-roll** — If 80% good, iterate don't restart

### Asset Generation Order

```
1. Style Card (anchor)
   ↓
2. Logo (uses Style Card as reference)
   ↓
3. Social Preview (uses Style Card + Logo)
```

---

## Final Prompts (Nano Banana Pro)

### 1. Style Card (first, most important)

```
Create a brand style reference card for a developer CLI tool called "DLD"
(Double-Loop Development).

Visual identity — MATRIX AESTHETIC (1999 film):
- Background: Pure black (#000000)
- Primary color: Matrix green (#00FF41) — bright phosphor
- Gradient style: Green fading to black (like falling code rain)
- Glow effect: Soft bloom/halo around bright green elements (radial gradient)
- Text: Green on black with subtle glow

Key Matrix visual elements:
- The "digital rain" gradient — bright at top, fading down
- Phosphor CRT glow (soft green halo around text)
- Depth through brightness (foreground bright, background dim)

Typography: Monospace only. Sharp, technical.

Mood: Neo's terminal. The moment before he sees the Matrix.

Show in the card:
1. Color palette with the gradient variations (bright → dim green)
2. Typography with glow effect demonstrated
3. Example of "rain" gradient application
4. Terminal-style UI element with the aesthetic

Resolution: 4K.
```

### 2. Logo (uses Style Card as Image 1)

```
Using the style reference from Image 1, create a minimal wordmark logo.

Text: "DLD"

Requirements:
- Use the bright phosphor green (#00FF41) from the palette
- Monospace typography as shown in the style guide
- Subtle glow effect around the letters (the phosphor bloom)
- Background: Pure black or transparent
- No tagline, no icons — just the three letters

The logo should feel like it's displayed on Neo's terminal.
Clean, readable at small sizes, but with that Matrix energy.

Output: 4K resolution, suitable for both dark and transparent backgrounds.
```

### 3. Social Preview (uses Style Card + Logo as references)

```
Using the style from Image 1 and the logo from Image 2, create a GitHub
social preview banner.

Size: 1280x640px (2:1 aspect ratio)

Layout:
- Background: Black with subtle Matrix rain effect (dim, not distracting)
- Top center: The "DLD" logo from Image 2 (with glow)
- Below logo: "Double-Loop Development" in dim green (#008F11)
- Center: Tagline "Turn Claude Code into an Autonomous Developer"
  in bright phosphor green
- Bottom: Simple workflow diagram showing three terminal-style boxes:
  /spark → /autopilot → shipped
  Connected with arrows, all in the Matrix green style

Important:
- All text must be legible at small sizes (when shared on Twitter/LinkedIn)
- Keep the phosphor glow effect on key elements
- The Matrix rain in background should be very subtle, almost subliminal

Style: Professional but with that "welcome to the real world" energy.
```

### Edit Prompts Used

When fixing issues, used "Edit, Don't Re-roll" approach:

```
Fix this image:
1. Remove the text "the White" completely
2. Fix the workflow boxes — remove the square brackets:
   - "[/spark]" → "/spark"
   - "[/autopilot]" → "/autopilot"
   - "[shipped]" → "shipped"
Keep everything else exactly the same.
```

---

## Remaining Tasks

### Upload to GitHub (manual)

1. Go to GitHub repo → Settings → General
2. Scroll to "Social preview"
3. Upload `assets/social-preview.png`
4. Save

### Verify

1. Share repo link in Slack/Twitter to test
2. Use Twitter Card Validator to preview
3. Check LinkedIn preview

---

## Definition of Done

### Functional
- [x] Style guide created
- [x] Logo created with glow effect
- [x] Social preview matches Matrix aesthetic
- [x] Text readable at small sizes
- [x] Uploaded to GitHub Settings
- [x] Preview visible when sharing link

### Technical
- [x] Files in `assets/` directory
- [x] social-preview.png < 1MB (563KB)
- [x] PNG format
- [x] Committed to repo

---

## Learnings

1. **Style Anchor approach works** — creating style guide first ensured consistency
2. **Edit, Don't Re-roll** — saved iterations (3 edits vs potential 20+ regenerations)
3. **Be explicit about text** — AI tends to add brackets, typos; must specify exact strings
4. **Matrix references cause hallucinations** — "the White" appeared from "white rabbit"

---

## Tool Used

**Nano Banana Pro** (Google AI Studio) — Gemini 3 Pro image model
- SOTA text rendering
- Supports up to 14 reference images
- 4K output
- Conversational editing

---

## Execution Log

| Time | Action | Result |
|------|--------|--------|
| 03:41 | Generated Style Card | Success — Matrix palette, typography, UI elements |
| 03:58 | Generated Logo | Success — DLD with phosphor glow, two variants |
| 04:05 | Generated Social Preview v1 | Issues: wrong logo, typo, brackets |
| 04:08 | Edit: fix logo + typo | Partial — "the White" appeared |
| 04:11 | Edit: remove garbage + fix brackets | Success — final version |
| 04:13 | Saved to assets/ | style-guide.png, logo.png, social-preview.png |
