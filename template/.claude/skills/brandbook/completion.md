# Completion — Phase 11

## Phase 11: Compilation

### 11.1 Prompts Collection

Create `prompts.md` — all AI prompts from all phases, copy-paste ready:

```markdown
# AI Prompts Collection: {App Name}
Generated: {date}

## 1. Copywriting System Prompt (Phase 3)
{Full system prompt for LLM copywriting}

## 2. Logo / Icon Generation (Phase 7)

### Midjourney
{prompt with --sref and --v flags}

### Recraft.ai
{vector prompt}

### DALL-E 3
{prompt}

### Flux (Replicate)
{prompt}

## 3. Motion / Animation (Phase 8)

### Runway
{logo animation prompt}

## 4. Ad Creatives
{prompts for each platform based on brand + specs}

## 5. Social Media Content
{template prompts using brand voice for each content pillar}
```

### 11.2 Asset Checklist

Create `checklist.md`:

```markdown
# Brand Launch Checklist: {App Name}
Generated: {date}

## Day 1: Foundation (2-3 hours)
- [ ] Review brand-dna.md, adjust if needed
- [ ] Download fonts: {Google Fonts links}
- [ ] Test color contrast: webaim.org/resources/contrastchecker
- [ ] Set up Brand Kit in Canva or Adobe Express
  - Upload logo SVG
  - Add HEX codes: {list}
  - Upload font files

## Day 2: Visual Core (3-4 hours)
- [ ] Generate logo variants using prompts.md
- [ ] Select best, vectorize (Vectorizer.ai) if needed
- [ ] Export app icon: iOS 1024x1024 (no alpha) + Android adaptive
- [ ] Create favicon: 32x32 + 16x16
- [ ] Create OG image: 1200x630

## Day 3: Store & Marketing (2-3 hours)
- [ ] Take app screenshots (emulator or device, no status bar)
- [ ] Create store mockups (Previewed.app): 5 slides
- [ ] Add headline copy per screenshot (from store-assets.md)
- [ ] Create Feature Graphic 1024x500 (Google Play)
- [ ] Create social banners: resize from master template
- [ ] Set up social profiles with brand assets

## Week 2: Polish (optional)
- [ ] Create logo animation (Runway / LottieFiles)
- [ ] Set up content calendar using pillars
- [ ] Generate first batch of ad creatives
- [ ] Create Product Hunt gallery (1270x760)
- [ ] Write App Store description using brand voice
```

### 11.3 File Naming Convention

Include in checklist:

```
{app-name}_{asset}_{variant}_{size}.{fmt}

Examples:
ellevated_logo_full-color_1024x1024.png
ellevated_icon_ios_1024x1024.png
ellevated_icon_android-adaptive_1024x1024.png
ellevated_favicon_32x32.ico
ellevated_og-image_1200x630.png
ellevated_screenshot_01-hero_1290x2796.png
ellevated_banner_twitter-header_1500x500.png
```

---

## MCP Media Generation (if IMAGE_GEN_MODE = true)

### Pre-generation Checklist

Before generating, confirm with user:
1. Which assets to generate (logo, icon, banners, OG image, video, music)
2. How many variations per asset (recommend 3-4 for logo)
3. Budget awareness — use `get_pricing` tool to check costs:
   - Flux Schnell: ~$0.003/image
   - Recraft V3: ~$0.03/image
   - Flux Pro Ultra: ~$0.05/image
   - Video generation: varies by model
4. Use `get_usage` to check current spending

### Generation Workflow

```
For each approved asset:
1. Call MCP tool → file auto-saves to brandbook/assets/
2. Show saved file to user (Read tool)
3. Ask: keep / regenerate / skip
```

No CDN links. No downloads. Everything lands in `brandbook/assets/` automatically.

### Recommended Models by Asset

Use `recommend_model` for AI-powered suggestions, or these defaults:

| Asset | Tool | Model ID | Price | Why |
|-------|------|---------|-------|-----|
| Logo, icon | `generate_image` | `fal-ai/recraft-v3` | ~$0.03 | #1 leaderboard, vector, best text |
| Photo imagery | `generate_image` | `fal-ai/flux-pro/v1.1-ultra` | ~$0.05 | Top photorealism |
| Quick iterations | `generate_image` | `fal-ai/flux/schnell` | ~$0.003 | Fast + cheap |
| Banners with text | `generate_image` | `fal-ai/recraft-v3` | ~$0.03 | Superior text rendering |
| OG Image | `generate_image` | `fal-ai/flux-pro/v1.1-ultra` | ~$0.05 | High quality |
| Transparent logo | `remove_background` | — | — | Auto tool |
| Hi-res for print | `upscale_image` | — | — | 2x/4x |
| Social media sizes | `resize_image` | — | — | Auto-crop for platforms |
| Logo animation | `generate_video_from_image` | — | varies | Animate static logo |
| Brand jingle | `generate_music` | — | varies | Instrumental or vocals |

