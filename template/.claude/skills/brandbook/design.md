# Design — Phases 4-8

> **CONVERGENCE CHECK:** Before starting any phase below, re-read the Emotive Narrative and chosen Aesthetic Direction from Phase 0 (in `brand-dna.md`). Every visual decision must trace back to those anchors. If you catch yourself defaulting to "safe, modern, minimal" — you've drifted.

## Phase 4: Research (Scout)

Dispatch Scout agent for competitor and trend analysis:

```
Task tool → scout agent:
"Research visual identity for {vertical} apps in 2026.
Competitors: {list from Discovery}.
Find:
1. Color trends for {vertical} (specific HEX examples)
2. Typography trends (popular font pairs)
3. Icon style trends (flat/3D/neumorphic/glassmorphic)
4. Store screenshot patterns (layout, copy style)
5. Motion/animation trends
6. Competitor voice and messaging patterns
Focus on what performs NOW in 2026, not generic theory."
```

**After research:** Validate or adjust Brand DNA decisions. Document reasoning.

---

## Phase 5: Visual System

### 5.1 Color Palette

**Color psychology by vertical (2026 trends):**

| Vertical | Direction | Avoid |
|----------|-----------|-------|
| Fintech | Deep black + neon purple/green | Corporate blue (overused) |
| Health | Sage, beige, warm gray | Bright aggressive colors |
| Social/GenZ | Dopamine colors (saturated) | Muted pastels |
| Productivity | Monochrome + 1 accent | Rainbow palettes |
| Education | Warm blues, amber accents | Dark/heavy tones |

**Generate this structure:**

```markdown
### Primary
| Role | HEX | RGB | Usage |
|------|-----|-----|-------|
| Brand | #XXXXXX | rgb(X,X,X) | Logo, primary CTA, links |
| Brand Light | #XXXXXX | rgb(X,X,X) | Hover, highlights, backgrounds |
| Brand Dark | #XXXXXX | rgb(X,X,X) | Pressed states, headers |

### Neutrals
| Step | HEX | Usage |
|------|-----|-------|
| 50 | #FAFAFA | Page background |
| 100 | #F5F5F5 | Card background |
| 200 | #E5E5E5 | Dividers |
| 300 | #D4D4D4 | Borders |
| 500 | #737373 | Secondary text |
| 700 | #404040 | Primary text |
| 900 | #171717 | Headings |

### Semantic
| Role | HEX | Usage |
|------|-----|-------|
| Success | #XXXXXX | Confirmations |
| Error | #XXXXXX | Errors, destructive |
| Warning | #XXXXXX | Caution |
| Info | #XXXXXX | Tips, information |

### Dark Mode Mapping
| Light | Dark | Element |
|-------|------|---------|
| #XXXXXX | #XXXXXX | Background |
| #XXXXXX | #XXXXXX | Surface |
| #XXXXXX | #XXXXXX | Text |
| Brand stays same or adjust lightness | | Brand |
```

### 5.1a Three Palette Directions

Present 3 distinct palettes tied to the chosen Aesthetic Direction from Phase 0. User picks one — do not blend.

| | Conservative | Bold | Experimental |
|---|---|---|---|
| **Primary** | Safe, industry-aligned | Distinctive, high-contrast | Unexpected, rule-breaking |
| **Neutral strategy** | Warm/cool grays | Tinted neutrals | Chromatic neutrals |
| **Accent approach** | Single accent | Complementary pair | Triadic or split-comp |

For each palette, provide:

```markdown
#### Palette {A/B/C}: {Name}

| Role | HEX | OKLCH | Usage |
|------|-----|-------|-------|
| Primary | #XXXXXX | oklch(L% C H) | Logo, primary CTA |
| Primary Light | #XXXXXX | oklch(L% C H) | Hover, highlights |
| Primary Dark | #XXXXXX | oklch(L% C H) | Pressed, headers |
| Accent | #XXXXXX | oklch(L% C H) | Secondary actions |
| Neutral 50 | #XXXXXX | oklch(L% C H) | Page background |
| Neutral 900 | #XXXXXX | oklch(L% C H) | Headings |
```

> **OKLCH note:** Use `oklch(lightness% chroma hue)` — perceptually uniform, CSS Color Level 4 standard. Generate OKLCH from HEX, never the reverse. Tools: oklch.com, css.land/lch

### How to Present Palette Choices Visually

**Users cannot pick colors from HEX codes in a terminal.** Generate an HTML preview:

1. Write `brandbook/palette-preview.html` with visual swatches for all 3 palettes
2. Open in browser: `open brandbook/palette-preview.html` (macOS) / `xdg-open` (Linux)
3. After user sees the visual, use `AskUserQuestion` to record their choice

