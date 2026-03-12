# Tech: [TECH-080] Terminal Demo GIF

**Status:** draft | **Priority:** P2 | **Date:** 2026-02-02

## Why

README needs a demo GIF showing DLD workflow in action. A terminal GIF is the standard way to showcase CLI tools — it lets users see the experience before installing.

## Context

**Brand assets created in TECH-079:**
- `assets/style-guide.png` — Matrix aesthetic reference
- `assets/logo.png` — DLD logo with phosphor glow
- `assets/social-preview.png` — GitHub social preview

**Visual style:** Matrix (1999) — green on black, phosphor glow, monospace.

**Color palette:**
| Color | Hex | Usage |
|-------|-----|-------|
| Background | #000000 | Terminal bg |
| Primary | #00FF41 | Bright text, commands |
| Secondary | #008F11 | Dim text, comments |
| Glow | Bloom effect | Around bright elements |

---

## Scope

**In scope:**
- Terminal demo GIF showing `/spark` → `/autopilot` → shipped flow
- VHS script for reproducible generation
- Matrix-style terminal theme
- Optimization for README embed

**Out of scope:**
- Video format (GIF only)
- Sound
- Multiple demo variants

---

## Tool: VHS by Charmbracelet

**Why VHS:**
- Purpose-built for terminal GIFs
- Scriptable (`.tape` files) — reproducible
- Custom themes — can match Matrix colors exactly
- Beautiful output, compact files
- Used by major CLI tools (gh, charm, etc.)

**Installation:**
```bash
brew install charmbracelet/tap/vhs
```

**How it works:**
1. Write a `.tape` script defining terminal actions
2. Run `vhs script.tape`
3. Get `output.gif`

---

## Workflow

### Step 1: Install VHS

```bash
brew install charmbracelet/tap/vhs
```

### Step 2: Create Matrix Theme

Create `assets/demo/matrix-theme.json`:
```json
{
  "name": "Matrix",
  "black": "#000000",
  "red": "#008F11",
  "green": "#00FF41",
  "yellow": "#00FF41",
  "blue": "#008F11",
  "magenta": "#00FF41",
  "cyan": "#00FF41",
  "white": "#00FF41",
  "brightBlack": "#003B00",
  "brightRed": "#008F11",
  "brightGreen": "#00FF41",
  "brightYellow": "#00FF41",
  "brightBlue": "#008F11",
  "brightMagenta": "#00FF41",
  "brightCyan": "#00FF41",
  "brightWhite": "#00FF41",
  "background": "#000000",
  "foreground": "#00FF41",
  "selection": "#003B00",
  "cursor": "#00FF41"
}
```

### Step 3: Create VHS Script

Create `assets/demo/demo.tape`:
```tape
# DLD Demo — Matrix Style
Output assets/demo.gif

# Terminal settings
Set FontFamily "JetBrains Mono"
Set FontSize 16
Set Width 900
Set Height 500
Set Theme "matrix-theme.json"
Set Padding 20

# Animation settings
Set TypingSpeed 50ms
Set PlaybackSpeed 1

# --- Scene 1: Start claude ---
Type "claude"
Enter
Sleep 2s

# --- Scene 2: Spark a feature ---
Type "/spark add user authentication with OAuth"
Sleep 500ms
Enter
Sleep 3s

# Simulate spark output (abbreviated)
# Note: In real recording, this would be actual output

# --- Scene 3: Autopilot executes ---
Type "/autopilot"
Sleep 500ms
Enter
Sleep 4s

# --- Scene 4: Done ---
Sleep 2s
Type "# Feature shipped! 🚀"
Enter
Sleep 2s
```

### Step 4: Generate GIF

```bash
cd /Users/desperado/dev/dld
vhs assets/demo/demo.tape
```

### Step 5: Optimize

```bash
# Install gifsicle if needed
brew install gifsicle

# Optimize
gifsicle -O3 --lossy=80 assets/demo.gif -o assets/demo-optimized.gif
```

### Step 6: Embed in README

```markdown
![DLD Demo](assets/demo.gif)
```

---

## Alternative: Simulated Demo

If real Claude output is hard to capture, create a "simulated" demo:
1. Write a bash script that echoes fake output
2. Record that with VHS
3. Looks real, fully controlled

Example fake script `assets/demo/fake-session.sh`:
```bash
#!/bin/bash
# Simulated DLD session for demo

echo -e "\033[32m╭─ DLD v0.1.0 ─────────────────────────────────────╮\033[0m"
echo -e "\033[32m│ Turn Claude Code into an Autonomous Developer    │\033[0m"
echo -e "\033[32m╰──────────────────────────────────────────────────╯\033[0m"
echo ""
sleep 1

echo -e "\033[32m> /spark add OAuth authentication\033[0m"
sleep 2
echo -e "\033[90m[spark] Researching OAuth best practices...\033[0m"
sleep 1
echo -e "\033[90m[spark] Creating spec: ai/features/FEAT-042-oauth.md\033[0m"
sleep 1
echo -e "\033[32m✓ Spec ready. Run /autopilot to implement.\033[0m"
echo ""
sleep 2

echo -e "\033[32m> /autopilot\033[0m"
sleep 1
echo -e "\033[90m[planner] Breaking down into 5 tasks...\033[0m"
sleep 1
echo -e "\033[90m[coder] Implementing OAuth provider...\033[0m"
sleep 1
echo -e "\033[90m[tester] Running tests... 12/12 passed\033[0m"
sleep 1
echo -e "\033[90m[review] Code quality check passed\033[0m"
sleep 1
echo -e "\033[32m✓ Feature complete. Ready to commit.\033[0m"
```

Then in VHS:
```tape
Output assets/demo.gif
Set Theme "matrix-theme.json"
...
Type "bash assets/demo/fake-session.sh"
Enter
Sleep 15s
```

---

## Specifications

| Attribute | Value |
|-----------|-------|
| Format | GIF |
| Width | 900px (reasonable for README) |
| Height | 500px |
| Duration | 15-20 seconds |
| File size | < 2MB (ideally < 1MB) |
| Frame rate | 15-20 fps |
| Font | JetBrains Mono or similar monospace |
| Colors | Matrix palette from TECH-079 |

---

## Definition of Done

- [ ] VHS installed
- [ ] Matrix theme created
- [ ] Demo script written
- [ ] GIF generated
- [ ] GIF optimized (< 2MB)
- [ ] Embedded in README
- [ ] Looks professional and on-brand

---

## Notes for Next Session

**Context to remember:**
1. Brand style is Matrix (1999) — see `assets/style-guide.png`
2. Colors: #00FF41 (bright green), #008F11 (dim green), #000000 (black)
3. Use VHS by Charmbracelet for terminal GIF generation
4. Either real recording or simulated script approach works
5. Final GIF goes to `assets/demo.gif`

**Files to reference:**
- `assets/style-guide.png` — visual reference
- `assets/social-preview.png` — see the vibe
- This spec — workflow steps

**Commands:**
```bash
brew install charmbracelet/tap/vhs
brew install gifsicle
vhs assets/demo/demo.tape
gifsicle -O3 --lossy=80 assets/demo.gif -o assets/demo.gif
```