### Post-generation Pipeline

```
All files auto-save to brandbook/assets/

Logo:    generate_image → remove_background → upscale_image → resize_image
Banner:  generate_image → resize_image (for each platform)
Motion:  upload_file (logo) → generate_video_from_image
```

After all generation: `ls -la brandbook/assets/`

### If IMAGE_GEN_MODE = false

All prompts are collected in `prompts.md` for manual use in:
- Midjourney, Recraft.ai, DALL-E, or any image AI
- User generates externally, then saves files to `brandbook/assets/`

---

## Phase 12: Design Tokens Export

**Goal:** Machine-readable brand values for Tailwind v4 / CSS. Write `brandbook/brand-tokens.css`.

### Template

```css
/* ============================================
   Brand Tokens: {App Name}
   Generated: {date} by /brandbook

   Usage: @import "brand-tokens.css" in your main CSS
   Tailwind v4: These integrate with @theme automatically
   ============================================ */

/* --- PRIMITIVES (raw OKLCH values) --- */
@theme {
  /* Brand Colors */
  --color-brand: oklch({L}% {C} {H});
  --color-brand-light: oklch({L}% {C} {H});
  --color-brand-dark: oklch({L}% {C} {H});
  --color-accent: oklch({L}% {C} {H});

  /* Neutrals */
  --color-neutral-50: oklch({L}% {C} {H});
  --color-neutral-100: oklch({L}% {C} {H});
  --color-neutral-200: oklch({L}% {C} {H});
  --color-neutral-300: oklch({L}% {C} {H});
  --color-neutral-500: oklch({L}% {C} {H});
  --color-neutral-700: oklch({L}% {C} {H});
  --color-neutral-900: oklch({L}% {C} {H});

  /* Semantic */
  --color-success: oklch({L}% {C} {H});
  --color-error: oklch({L}% {C} {H});
  --color-warning: oklch({L}% {C} {H});
  --color-info: oklch({L}% {C} {H});

  /* --- SEMANTIC TOKENS (mapped from primitives) --- */
  --color-bg: var(--color-neutral-50);
  --color-surface: var(--color-neutral-100);
  --color-border: var(--color-neutral-300);
  --color-text: var(--color-neutral-900);
  --color-text-secondary: var(--color-neutral-500);
  --color-cta: var(--color-brand);
  --color-cta-hover: var(--color-brand-light);
  --color-cta-active: var(--color-brand-dark);

  /* --- TYPOGRAPHY --- */
  --font-display: "{Display Font}", {fallback-stack};
  --font-body: "{Body Font}", {fallback-stack};

  --text-h1: 2rem;      /* 32px */
  --text-h2: 1.5rem;    /* 24px */
  --text-h3: 1.25rem;   /* 20px */
  --text-body: 1rem;    /* 16px */
  --text-caption: 0.875rem; /* 14px */
  --text-small: 0.75rem;    /* 12px */

  --leading-tight: 1.2;
  --leading-normal: 1.5;
  --leading-relaxed: 1.6;

  /* --- SPACING --- */
  --space-xs: 0.25rem;  /* 4px */
  --space-sm: 0.5rem;   /* 8px */
  --space-md: 1rem;     /* 16px */
  --space-lg: 1.5rem;   /* 24px */
  --space-xl: 2rem;     /* 32px */
  --space-2xl: 3rem;    /* 48px */

  /* --- RADIUS --- */
  --radius-sm: {from brand personality}px;
  --radius-md: {from brand personality}px;
  --radius-lg: {from brand personality}px;
  --radius-full: 9999px;

  /* --- SHADOWS --- */
  --shadow-sm: 0 1px 2px oklch(0% 0 0 / 0.05);
  --shadow-md: 0 4px 6px oklch(0% 0 0 / 0.07);
  --shadow-lg: 0 10px 15px oklch(0% 0 0 / 0.1);

  /* --- MOTION (from Phase 8.5) --- */
  --motion-duration-instant: 100ms;
  --motion-duration-fast: {value}ms;
  --motion-duration-normal: {value}ms;
  --motion-duration-slow: {value}ms;
  --motion-easing-default: {cubic-bezier(...)};
  --motion-easing-enter: {cubic-bezier(...)};
  --motion-easing-exit: {cubic-bezier(...)};
}

/* --- DARK MODE OVERRIDES --- */
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: var(--color-neutral-900);
    --color-surface: var(--color-neutral-700);
    --color-border: var(--color-neutral-500);
    --color-text: var(--color-neutral-50);
    --color-text-secondary: var(--color-neutral-300);
    /* Brand color: adjust lightness if needed for dark backgrounds */
  }
}

/* --- REDUCED MOTION --- */
@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-duration-instant: 0ms;
    --motion-duration-fast: 0ms;
    --motion-duration-normal: 0ms;
    --motion-duration-slow: 0ms;
  }
}
```

