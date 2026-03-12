# External Research — FTR-147 Multi-Project Orchestrator Phase 2: Architecture & Reliability

## Best Practices

### 1. Groq Whisper: Use whisper-large-v3 for Russian Accuracy, whisper-large-v3-turbo for Speed
**Source:** [Groq Speech to Text Docs](https://console.groq.com/docs/speech-to-text) + [whisper-large-v3 model card](https://console.groq.com/docs/model/whisper-large-v3)
**Summary:** Groq offers two production models. `whisper-large-v3` costs $0.111/hour, achieves 10.3% WER multilingual, supports translation, runs at 189x real-time. `whisper-large-v3-turbo` costs $0.04/hour, 12% WER, 216x real-time, transcription only (no translation). Endpoint is OpenAI-compatible: `POST https://api.groq.com/openai/v1/audio/transcriptions`. Max file size 100 MB. Supported formats: FLAC, MP3, M4A, MPEG, MPGA, OGG, WAV, WEBM.
**Why relevant:** Telegram voice messages arrive as `.ogg` — directly supported. For Russian + English mixed speech, `whisper-large-v3` is the safer choice (lower WER on multilingual). Rate limit on developer plan: 300 RPM / 200K ASH.

### 2. Claude Code Headless Mode: `claude -p` with `CLAUDE_CODE_OAUTH_TOKEN` for VPS
**Source:** [Automating Claude Code on Headless VPS (Gist)](https://gist.github.com/coenjacobs/d37adc34149d8c30034cd1f20a89cce9) + [Run Claude Code programmatically](https://code.claude.com/docs/en/headless)
**Summary:** On a VPS without a browser, generate a long-lived OAuth token locally with `claude setup-token` (requires Claude Pro/Max). Set `CLAUDE_CODE_OAUTH_TOKEN=<token>` and create `~/.claude.json` marking onboarding complete. Token is valid 1 year. For project context, pass `--cwd /path/to/project` — Claude Code reads CLAUDE.md from that directory. Critical known bug: OAuth token refresh race condition (GitHub issue #27933) when multiple concurrent `claude` processes share one `~/.claude/.credentials.json`. First process refreshes, second gets HTTP 404. Workaround: serialize refreshes or use API key instead of OAuth for non-interactive processes.
**Why relevant:** We run 2-3 concurrent autopilot processes. Race condition on token refresh is a real production risk. Must stagger process starts or add lock file around token refresh.

### 3. CLAUDE.md Three-Level Hierarchy for Multi-Project VDS
**Source:** [CLAUDE.md Ultimate Guide](https://allahabadi.dev/blogs/ai/claude-md-ultimate-guide/) + [The Definitive Guide to CLAUDE.md](https://potapov.dev/blog/claude-md-guide)
**Summary:** Claude Code reads three levels: `~/.claude/CLAUDE.md` (global, all projects), `CLAUDE.md` in project root (project-specific), `.claude/CLAUDE.local.md` (machine-specific overrides, not committed). Priority: LOCAL > PROJECT > USER. Rules in CLAUDE.md are context/conventions; hard enforcement belongs in `settings.json` (deny lists) and hooks (lifecycle enforcement). Putting "NEVER do X" in CLAUDE.md works until context grows long — hooks are the reliable enforcement layer.
**Why relevant:** Global VDS CLAUDE.md should contain: MCP server configs, push-only-to-develop rule (as hook, not CLAUDE.md text), common tooling, nighttime agent instructions. Project-level CLAUDE.md stays project-specific.

### 4. Agent QA Fix Loop: 3-Strike Same-Bug Detection to Prevent Infinite Loops
**Source:** [Next-Level Self-Healing: Building Agents That Fix Their Own Bugs](https://www.sethserver.com/ai/next-level-self-healing-building-agents-that-fix-their-own-bugs.html) + [The Agent Loop Problem](https://medium.com/@Modexa/the-agent-loop-problem-when-smart-wont-stop-ccbf8489180f)
**Summary:** Production closed-loop QA patterns: (1) Max iteration budget — hard cap on loop count (typically 3-5 rounds); (2) Same-bug fingerprinting — hash bug signatures, detect if same bug reappears after a fix attempt, escalate instead of retry; (3) Evidence-driven loop — each iteration must produce a test result diff proving progress; (4) Fallback to human escalation when budget exhausted. The loop pattern: run QA → collect findings → fix → verify → repeat. Stop conditions: all findings resolved OR max iterations OR same finding appears twice (stuck).
**Why relevant:** Our QA loop (autopilot → QA → fix spec → Spark → autopilot) needs explicit halt conditions. Without fingerprinting, the same bug can cycle forever. Budget: 3 outer loops max.

### 5. Claude Code Security: Multi-Stage Verification Pipeline for Audit Night Mode
**Source:** [Anthropic announcement: Making frontier cybersecurity capabilities available](https://www.anthropic.com/news/claude-code-security) + [Claude Code Security Architecture](https://bytevanguard.com/2026/02/22/claude-code-security-architecture-limitations/) + [Kingy AI deep dive](https://kingy.ai/ai/claude-code-security-2026-the-most-important-new-shift-in-appsec-workflows-what-it-is-how-it-works-who-its-for-and-how-to-use-it/)
**Summary:** Claude Code Security (launched Feb 20, 2026, research preview for Enterprise/Team) uses Opus 4.6 for semantic code analysis — not pattern matching. Pipeline: repository input → semantic analysis (data flows, component interactions) → vulnerability detection (logic flaws, access control) → severity + confidence rating → remediation patch suggestion → human review dashboard. Found 500+ high-severity vulnerabilities in production OSS undetected for decades. Key mechanism: multi-stage verification, each finding gets severity + confidence score before surfacing. The `/security-review` command is available more broadly via GitHub Action.
**Why relevant:** Our night audit mode should mirror this pipeline: scan → severity + confidence rating → individual finding per Telegram message → Approve/Reject. The "confidence rating" pattern is critical — surfaces only high-confidence findings to avoid alert fatigue. For 10-100K LOC projects, scanning entire repo in one pass is feasible with 200K context.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| groq (Python SDK) | latest | OpenAI-compatible API, 189x real-time, 300 RPM dev limit, .ogg support | Paid (but cheap: $0.111/hr), cloud dependency | Telegram voice → text | [GroqDocs](https://console.groq.com/docs/speech-to-text) |
| whisper-large-v3 | production | Best accuracy for Russian+EN mixed, translation support, 10.3% WER | Slower than turbo, $0.111/hr | Mixed Russian/English voice messages | [Groq model page](https://console.groq.com/docs/model/whisper-large-v3) |
| whisper-large-v3-turbo | production | 216x real-time, $0.04/hr, cheaper | No translation, 12% WER, transcription only | Pure Russian voice if cost matters | [Groq models list](https://console.groq.com/docs/models) |
| python-telegram-bot | v21.9+ | Mature, async, CallbackQueryHandler, context.user_data for state, arbitrary callback data | PTB multiselect requires manual state tracking (no built-in checkbox) | Telegram inline keyboards, Approve/Reject buttons | [PTB docs](https://docs.python-telegram-bot.org/en/v21.11.1/) |
| systemd | v254+ | Native exponential backoff via RestartSteps + RestartMaxDelaySec, battle-tested | Linux only, v254 required for exponential backoff | Service restart with backoff | [systemd backoff post](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/) |
| pueue | current (from Phase 1) | Already in stack, queue management | No built-in retry logic — must handle externally | Task queue for agents | (existing) |
| flock / lockfile | system | Prevents token refresh race condition, POSIX-standard | Adds startup latency | Serializing OAuth refresh | stdlib |

**Recommendation for Groq STT:** Use `whisper-large-v3` (not turbo) for Russian conversational mixed with English technical terms. The 2.77x price premium ($0.111 vs $0.04/hr) is negligible for voice-message volumes (typical Telegram voice: 15-60 sec → costs fractions of a cent). The 1.7% WER improvement matters for technical terms and proper nouns.

**Recommendation for PTB inline keyboards:** Use `context.user_data` dict to track multi-select state per chat. Edit the message on each tap to show checkmarks. Add a "Done" button to submit the selection. This is the standard PTB pattern.

---

## Production Patterns

### Pattern 1: Groq Whisper Pipeline for Telegram Voice Inbox
**Source:** [Groq Speech to Text Docs](https://console.groq.com/docs/speech-to-text) + [Batch transcribe gist](https://gist.github.com/sebington/c2e6c6ef7bb32fb8bcb1f2cd062b4bdc)
**Description:** Telegram delivers voice messages as `.ogg` (OGG Opus). Download via `bot.get_file()` + `file.download_to_memory()`. Pass to Groq: `client.audio.transcriptions.create(file=(filename, bytes), model="whisper-large-v3", language="ru", response_format="text")`. Setting `language="ru"` improves accuracy on Russian but still handles English technical terms. Latency: Groq processes 10 min audio in ~3.7 sec. For typical 30-60 sec voice messages, expect ~0.7-1.5 sec transcription time. Write result to `ai/inbox/{timestamp}-voice.md`.
**Real-world use:** Used by "Stream of Thought" (drafting emails from voice), "Brainy Read" (video analysis), openclaw-curated-skills free-groq-voice skill.
**Fits us:** Yes — OGG is natively supported, latency is acceptable, price is negligible, no GPU required on VDS.

### Pattern 2: Claude Code Headless VPS Auth with Long-Lived Token
**Source:** [Automating Claude Code on Headless VPS Gist](https://gist.github.com/coenjacobs/d37adc34149d8c30034cd1f20a89cce9) + [GitHub Issue #7100](https://github.com/anthropics/claude-code/issues/7100)
**Description:** Generate token once locally: `claude setup-token` → saves `sk-ant-oat01-...` (valid 1 year). On VDS: `export CLAUDE_CODE_OAUTH_TOKEN=<token>` + create `~/.claude.json` with `{"onboardingCompleted": true}`. Run per-project: `cd /projects/myapp && claude -p "..." --allowedTools "Read,Edit,Bash" --output-format json`. The `--cwd` flag overrides working directory, making Claude load the project's CLAUDE.md. Known race condition: refresh token is single-use; concurrent processes race on expiry. Mitigation: use `flock ~/.claude/.credentials.lock` wrapper around claude invocation or stagger starts by 60+ sec.
**Real-world use:** Standard pattern in CI/CD pipelines, VPS automation setups (GitHub Issue #7100, multiple community implementations).
**Fits us:** Yes — matches our pueue-based orchestrator. Must add flock wrapper to run-agent.sh to prevent token refresh collisions.

### Pattern 3: Cron-Triggered Night Agent with File-Based Findings Inbox
**Source:** [The Cron Agent Pattern](https://dev.to/askpatrick/the-cron-agent-pattern-how-to-run-ai-agents-on-a-schedule-without-them-going-off-the-rails-4gma) + [Seven Hosting Patterns for AI Agents](https://james-carr.org/posts/2026-03-01-agent-hosting-patterns/)
**Description:** Night agents follow the "Scheduled Agent (Cron)" hosting pattern. Key rules from production: (1) Reload identity/context on every run — no state accumulation between nights; (2) Write findings to files, not keep in agent memory; (3) Exit cleanly after each run — no persistent process; (4) Guard against scope creep with explicit stop conditions in prompt. Findings land in `ai/inbox/YYYYMMDD-{project}-{finding-id}.md`. Extensibility: each agent type (reviewer, security scanner, performance auditor) is a separate cron entry pointing to a different prompt/skill.
**Real-world use:** Used by OpenClaw-style architectures for 24/7 autonomous agents, blog writers, prospect finders.
**Fits us:** Yes — night reviewer runs as cron → pueue job (not using compute slots) → writes individual finding files → Telegram bot polls inbox and sends Approve/Reject messages.

### Pattern 4: systemd Exponential Backoff for Resilient Service Restarts
**Source:** [How systemd exponential restart delay works](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/) + [systemd/systemd PR #26902](https://github.com/systemd/systemd/pull/26902)
**Description:** systemd v254+ supports native exponential backoff via `RestartSteps` + `RestartMaxDelaySec`. Config pattern:
```ini
[Service]
Restart=on-failure
RestartSec=1s
RestartMaxDelaySec=60s
RestartSteps=5
StartLimitBurst=10
StartLimitIntervalSec=300s
```
This gives: 1s → 2.1s → 4.6s → 10s → 21s → 60s backoff. After 10 failures in 300s window, service enters failed state requiring manual `systemctl reset-failed`. For pueue-callback.sh and telegram-bot.py services, this is the right pattern.
**Real-world use:** Standard in any production systemd deployment. Merged to systemd mainline.
**Fits us:** Yes — replace flat `RestartSec=5` in current service files with exponential backoff config.

### Pattern 5: Multi-Select Inline Keyboard via State Editing in PTB
**Source:** [Enhancing User Engagement with Multiselection Inline Keyboards](https://medium.com/@moraneus/enhancing-user-engagement-with-multiselection-inline-keyboards-in-telegram-bots-7cea9a371b8d) + [PTB context.user_data pattern](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-requested-design-patterns)
**Description:** Telegram Bot API has no native multi-select widget. Production pattern: (1) Store selections in `context.user_data["selected_projects"] = set()`; (2) On each button tap, toggle the project in the set; (3) Immediately `query.edit_message_reply_markup()` to redraw keyboard showing checkmarks on selected items; (4) "Confirm" button submits the set. Duplicate callback guard: track `last_cbq` in `user_data` to prevent double-processing during async delays (BadRequest from editing same message twice). Key: always `await query.answer()` before any async work.
**Real-world use:** Standard pattern for survey bots, booking systems, preference UIs.
**Fits us:** Yes — evening project selection for review uses this exact pattern. 10 projects fit in one keyboard (2 columns × 5 rows + 1 confirm row).

### Pattern 6: QA Fix Loop with Bug Fingerprinting
**Source:** [Agentic Full-Stack Development: Build the Feedback Loop](https://www.james-ralph.com/posts/2026-02-15-agentic-development-feedback.html) + [LLM-based Agents for Automated Bug Fixing (ICSE 2026)](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/227/LLM-based-Agents-for-Automated-Bug-Fixing-How-Far-Are-We-)
**Description:** Production QA loop pattern: `while iterations < MAX_ITERATIONS: run_qa() → if no_findings: break → hash_findings() → if findings_hash == prev_hash: escalate_to_human(); break → create_fix_spec() → run_autopilot() → prev_hash = findings_hash`. Fingerprinting uses content hash of finding descriptions (not line numbers — those shift after fixes). ICSE 2026 research: SWE-bench shows LLM agents solve ~40-50% of bugs autonomously on first pass; iterative validation improves this. Key: the loop must produce a test result diff proving progress on each iteration, not just "I tried to fix it."
**Real-world use:** SWE-bench benchmarked systems (SWE-agent, Devin, Agentless), OpenClaw self-healing pattern.
**Fits us:** Yes — outer loop max 3 iterations. Bug fingerprint = SHA256 of sorted finding titles. Escalate to Telegram message if same bug appears after 2 fix attempts.

---

## Key Decisions Supported by Research

1. **Decision:** Use `whisper-large-v3` (not turbo) for voice inbox
   **Evidence:** [Groq STT docs](https://console.groq.com/docs/speech-to-text) — turbo lacks translation, has higher WER (12% vs 10.3%), and Russian+English technical terms require the full model. Cost difference is ~$0.07/hr extra, negligible for our volume.
   **Confidence:** High

2. **Decision:** Night reviewer runs as separate cron/pueue job, NOT using compute slots
   **Evidence:** [Seven Hosting Patterns for AI Agents](https://james-carr.org/posts/2026-03-01-agent-hosting-patterns/) — scheduled agents are stateless, exit after each run, don't compete with interactive slots. Matches Socratic insight: "Reviewer runs as separate process, not using compute slots."
   **Confidence:** High

3. **Decision:** Serialize OAuth token refresh with `flock` in `run-agent.sh`
   **Evidence:** [GitHub Issue #27933](https://github.com/anthropics/claude-code/issues/27933) — confirmed race condition on concurrent OAuth refresh, closed as duplicate (known issue, no ETA for fix). `flock` is the standard POSIX workaround.
   **Confidence:** High

4. **Decision:** Individual findings per Telegram message (not one big report) for audit night mode
   **Evidence:** [Claude Code Security architecture](https://bytevanguard.com/2026/02/22/claude-code-security-architecture-limitations/) — Anthropic's own security scanner surfaces findings individually with severity + confidence. Alert fatigue is real; individual messages with Approve/Reject let human triage without reading a wall of text.
   **Confidence:** High

5. **Decision:** QA fix loop max 3 outer iterations + bug fingerprinting for stuck detection
   **Evidence:** [ICSE 2026 LLM bug fixing research](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/227/LLM-based-Agents-for-Automated-Bug-Fixing-How-Far-Are-We-) + [Agent Loop Problem](https://medium.com/@Modexa/the-agent-loop-problem-when-smart-wont-stop-ccbf8489180f) — most LLM agents solve bugs in 1-2 iterations or not at all. Beyond 3 loops with same hash = infinite loop, not progress.
   **Confidence:** High

6. **Decision:** Global VDS `~/.claude/CLAUDE.md` for cross-project rules; project CLAUDE.md for project-specific context
   **Evidence:** [CLAUDE.md three-level hierarchy](https://allahabadi.dev/blogs/ai/claude-md-ultimate-guide/) — user-level CLAUDE.md is loaded for every project. Hard enforcement (push to develop only) goes in hooks, not CLAUDE.md text.
   **Confidence:** High

7. **Decision:** systemd exponential backoff (v254+) for telegram-bot and callback services
   **Evidence:** [systemd exponential restart](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/) — native feature in systemd v254+, no external tooling. Pattern tested at Debian/Ubuntu/RHEL scale.
   **Confidence:** High (pending VDS systemd version check)

---

## Component-Specific Technical Notes

### Component 1: Groq Voice Inbox

**API endpoint:**
```
POST https://api.groq.com/openai/v1/audio/transcriptions
Authorization: Bearer {GROQ_API_KEY}
Content-Type: multipart/form-data

file: <ogg bytes>
model: whisper-large-v3
language: ru
response_format: text
```

**Rate limits (developer plan):**
- 300 RPM
- 200K ASH (Audio Seconds per Hour)
- For our volumes (< 100 voice messages/day), never a concern

**Error handling pattern:**
- Retry on 429 (rate limit) with exponential backoff
- Retry on 503 (service unavailable) up to 3 times
- On 400 (bad file): log + discard (malformed audio from Telegram)
- Write to `ai/inbox/{YYYYMMDD-HHMMSS}-voice.md`

**Source:** [Groq docs](https://console.groq.com/docs/speech-to-text), [Groq 100MB announcement](https://groq.com/blog/largest-most-capable-asr-model-now-faster-on-groqcloud)

---

### Component 2: Claude Code Security — Adoptable Patterns for Audit Night Mode

Claude Code Security (Enterprise preview) is not available to us directly. However, its architecture patterns are public and adoptable:

1. **Data flow tracing** — scan across files, not file-by-file. Pass entire codebase context (200K window handles 50-100K LOC).
2. **Severity + confidence rating** — each finding gets `HIGH/MED/LOW` severity and `HIGH/MED/LOW` confidence. Only surface `confidence >= MED` to avoid alert fatigue.
3. **Self-debate on false positives** — prompt pattern: "Here is a potential vulnerability. Argue for and against it being a real issue. Conclude with your confidence rating." (multi-stage verification)
4. **Individual findings, not reports** — one finding per output unit, each with: title, file:line, description, remediation suggestion.
5. **The `/security-review` GitHub Action** is available broadly (not Enterprise-only) — usable in CI but not applicable to our VDS batch pattern.

**Source:** [Anthropic announcement](https://www.anthropic.com/news/claude-code-security), [VentureBeat analysis](https://venturebeat.com/security/anthropic-claude-code-security-reasoning-vulnerability-hunting), [Kingy AI deep dive](https://kingy.ai/ai/claude-code-security-2026-the-most-important-new-shift-in-appsec-workflows-what-it-is-how-it-works-who-its-for-and-how-to-use-it/)

---

### Component 3: Claude CLI Context Switching

**Confirmed behavior from docs + community:**
- `claude -p "prompt" --cwd /path/to/project` — sets working directory, reads that project's CLAUDE.md
- `~/.claude/CLAUDE.md` is always loaded (global rules apply)
- Project CLAUDE.md is read from `--cwd` directory
- `CLAUDE_CODE_OAUTH_TOKEN` env var bypasses interactive OAuth entirely
- `--output-format json` for structured output (use `stream-json` for streaming)
- `--allowedTools "Read,Edit,Bash(git:*)"` for tool permissions without prompting
- `--max-turns 30` to limit agent loop iterations

**Multiple concurrent processes:** Race condition on OAuth refresh (Issue #27933). Mitigation options:
1. `flock /tmp/claude-oauth.lock claude -p ...` — serializes token refresh, adds ~0ms overhead when no contention
2. Use `ANTHROPIC_API_KEY` instead of OAuth for non-interactive VDS agents (bypasses OAuth entirely, but requires API billing)
3. Stagger launch times by 60+ seconds between processes (crude but effective for our 2-3 concurrent limit)

**Source:** [Run Claude Code programmatically](https://code.claude.com/docs/en/headless), [Headless VPS Gist](https://gist.github.com/coenjacobs/d37adc34149d8c30034cd1f20a89cce9), [GitHub Issue #27933](https://github.com/anthropics/claude-code/issues/27933)

---

### Component 4: Global CLAUDE.md for VDS (Multi-Project)

**What goes in `~/.claude/CLAUDE.md` (global VDS):**
```markdown
## VDS Global Rules

### Git Policy
- Push only to `develop` branch. Never push to `main` directly.
- Commits: Conventional Commits format.

### MCP Servers (available to all projects)
- Context7: npx @context7/mcp-server
- Exa: https://mcp.exa.ai/mcp

### Orchestrator Awareness
- This VDS runs up to 3 concurrent autopilot sessions.
- Night agents (reviewer, auditor) run independently — do not interfere.
- Max session length: 30 turns.

### Quality Rules
- Never mock in integration tests.
- Tests must pass before committing.
```

**What stays in project CLAUDE.md:** Project-specific stack, domains, backlog format, skills.

**What goes in hooks (not CLAUDE.md text):**
- Push-to-develop enforcement: PreToolUse hook checking `git push` commands
- Mock ban in tests: PostToolUse hook on file writes to `tests/integration/`

**Source:** [CLAUDE.md Ultimate Guide](https://allahabadi.dev/blogs/ai/claude-md-ultimate-guide/), [Definitive CLAUDE.md Guide](https://potapov.dev/blog/claude-md-guide), [CLAUDE.md Best Practices 2026](https://uxplanet.org/claude-md-best-practices-1ef4f861ce7c)

---

### Component 5: Resilience Patterns

**systemd service template for exponential backoff (requires systemd v254+):**
```ini
[Service]
Type=simple
Restart=on-failure
RestartSec=1s
RestartMaxDelaySec=60s
RestartSteps=5
StartLimitBurst=10
StartLimitIntervalSec=300s
```
**Check VDS systemd version:** `systemctl --version`. Ubuntu 24.04 ships systemd v255 (supported). Ubuntu 22.04 ships systemd v249 (NOT supported — use flat RestartSec + wrapper script).

**Stale process detection pattern (bash):**
```bash
PIDFILE=/var/run/night-reviewer.pid
if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE")
  if ! kill -0 "$OLD_PID" 2>/dev/null; then
    rm -f "$PIDFILE"  # stale PID, clean up
  else
    echo "Reviewer already running (PID $OLD_PID), exiting."
    exit 0
  fi
fi
echo $$ > "$PIDFILE"
trap "rm -f $PIDFILE" EXIT
```

**Source:** [systemd exponential restart](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/), [systemd PR #26902](https://github.com/systemd/systemd/pull/26902), [ZeonEdge systemd guide](https://zeonedge.com/en/blog/systemd-service-keeps-restarting-fix)

---

### Component 6: Evening Review Telegram UX (PTB v21 Multi-Select)

**Pattern for project multi-select:**
```python
# State stored in context.user_data
SELECTED = "selected_projects"

async def show_project_selector(update, context):
    projects = get_all_projects()  # from db.py
    selected = context.user_data.get(SELECTED, set())

    keyboard = []
    for i in range(0, len(projects), 2):
        row = []
        for proj in projects[i:i+2]:
            label = f"[x] {proj.name}" if proj.id in selected else proj.name
            row.append(InlineKeyboardButton(label, callback_data=f"toggle:{proj.id}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("Start Review", callback_data="confirm")])

    await update.message.reply_text(
        "Select projects for tonight's review:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_selection(update, context):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("toggle:"):
        project_id = int(query.data.split(":")[1])
        selected = context.user_data.setdefault(SELECTED, set())
        if project_id in selected:
            selected.discard(project_id)
        else:
            selected.add(project_id)
        # Redraw keyboard with updated checkmarks
        await show_project_selector_edit(query, context)

    elif query.data == "confirm":
        selected = context.user_data.get(SELECTED, set())
        # Trigger night review for selected projects
        await launch_night_reviewer(selected)
        await query.edit_message_text(f"Review queued for {len(selected)} projects.")
        context.user_data.pop(SELECTED, None)
```

**Source:** [PTB docs v21.11.1](https://docs.python-telegram-bot.org/en/v21.11.1/), [Multiselection inline keyboards](https://medium.com/@moraneus/enhancing-user-engagement-with-multiselection-inline-keyboards-in-telegram-bots-7cea9a371b8d), [PTB design patterns](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-requested-design-patterns)

---

## Research Sources

1. [Groq Speech to Text Documentation](https://console.groq.com/docs/speech-to-text) — endpoint format, model comparison, rate limits, supported formats
2. [whisper-large-v3 model card](https://console.groq.com/docs/model/whisper-large-v3) — $0.111/hr, 10.3% WER, 100MB limit, 189x real-time
3. [Groq 100MB announcement](https://groq.com/blog/largest-most-capable-asr-model-now-faster-on-groqcloud) — performance benchmarks
4. [Anthropic Claude Code Security announcement](https://www.anthropic.com/news/claude-code-security) — pipeline architecture, 500+ vulns found
5. [Claude Code Security Architecture & Limitations](https://bytevanguard.com/2026/02/22/claude-code-security-architecture-limitations/) — 5-stage pipeline, severity + confidence rating
6. [VentureBeat: Claude Code Security finds 500+ vulnerabilities](https://venturebeat.com/security/anthropic-claude-code-security-reasoning-vulnerability-hunting) — production context, enterprise impact
7. [Run Claude Code programmatically (official docs)](https://code.claude.com/docs/en/headless) — `-p` flag, `--cwd`, `--allowedTools`, `--output-format`
8. [Automating Claude Code on Headless VPS (Gist)](https://gist.github.com/coenjacobs/d37adc34149d8c30034cd1f20a89cce9) — `claude setup-token`, `CLAUDE_CODE_OAUTH_TOKEN`, `~/.claude.json`
9. [GitHub Issue #27933 — OAuth token refresh race condition](https://github.com/anthropics/claude-code/issues/27933) — confirmed bug, multiple concurrent processes, single-use refresh token
10. [CLAUDE.md Ultimate Guide](https://allahabadi.dev/blogs/ai/claude-md-ultimate-guide/) — three-level hierarchy (user/project/local), priority order
11. [The Definitive Guide to CLAUDE.md](https://potapov.dev/blog/claude-md-guide) — five-layer config system, what belongs where
12. [The Cron Agent Pattern](https://dev.to/askpatrick/the-cron-agent-pattern-how-to-run-ai-agents-on-a-schedule-without-them-going-off-the-rails-4gma) — scheduled agent rules: reload identity, file-based output, clean exit
13. [Seven Hosting Patterns for AI Agents](https://james-carr.org/posts/2026-03-01-agent-hosting-patterns/) — Scheduled Agent (Cron) pattern, trade-offs
14. [The Agent Loop Problem](https://medium.com/@Modexa/the-agent-loop-problem-when-smart-wont-stop-ccbf8489180f) — infinite loop patterns, budget + state machine guardrails
15. [ICSE 2026 LLM-based Agents for Automated Bug Fixing](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/227/LLM-based-Agents-for-Automated-Bug-Fixing-How-Far-Are-We-) — iterative validation benchmark on SWE-bench
16. [Agentic Development Feedback Loop](https://www.james-ralph.com/posts/2026-02-15-agentic-development-feedback.html) — evidence-driven loop, pass condition per iteration
17. [How systemd exponential restart delay works](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/) — RestartSteps, RestartMaxDelaySec (v254+)
18. [systemd PR #26902](https://github.com/systemd/systemd/pull/26902) — merge confirmation, formula
19. [Enhancing User Engagement with Multiselection Inline Keyboards](https://medium.com/@moraneus/enhancing-user-engagement-with-multiselection-inline-keyboards-in-telegram-bots-7cea9a371b8d) — multi-select pattern implementation
20. [PTB InlineKeyboardButton docs v21.11.1](https://docs.python-telegram-bot.org/en/v21.11.1/telegram.inlinekeyboardbutton.html) — API reference
21. [PTB Frequently Requested Design Patterns](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-requested-design-patterns) — callback state tracking, duplicate prevention
