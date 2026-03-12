# Foundation — Phases 0-3

## Phase 0: Convergence Shield

**Goal:** Prevent LLM drift to "average design". Establish brand's unique aesthetic territory BEFORE any visual decisions.

> **Why this exists:** LLMs consistently converge on Inter/system-ui, purple-blue gradients, rounded-white-card layouts. This phase forces divergence by anchoring the brand in words and emotions before colors and fonts.

### 0.1 Emotive Narrative

Before any visual work, write a 3-5 sentence **brand feeling** in plain language. No HEX codes, no font names — only sensory and emotional descriptions.

```
Template:
"When someone opens {App Name}, they should feel like _________.
The aesthetic is closer to _________ than _________.
If this brand were a physical space, it would be _________.
The vibe is _________, never _________."
```

**Ask the user these questions.** Fill from their answers + Discovery context.

### 0.2 Anti-Convergence Defaults

These are **banned starting points** — the LLM's comfort zone:

| Banned Default | Why | Instead |
|----------------|-----|---------|
| Inter, system-ui | Every AI picks these first | Start from archetype mood |
| Purple/blue gradient backgrounds | #1 AI-generated cliche | Derive from emotive narrative |
| Rounded white cards on gray | Default UI kit aesthetic | Match brand personality |
| Generic "modern minimalist" | Meaningless descriptor | Use specific sensory words |
| Stock photo style imagery | Dilutes brand uniqueness | Match archetype visual language |

**Rule:** If you catch yourself reaching for any of these — STOP and re-read the Emotive Narrative.

### 0.3 Three Aesthetic Directions

Generate 3 **distinct** aesthetic directions based on the Emotive Narrative. Each must be noticeably different — not 3 variations of the same idea.

| Direction | Mood Board Words | Color Temperature | Typography Feel | Reference World |
|-----------|-----------------|-------------------|-----------------|-----------------|
| A: Conservative | {5 words} | {warm/cool/neutral} | {serif/geometric/humanist} | {real-world reference} |
| B: Bold | {5 words} | {warm/cool/neutral} | {display/mono/contrast} | {real-world reference} |
| C: Experimental | {5 words} | {warm/cool/neutral} | {unexpected/mixed/custom} | {real-world reference} |

**Present all 3 to user. User PICKS ONE. Do not blend.**

"Reference World" = a real place, era, or medium (e.g., "1970s Japanese department store signage", "Scandinavian sauna interior", "90s rave flyer"). This anchors the LLM away from generic AI aesthetics.

### How to Present the Choice

1. Show the full comparison table above with all 5 columns filled
2. Add 1-2 sentence description per direction explaining the *feeling*
3. Use `AskUserQuestion` tool with 3 options:

```
AskUserQuestion:
  question: "Which aesthetic direction fits your brand?"
  header: "Direction"
  options:
    - label: "A: Conservative"
      description: "{mood words} — {reference world}"
    - label: "B: Bold"
      description: "{mood words} — {reference world}"
    - label: "C: Experimental"
      description: "{mood words} — {reference world}"
```

**After user picks:** Confirm choice, record in brand-dna.md, use as anchor for ALL subsequent phases.

---

## Phase 1: Discovery (Socratic Dialogue)

**Goal:** Extract brand DNA from founder's vision through 7 questions.

### If Context Files Exist

Check `biz/` for product briefs, personas, research docs.
Found? → Read them first, pre-fill answers, confirm with user.

### Questions

| # | Question | Purpose | Example |
|---|----------|---------|---------|
| 1 | App name + one-line description? | Core identity | "Ellevated — AI elevator pitch coach" |
| 2 | What problem does it solve? For whom? | Value prop | "Founders waste weeks on decks. We cut to 1 hour." |
| 3 | Target audience: age, occupation, tech level? | Visual direction | "25-40, tech founders, high literacy" |
| 4 | Name 3-5 competitor apps | Positioning | "Pitch.com, Slidebean, Beautiful.ai" |
| 5 | App vertical? | Color psychology | fintech / health / social / productivity / education / other |
| 6 | 3 adjectives your app should "feel like"? | Personality | "confident, sharp, premium" |
| 7 | Visual preferences or anti-preferences? | Constraints | "No gradients. Dark mode preferred." |