**HTML template for palette preview:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{App Name} — Palette Directions</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui; background: #f5f5f5; padding: 40px; }
  h1 { text-align: center; margin-bottom: 40px; font-size: 24px; }
  .directions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px; max-width: 1200px; margin: 0 auto; }
  .direction { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .direction h2 { font-size: 18px; margin-bottom: 8px; }
  .direction .mood { color: #666; font-size: 14px; margin-bottom: 16px; }
  .swatch-row { display: flex; gap: 8px; margin-bottom: 12px; }
  .swatch { width: 64px; height: 64px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.1); }
  .swatch-label { font-size: 11px; color: #999; text-align: center; margin-top: 4px; }
  .swatch-group { text-align: center; }
  .section-label { font-size: 12px; font-weight: 600; color: #333; margin: 12px 0 8px; }
  .sample-ui { border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-top: 16px; }
  .sample-btn { display: inline-block; padding: 8px 24px; border-radius: 6px; color: white; font-weight: 600; font-size: 14px; }
  .sample-text { font-size: 14px; margin: 8px 0; }
</style>
</head>
<body>
<h1>🎨 {App Name} — Choose Your Palette Direction</h1>
<div class="directions">

  <!-- REPEAT FOR EACH DIRECTION A/B/C -->
  <div class="direction">
    <h2>A: Conservative</h2>
    <p class="mood">{5 mood words}. {Reference world}.</p>

    <div class="section-label">Primary</div>
    <div class="swatch-row">
      <div class="swatch-group">
        <div class="swatch" style="background: {primary-hex};"></div>
        <div class="swatch-label">{primary-hex}</div>
      </div>
      <div class="swatch-group">
        <div class="swatch" style="background: {primary-light-hex};"></div>
        <div class="swatch-label">Light</div>
      </div>
      <div class="swatch-group">
        <div class="swatch" style="background: {primary-dark-hex};"></div>
        <div class="swatch-label">Dark</div>
      </div>
      <div class="swatch-group">
        <div class="swatch" style="background: {accent-hex};"></div>
        <div class="swatch-label">Accent</div>
      </div>
    </div>

    <div class="section-label">Neutrals</div>
    <div class="swatch-row">
      <div class="swatch-group">
        <div class="swatch" style="background: {n50};"></div>
        <div class="swatch-label">50</div>
      </div>
      <div class="swatch-group">
        <div class="swatch" style="background: {n200};"></div>
        <div class="swatch-label">200</div>
      </div>
      <div class="swatch-group">
        <div class="swatch" style="background: {n500};"></div>
        <div class="swatch-label">500</div>
      </div>
      <div class="swatch-group">
        <div class="swatch" style="background: {n900};"></div>
        <div class="swatch-label">900</div>
      </div>
    </div>

    <!-- Sample UI -->
    <div class="sample-ui" style="background: {n50};">
      <div class="sample-text" style="color: {n900};">How your UI will feel</div>
      <div class="sample-btn" style="background: {primary-hex};">Get Started</div>
    </div>
  </div>
  <!-- END REPEAT -->

</div>
</body>
</html>
```

**After generating:** `open brandbook/palette-preview.html`

Then use `AskUserQuestion`:

```
AskUserQuestion:
  question: "Which color palette direction? (preview open in browser)"
  header: "Palette"
  options:
    - label: "A: Conservative"
      description: "{mood} — {reference world}"
    - label: "B: Bold"
      description: "{mood} — {reference world}"
    - label: "C: Experimental"
      description: "{mood} — {reference world}"
```

**User picks one palette. Then fill out the full Primary/Neutrals/Semantic/Dark Mode table (5.1 format) for the chosen palette.**

### 5.2a Three Font Pair Directions

Present 3 font pair options — one for each personality range. User picks one.

| Direction | Display Font | Body Font | Personality | Google Fonts |
|-----------|-------------|-----------|-------------|--------------|
| **Safe** | {name} | {name} | Professional, proven | Yes/No |
| **Distinctive** | {name} | {name} | Memorable, character | Yes/No |
| **Experimental** | {name} | {name} | Unexpected, bold | Yes/No |

**Rules:**
- NEVER suggest Inter, system-ui, or Roboto as the first option
- At least one pair must include a non-Google-Fonts option (with fallback)
- Each pair must be visually distinct from the others
- Include weight range and OpenType features available

### How to Present Font Choices Visually

**Users cannot evaluate fonts from names alone.** Add font specimens to the palette preview HTML, or generate a separate `brandbook/font-preview.html`.

**Add to the palette HTML or create separate file:**

```html
<!-- Font preview section (add Google Fonts import in <head>) -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={Font1}:wght@400;600;700&family={Font2}:wght@400;500&display=swap">

<div class="font-directions">
  <!-- REPEAT FOR EACH DIRECTION -->
  <div class="font-option">
    <h3>A: Safe — {Display} + {Body}</h3>
    <p style="font-family: '{Display}'; font-size: 32px; font-weight: 700;">{App Name}</p>
    <p style="font-family: '{Display}'; font-size: 24px; font-weight: 600;">The quick brown fox jumps</p>
    <p style="font-family: '{Body}'; font-size: 16px; line-height: 1.5;">
      Body text sample. This is how your app's main content will look.
      Reading comfort and clarity at 16px with 1.5 line height.
    </p>
    <p style="font-family: '{Body}'; font-size: 14px; color: #666;">
      Caption: Secondary text, timestamps, labels
    </p>
  </div>
</div>
```

> **Tip:** Combine palette + font previews in ONE HTML file. Show each direction as a complete mini-mockup: colors + typography together. This gives the most realistic feel.

**After generating:** `open brandbook/font-preview.html` (or palette-preview.html if combined)

Then use `AskUserQuestion`:

```
AskUserQuestion:
  question: "Which font pair fits the brand? (preview open in browser)"
  header: "Typography"
  options:
    - label: "A: Safe — {Display} + {Body}"
      description: "Professional, proven, Google Fonts available"
    - label: "B: Distinctive — {Display} + {Body}"
      description: "Memorable, has character"
    - label: "C: Experimental — {Display} + {Body}"
      description: "Unexpected, bold choice"
```

**User picks one pair. Then fill the full Scale table (5.2 format).**

### 5.2 Typography

```markdown
### Font Pair
| Role | Font | Weight | Link |
|------|------|--------|------|
| Display | {Name} | 600-700 | fonts.google.com/specimen/{Name} |
| Body | {Name} | 400-500 | fonts.google.com/specimen/{Name} |

### Scale
| Level | Size | Line Height | Weight | Usage |
|-------|------|-------------|--------|-------|
| H1 | 32px | 1.2 | 700 | Page titles |
| H2 | 24px | 1.3 | 600 | Sections |
| H3 | 20px | 1.3 | 600 | Subsections |
| Body | 16px | 1.5 | 400 | Main text |
| Caption | 14px | 1.4 | 400 | Secondary |
| Small | 12px | 1.4 | 500 | Labels, badges |
```

---

## Phase 6: Accessibility Validation

**WCAG 2.2 AA — mandatory for all color combos.**

### 6.1 Contrast Ratios

For EVERY text+background combination:

| Combo | Foreground | Background | Ratio | Pass? |
|-------|-----------|------------|-------|-------|
| Body on light | #XXXXXX | #XXXXXX | X.X:1 | >=4.5:1 |
| Body on dark | #XXXXXX | #XXXXXX | X.X:1 | >=4.5:1 |
| Large text | #XXXXXX | #XXXXXX | X.X:1 | >=3:1 |
| CTA text | #XXXXXX | #XXXXXX | X.X:1 | >=4.5:1 |
| Link on bg | #XXXXXX | #XXXXXX | X.X:1 | >=4.5:1 |

**Formula:** `(L1 + 0.05) / (L2 + 0.05)` where L = relative luminance.

### 6.2 Color Blindness Check

Verify brand colors are distinguishable under:
- Protanopia (red-blind, ~1% males)
- Deuteranopia (green-blind, ~1% males)
- Tritanopia (blue-blind, rare)

**Rule:** Never use color ALONE to convey meaning. Always pair with icon or text.

### 6.3 Remediation

If any combo fails → adjust lightness while preserving hue.
Document both original intent and adjusted accessible version.

**Output:** Write `visual-system.md` (phases 5-6 combined).

---

## Phase 7: Logo & Icon

### 7.1 Concept

Describe logo concept in words BEFORE any generation:
- Symbol/icon: what it depicts and why
- Connection to brand archetype
- How it works at small sizes (16px favicon)

### 7.2 AI Prompts

#### MCP Direct Generation (preferred — auto-saves to disk)

**Recraft V3 via `generate_image` (BEST for logos):**
```
model: fal-ai/recraft-v3
prompt: Vector app icon for "{app name}". Concept: {concept}.
Style: {visual descriptors}. Colors: {primary HEX} on {background HEX}.
Minimal, modern, professional. No text in icon.
```

**Flux Schnell via `generate_image` (fast iterations, $0.003):**
```
model: fal-ai/flux/schnell (or alias: flux_schnell)
prompt: Minimalist app icon, {concept}, {visual descriptors},
{primary color} palette, vector style, clean edges,
no text, white background, professional quality
```

**Flux Pro Ultra via `generate_image` (highest quality):**
```
model: fal-ai/flux-pro/v1.1-ultra
prompt: Professional app icon for "{app name}", {concept},
{visual descriptors}, {primary HEX} color palette,
clean minimal design, no text, studio quality
```

**Structured generation via `generate_image_structured` (fine control):**
```
Use for precise control over composition, lighting, subjects.
Specify exact layout, color positions, element placement.
```

#### External Tool Prompts (copy-paste for manual use)

**Midjourney:**
```
ios app icon for {app description}, {visual descriptors},
{archetype-inspired elements}, flat design,
solid {brand-color} background, minimal, clean edges
--sref {style-ref-url} --v 6.1 --ar 1:1
```

**DALL-E 3:**
```
A minimalist app icon for "{app name}": {concept}.
Style: {visual descriptors}.
Color: {primary HEX} on {background HEX}.
Modern, clean, professional. No text. Square format.
```

**Recraft.ai (web):**
```
Vector app icon: {concept}. Style: {visual descriptors}.
Colors: {primary HEX} on {background HEX}.
Minimal, modern, {archetype} archetype feel. No text.
```

### 7.3 Technical Specs

| Asset | Size | Format | Notes |
|-------|------|--------|-------|
| App Icon (iOS) | 1024x1024 | PNG, no alpha | System rounds corners |
| App Icon (Android) | 1024x1024 | PNG, adaptive | 108dp canvas, 66dp safe |
| Favicon | 32x32, 16x16 | PNG/ICO | Simplified version |
| Logo Mark | Vector | SVG | Full color + monochrome |
| Wordmark | Vector | SVG | App name in display font |
| OG Image | 1200x630 | PNG | Social sharing default |

### 7.4 Logo Variations

| Variant | When to Use |
|---------|------------|
| Full (icon + wordmark) | Website header, splash screen |
| Icon only | App icon, favicon, small spaces |
| Wordmark only | Legal, documents, footer |
| Monochrome | Single-color contexts, watermarks |
| Reversed | Dark backgrounds |

**Output:** Write `logo-and-icon.md`.

---

## Phase 8: Motion System

### 8.1 Motion Principles by Archetype

| Archetype | Style | Duration | Easing |
|-----------|-------|----------|--------|
| Creator | Expressive, flowing | 400-600ms | ease-in-out |
| Sage | Subtle, precise | 200-300ms | ease-out |
| Hero | Bold, impactful | 300-500ms | spring |
| Magician | Smooth, transformative | 400-600ms | cubic-bezier |
| Jester | Bouncy, playful | 250-400ms | spring(bounce) |
| Rebel | Sharp, snappy | 150-250ms | ease-in |
| Everyman | Natural, comfortable | 250-400ms | ease-out |
| Caregiver | Gentle, soft | 400-600ms | ease-in-out |

### 8.2 Animation Specs

| Element | Animation | Duration | Format |
|---------|-----------|----------|--------|
| Logo intro | {describe based on archetype} | 2-3s | MP4, GIF, Lottie |
| Screen transitions | {describe} | 300ms | CSS / Lottie |
| Button feedback | {describe} | 150ms | CSS |
| Loading state | {describe} | Loop | Lottie |
| Micro-interactions | {describe} | 100-200ms | CSS |

### 8.3 Motion AI Prompts

#### MCP Direct Generation (preferred)

**Logo animation via `generate_video_from_image`:**
```
Upload logo image with upload_file, then:
generate_video_from_image:
  image: {uploaded logo path}
  prompt: Smooth {archetype motion style} animation of this logo,
  {brand color} background, professional motion design,
  3 seconds, seamless loop
```

**Video restyling via `generate_video_from_video`:**
```
Restyle existing video in brand colors and style.
Apply {visual descriptors} aesthetic to footage.
```

#### External Tool Prompts

**Runway:**
```
Animate this logo: {description}.
Motion style: {archetype motion style}.
Duration: 3 seconds. Background: {brand color}.
Professional, smooth, brand-appropriate.
```

### 8.4 Motion Don'ts

- No motion for motion's sake
- Never exceed 600ms for UI transitions
- No autoplay video with sound
- Respect `prefers-reduced-motion` media query

### 8.5 Motion Tokens (CSS Custom Properties)

Export motion values as CSS custom properties for `brand-tokens.css` (Phase 12):

```css
/* Motion Tokens — generated from Phase 8 */
--motion-duration-instant: 100ms;
--motion-duration-fast: {from 8.1}ms;
--motion-duration-normal: {from 8.1}ms;
--motion-duration-slow: {from 8.1}ms;
--motion-duration-intro: 2000ms;

--motion-easing-default: {from archetype, e.g., cubic-bezier(0.4, 0, 0.2, 1)};
--motion-easing-enter: {e.g., cubic-bezier(0, 0, 0.2, 1)};
--motion-easing-exit: {e.g., cubic-bezier(0.4, 0, 1, 1)};
--motion-easing-spring: {if archetype uses spring};

--motion-stagger-delay: 50ms;
--motion-stagger-max: 5;
```

> Include the `@media (prefers-reduced-motion: reduce)` override that sets all durations to 0ms.

**Output:** Write `motion-system.md`.

**Then proceed to:** `launch.md`
