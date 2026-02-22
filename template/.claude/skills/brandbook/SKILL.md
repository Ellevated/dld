---
name: brandbook
description: Generate complete brand identity system for app launch. Strategy to store assets to marketing kit.
model: opus
---

# Brandbook — AI-Powered Brand Identity Generator

Creates complete brand identity for mobile/web apps through structured dialogue, AI research, and optional MCP image generation.

**Activation:** `brandbook`, `brandbook {app-name}`

## When to Use

- Launching new app, need visual identity from scratch
- Rebranding existing product
- Need store-ready assets specification

**Don't use:** Redesigning mature brand with existing guidelines (hire an agency)

## Principles

1. **Concrete over abstract** — HEX codes, not "blueish"; font names, not "something modern"
2. **Research-backed** — every choice has psychological/market justification
3. **Ready-to-use outputs** — AI prompts are copy-paste ready, specs are pixel-exact
4. **Accessibility-first** — WCAG AA compliance is mandatory, not optional
5. **Progressive enhancement** — MCP image gen if available, prompts-only if not
6. **Anti-convergence** — LLMs drift to "average design" (Inter, purple gradients, rounded-white-cards). Phase 0 forces emotive narrative BEFORE any visual work. All colors in OKLCH for perceptual uniformity

---

## Output

All files created in `brandbook/`:

| File | Content | Phases |
|------|---------|--------|
| `brand-dna.md` | Emotive narrative, convergence shield, archetype, personality, voice | 0-3 |
| `visual-system.md` | Colors (HEX/OKLCH), typography, accessibility validation | 4-6 |
| `logo-and-icon.md` | Concepts, AI prompts for 4 tools, tech specs | 7 |
| `motion-system.md` | Animation guidelines, video specs, motion tokens | 8 |
| `store-assets.md` | Screenshot strategy + copy, Feature Graphic | 9 |
| `marketing-kit.md` | Social specs for 7 platforms, ad strategy, tools | 10 |
| `prompts.md` | All AI prompts collected — copy-paste ready | 11 |
| `checklist.md` | "Zero to Launch" 3-day action plan | 11 |
| `brand-tokens.css` | Tailwind v4 @theme tokens — OKLCH, semantic, dark mode | 12 |
| `assets/` | Generated images (if MCP available) | 7-8 |

**Coder handoff (written outside brandbook/):**

| File | Content | Phase |
|------|---------|-------|
| `.claude/rules/brand.md` | Machine-readable brand rules for coding agents | 13 |

---

## Phase Overview

```
SHIELD:      0. Convergence Shield (emotive narrative, banned defaults, 3 directions)
             See: foundation.md

FOUNDATION:  1. Discovery → 2. Brand DNA → 3. Voice Framework
             See: foundation.md

DESIGN:      4. Research → 5. Visual System → 6. Accessibility
             → 7. Logo & Icon → 8. Motion
             See: design.md

LAUNCH:      9. Store Assets → 10. Marketing Kit
             See: launch.md

COMPILE:     11. Compilation + Checklist + MCP Generation
             12. Design Tokens Export (brand-tokens.css)
             13. Coder Handoff (.claude/rules/brand.md)
             See: completion.md
```

## Modules

| Module | When to Read | Content |
|--------|--------------|---------|
| `foundation.md` | Start | Discovery dialogue, Brand DNA, Voice Framework |
| `design.md` | After foundation | Research, colors, accessibility, logo, motion |
| `launch.md` | After design | Store assets, marketing kit |
| `completion.md` | After all phases | Compilation, checklists, MCP generation, output |

**Flow:**
```
SKILL.md → foundation.md → design.md → launch.md → completion.md
```

---

## Pre-flight

1. **Check context:** Look for files in `biz/`, `ai/` — product briefs, personas, research
2. **Migrate legacy path:** Check if `biz/brandbook/` exists (v1 output). If yes:
   - Show user: "Found previous brandbook at biz/brandbook/. Migrate to brandbook/?"
   - If approved: `mv biz/brandbook/* brandbook/ && rmdir biz/brandbook`
   - This preserves existing work (assets, docs) under the new path
3. **Detect existing brand:** Check if `.claude/rules/brand.md` exists (previous run). If yes:
   - Read the existing file
   - Show diff summary: "Previous brand: {font}, {primary color}, {archetype}"
   - Ask: "Update existing brand or start fresh?"
   - If update → pre-fill Phase 0 emotive narrative from existing, highlight what changed
4. **Detect MCP:** List available tools. Image generation tools found? → enable generation mode
5. **Create output dir:** `mkdir -p brandbook/assets`

### Asset Storage Rules

```
- MCP auto-saves all generated files to brandbook/assets/ (SAVE_MEDIA_DIR)
- After each generation: show the saved file to user (Read tool)
- Never give CDN URLs — only local paths
- Report: "Saved: brandbook/assets/{filename}"
```

### MCP Detection

**IMPORTANT:** fal-ai tools are DEFERRED — they won't appear in your tool list until you explicitly load them. You MUST use `ToolSearch` to detect and load them.

```
Step 1: Run ToolSearch with query: "fal-ai generate"
Step 2: If ToolSearch returns fal-ai tools → IMAGE_GEN_MODE = true
Step 3: If ToolSearch returns nothing   → IMAGE_GEN_MODE = false (prompts only)
```

**Do NOT skip this step. Do NOT assume tools are unavailable without running ToolSearch first.**

Available fal-ai tools (when MCP connected):

```
IMAGE: generate_image, generate_image_structured, generate_image_from_image,
       edit_image, remove_background, upscale_image, inpaint_image,
       resize_image, compose_images
VIDEO: generate_video, generate_video_from_image, generate_video_from_video
AUDIO: generate_music
UTIL:  list_models, recommend_model, get_pricing, get_usage, upload_file
```

### Recommended Models (via FAL.AI)

Use `recommend_model` tool for AI-powered suggestions, or these defaults:

| Asset | Model | Why |
|-------|-------|-----|
| Logo, icon, text-on-image | `fal-ai/recraft-v3` | #1 on leaderboard, vector+raster, best text |
| Photo-realistic imagery | `fal-ai/flux-pro/v1.1-ultra` | Top photorealism, latest Flux Pro |
| Quick iterations | `fal-ai/flux/schnell` | $0.003/image, fast |
| Banners with text | `fal-ai/recraft-v3` | Superior text rendering |
| Logo animation | `generate_video_from_image` | Animate logo directly via MCP |
| Background removal | `remove_background` | Transparent PNG via MCP |

---

## STRICT RULES

1. **READ-ONLY for app code** — never modify source files
2. **Output ONLY to brandbook/** — local, not committed (except `.claude/rules/brand.md`)
3. **Every choice needs WHY** — "Blue (#1E40AF) because fintech vertical = trust, contrast 7.2:1"
4. **Concrete values only** — no "consider using...", always exact HEX/font/size
5. **Accessibility is mandatory** — WCAG AA minimum for all color combinations
6. **Ask before MCP generation** — calls cost money, user must approve
7. **Use existing context** — if `biz/` has product briefs, pre-fill Discovery answers
8. **ALL ASSETS LOCAL** — every generated file saved to `brandbook/assets/`. No CDN links — only local paths. After generation → show image to user
9. **Anti-convergence** — NEVER start with Inter, system-ui, purple/blue gradients, or rounded-white-card aesthetics. Phase 0 Convergence Shield is MANDATORY before any visual decisions
10. **OKLCH-first** — all color values include OKLCH notation alongside HEX. OKLCH ensures perceptual uniformity across brand palette