**After collecting:** Summarize understanding, confirm before proceeding.

---

## Phase 2: Brand DNA

### 2.1 Brand Archetype (Jung's 12)

Map app's purpose + audience to ONE primary archetype:

| Archetype | Fits When | Visual Direction | Voice |
|-----------|-----------|------------------|-------|
| Creator | Tools, creativity apps | Artistic, unique shapes | Inspiring, expressive |
| Sage | Education, analytics | Clean, data-driven | Authoritative, clear |
| Explorer | Travel, discovery | Open, adventurous | Bold, curious |
| Hero | Fitness, productivity | Bold, strong contrasts | Motivating, direct |
| Caregiver | Health, family | Soft, warm tones | Gentle, supportive |
| Magician | Finance, transformation | Gradient, premium | Visionary, confident |
| Ruler | Enterprise, luxury | Structured, minimal | Commanding, refined |
| Jester | Social, entertainment | Bright, playful | Witty, energetic |
| Lover | Beauty, lifestyle | Elegant, sensual | Passionate, intimate |
| Everyman | Utility, daily use | Friendly, accessible | Simple, relatable |
| Rebel | Disruption, alternative | Edgy, high contrast | Provocative, raw |
| Innocent | Wellness, simplicity | Light, airy, minimal | Honest, optimistic |

**Output:** Archetype name + one paragraph explaining WHY it fits this app.

### 2.2 Visual Descriptors

Generate 5-7 adjectives guiding ALL visual generation:

```
Format: "descriptor1, descriptor2, ..., descriptor7"
Example: "minimal, geometric, premium, calm, trustworthy, dark-themed, sharp"
```

These become the **style seed** reused in every AI prompt.

### 2.3 Brand Personality Spectrum

For each pair, mark position (1-5):

```
Formal  ----[---]---- Casual         → ?
Serious ---[----]---  Playful        → ?
Luxury  -[------]---  Accessible     → ?
Traditional --[---]-  Modern         → ?
Complex ----[---]---  Simple         → ?
```

---

## Phase 3: Voice Framework

### 3.1 Voice Definition

One sentence formula:
```
"We sound [adj], [adj], and [adj] — but never [adj]."
Example: "We sound confident, sharp, and approachable — but never condescending."
```

### 3.2 Vocabulary Rules

| Use | Don't Use | Why |
|-----|-----------|-----|
| {word} | {word} | {reason} |

Generate 5-7 pairs based on archetype + audience.

### 3.3 Tone by Context

| Context | Tone | Example Copy |
|---------|------|-------------|
| App Store description | Persuasive, benefit-focused | "Launch your pitch in 60 minutes, not 60 days." |
| Push notification | Concise, action-oriented | "Your pitch deck is ready. Review now." |
| Error message | Helpful, non-blaming | "We couldn't save your changes. Try again?" |
| Onboarding welcome | Warm, exciting | "Welcome! Let's build something great." |
| Social media post | Energetic, value-first | "3 pitch mistakes that kill funding rounds" |

### 3.4 Copywriting AI Prompt

Generate a reusable system prompt for LLM-based copywriting:

```
You are {App Name}'s brand voice.
Tone: {voice definition}.
Always use: {approved words}.
Never use: {forbidden words}.
Audience: {audience description}.
Archetype: {archetype}.
```

---

## Foundation Output

Write `brand-dna.md` containing:
0. Emotive narrative + chosen aesthetic direction (from Phase 0)
1. App overview (from Discovery)
2. Brand archetype + justification
3. Visual descriptors (style seed)
4. Personality spectrum
5. Voice framework (definition, vocabulary, tone examples)
6. Copywriting system prompt

**Then proceed to:** `design.md`