**Rules:**
- Replace ALL `{placeholders}` with actual values from Phases 5-8
- OKLCH values must match HEX values from `visual-system.md`
- Radius values derive from brand personality (Rebel → 0px, Caregiver → 16px, etc.)
- Test: open file in browser devtools to verify all tokens resolve

---

## Phase 13: Coder Handoff

**Goal:** Write `.claude/rules/brand.md` — a machine-readable brand reference that coding agents load automatically. This ensures brand consistency across all AI-assisted development.

### Template

Write to `.claude/rules/brand.md`:

```markdown
# Brand: {App Name}

Generated by /brandbook on {date}. Machine-readable reference for coding agents.

## Colors

| Token | HEX | OKLCH | Usage |
|-------|-----|-------|-------|
| brand | {value} | {value} | Primary CTA, links, logo |
| brand-light | {value} | {value} | Hover states, highlights |
| brand-dark | {value} | {value} | Active states, headers |
| accent | {value} | {value} | Secondary actions |
| success | {value} | {value} | Confirmations |
| error | {value} | {value} | Errors, destructive actions |
| warning | {value} | {value} | Caution states |
| info | {value} | {value} | Informational |

## Typography

| Role | Font | Weight | Google Fonts |
|------|------|--------|--------------|
| Display | {name} | {weights} | `{url}` |
| Body | {name} | {weights} | `{url}` |

**Fallback stack:** `{display fallback}` / `{body fallback}`

## WCAG Validated Combinations

These combos are pre-validated to WCAG AA (4.5:1 minimum):

| Foreground | Background | Ratio | Use For |
|-----------|------------|-------|---------|
| {hex} | {hex} | {ratio}:1 | Body text on light bg |
| {hex} | {hex} | {ratio}:1 | Body text on dark bg |
| {hex} | {hex} | {ratio}:1 | CTA text on brand bg |
| {hex} | {hex} | {ratio}:1 | Heading on surface |

## ALWAYS Use

- Brand tokens from `brandbook/brand-tokens.css` (import via `@import`)
- OKLCH color notation in new CSS
- Font pair: {display} + {body}
- Semantic color tokens (`--color-cta`, `--color-bg`) not raw values
- `prefers-reduced-motion` media query for animations
- `prefers-color-scheme: dark` for dark mode

## NEVER Use

- Inter, system-ui, or Roboto as primary fonts
- Raw HEX values instead of CSS custom properties
- Colors not in the approved palette
- Border-radius values not from tokens
- Animations longer than {max-duration from archetype}ms
- Gradients (unless specifically approved in visual-system.md)

## Design Tokens Location

Import in your CSS:
\`\`\`css
@import "../brandbook/brand-tokens.css";
\`\`\`

## Multi-Project Reuse

To use this brand in another project:
1. Copy `brandbook/brand-tokens.css` to the new project
2. Copy this file (`.claude/rules/brand.md`) to `.claude/rules/brand.md`
3. Coding agents will automatically pick up brand rules
```

**Rules:**
- Fill ALL placeholders from Phase 5-8 outputs
- Every color must have both HEX and OKLCH
- WCAG combos must be actually validated (from Phase 6)
- ALWAYS/NEVER lists must be specific to THIS brand, not generic

---

## Final Report

After ALL files are written, present summary:

```
Brandbook for {App Name} — Complete

Documents:
brandbook/
  brand-dna.md          — emotive narrative, archetype, voice, descriptors
  visual-system.md      — colors (HEX+OKLCH), fonts, accessibility
  logo-and-icon.md      — concepts, prompts, specs
  motion-system.md      — animation guidelines, motion tokens
  store-assets.md       — screenshots, feature graphic
  marketing-kit.md      — social, ads, tools
  prompts.md            — all AI prompts (copy-paste ready)
  checklist.md          — 3-day action plan
  brand-tokens.css      — Tailwind v4 @theme tokens (OKLCH + dark mode)

Coder handoff:
.claude/rules/brand.md  — machine-readable brand rules (loaded by coding agents)

Assets (all local):
brandbook/assets/
  (run ls -la to show actual files)

Next steps:
1. Follow checklist.md: Day 1 → Day 2 → Day 3
2. Import brand-tokens.css in your project CSS
3. Coding agents now auto-load brand rules from .claude/rules/brand.md
4. All assets on disk — open brandbook/assets/
5. Upload to Canva/Adobe Express Brand Kit
```

---

## Brand Health Check (6 months post-launch)

Include this template at the end of `checklist.md`:

```markdown
## 6-Month Brand Health Check
- [ ] Are all materials using approved colors? (Check HEX codes)
- [ ] Is typography consistent across app and marketing?
- [ ] Do new screenshots match the original style?
- [ ] Has the voice drifted? (Compare recent copy to brand-dna.md)
- [ ] Are accessibility standards still met after UI updates?
- [ ] Does the logo still work at all required sizes?
→ If 2+ items fail: re-run /brandbook for refresh
```
