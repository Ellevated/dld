# Pattern Research — FTR-147 Multi-Project Orchestrator Phase 2

---

## Pattern 1: Night Reviewer Architecture

---

### Approach 1A: Extend Existing Audit Deep + Post-Processor

**Source:** [dshills/prism — Local-first AI code review CLI](https://github.com/dshills/prism)

#### Description
Reuse the existing `audit deep` skill. After completion, a post-processor script parses the monolithic report and splits it into individual finding objects (severity, file, line, description, fix suggestion). Each finding is stored in SQLite and dispatched to Telegram as a separate message.

#### Pros
- Zero new agent infrastructure — audit deep already exists and works
- Post-processor is deterministic (no LLM in splitting step)
- Leverages existing CLAUDE.md / skill chain we've already validated

#### Cons
- Audit deep produces prose, not structured JSON — regex/LLM parse adds fragility
- Monolithic single LLM pass = large context, may miss detail in 100K LOC codebases
- Splitting step can merge multi-file findings incorrectly (loses file:line precision)

#### Complexity
**Estimate:** Medium — 6-8 hours
**Why:** Audit skill exists, post-processor is new Python, SQLite schema extension, Telegram dispatch loop. Risky part is reliable finding extraction from prose output.

#### Example Source
Prism's `--output-format json` demonstrates structured per-finding output from a diff-centric LLM review:
```
{findings: [{severity: "critical", file: "auth.py", line: 47,
  description: "SQL injection via f-string", fix: "Use parameterized query"}]}
```

---

### Approach 1B: New Specialized "Night Critic" Agent with Structured Output

**Source:** [Multi-Model AI Code Review: Convergence Loops](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence)

#### Description
A dedicated `night-critic` agent built from scratch. System prompt instructs Claude to output **only** a JSON array of finding objects. The agent receives file chunks (not the entire repo at once), processes them in parallel background subagents (ADR-008), and a collector merges findings. Runs outside compute slots (separate systemd service).

#### Pros
- Structured JSON output guaranteed from the start — no post-parse step
- Parallel per-file/per-domain subagents = scales to 100K LOC without single context overflow
- Separate process = doesn't consume autopilot compute slots
- Finding count naturally decreases over weeks (25 → 15 → 5) as code improves

#### Cons
- New agent to build and maintain
- JSON-only constraint can cause Claude to miss cross-cutting findings that span multiple files
- Multi-model research shows 3-8 convergence rounds needed for zero false positives — single pass may generate noise

#### Complexity
**Estimate:** Medium-Hard — 10-14 hours
**Why:** New agent prompt, chunking strategy for large codebases, parallel background fan-out (ADR-008 pattern), collector subagent, SQLite persistence, Telegram dispatch. Well-understood patterns but many moving parts.

#### Example Source
Multi-model convergence research (Zylos, Mar 2026): "Separate models for generation and review, running in iterative loops that converge toward zero defects. Typical convergence: 3-8 rounds." Industry tools: CodeRabbit, BugBot, Qodo all use structured per-finding JSON with file/line/severity.

---

### Approach 1C: Chain — Audit Deep → LLM Parser → Individual Findings → Formatter

**Source:** [llimllib/pr-review — multi-specialist agents synthesized into one report](https://github.com/llimllib/pr-review)

#### Description
Three-step pipeline: (1) existing audit deep runs and produces prose, (2) a second LLM pass ("the extractor") converts prose to structured JSON findings, (3) a formatter dispatches each finding to Telegram. The extractor prompt is specifically tuned to parse audit output format.

#### Pros
- Preserves audit deep's quality (it's battle-tested in DLD)
- Extractor is a cheap, focused LLM call (Haiku/Sonnet)
- Separation of concerns: reviewer ≠ formatter

#### Cons
- Two LLM passes = 2x cost per run
- If audit prose changes format, extractor breaks silently
- Cross-file findings are still lost when split into individual messages

#### Complexity
**Estimate:** Medium — 8-10 hours
**Why:** Audit deep exists, extractor is a new focused prompt (~1h), Telegram dispatch is shared with approach 1B. Integration + testing is the bulk.

---

### Comparison Matrix — Night Reviewer

| Criteria | 1A: Extend Audit | 1B: Night Critic Agent | 1C: Audit + Extractor |
|----------|-----------------|----------------------|----------------------|
| Complexity | Medium | Medium-Hard | Medium |
| Reliability | Low (parse fragility) | High | Medium |
| Finding Quality | Medium | High | Medium |
| Scalability (100K LOC) | Low | High | Low |
| Dependencies | None | None | None |
| Reuses existing work | High | Low | High |
| Separate from compute slots | Easy | Easy | Easy |

---

### Recommendation — Night Reviewer

**Selected:** Approach 1B (Night Critic Agent with Structured Output)

**Rationale:** The core goal is reliable, actionable findings over time (25 → 15 → 5 trend). Approach 1A and 1C both rely on parsing prose — that's a fragile dependency that will break silently as audit output evolves. A dedicated agent that outputs structured JSON from the first token is the only approach that gives consistent file:line precision.

The ADR-008/ADR-009 background fan-out pattern already solves the context overflow problem for large codebases. Night Critic runs as a separate systemd process — no compute slot contention with autopilot.

**Trade-off accepted:** ~4 more hours to build vs 1C. Given that this runs every night for months, reliability > speed of initial build.

---

---

## Pattern 2: Groq Whisper Integration

---

### Approach 2A: Groq Whisper API (Cloud)

**Source:** [Groq Speech-to-Text Docs](https://console.groq.com/docs/speech-text) | [Batch transcription example](https://gist.github.com/sebington/c2e6c6ef7bb32fb8bcb1f2cd062b4bdc)

#### Description
Download Telegram voice message (.ogg), send directly to `https://api.groq.com/openai/v1/audio/transcriptions`. Groq natively accepts `.ogg`, `.mp3`, `.wav`, `.webm`. Use `whisper-large-v3` for Russian+English mix (multilingual). Response in <2s for typical voice messages.

#### Pros
- Groq accepts `.ogg` directly — no format conversion needed for Telegram voice
- `whisper-large-v3` supports Russian natively; ISO-639-1 `language` param speeds up detection
- 2-5s end-to-end latency (Groq runs Whisper at 189x realtime speed factor)
- Free tier: 2 hours audio/day; paid: $0.111/hour — negligible for bot usage
- Zero infrastructure — just one API call

#### Cons
- Rate limit: 20 req/min free tier; can hit if many voice messages simultaneously
- Audio data leaves server (privacy consideration for sensitive voice commands)
- Max 25MB per file (Telegram voice messages are typically <1MB — not an issue)
- API key dependency — if Groq is down, bot voice is down

#### Complexity
**Estimate:** Easy — 2-3 hours
**Why:** One `groq.audio.transcriptions.create()` call, Telegram file download, error handling. Well-documented API.

#### Example Source
```python
from groq import Groq
client = Groq(api_key=GROQ_API_KEY)

async def transcribe_voice(file_path: str, language: str = None) -> str:
    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(Path(file_path).name, f.read()),
            model="whisper-large-v3",
            language=language,  # None = auto-detect Russian/English
            response_format="text",
        )
    return result
```

---

### Approach 2B: OpenAI Whisper API (Cloud)

**Source:** [OpenAI Audio Transcriptions API](https://platform.openai.com/docs/guides/speech-to-text)

#### Description
Same pattern as Approach 2A but using OpenAI's Whisper endpoint. Uses `openai` Python SDK, same file formats, similar API surface.

#### Pros
- Same `whisper-large-v3` model as Groq (same quality)
- OpenAI has higher rate limits on paid tiers
- Better SLA/uptime than Groq (more mature service)

#### Cons
- Cost: $0.006/minute vs Groq's ~$0.002/minute — 3x more expensive
- Latency: ~5-15s vs Groq's 2-5s (no specialized hardware acceleration)
- Adds `openai` SDK dependency if not already present

#### Complexity
**Estimate:** Easy — 2-3 hours
**Why:** Identical pattern to Approach 2A, different SDK.

#### Example Source
```python
from openai import OpenAI
client = OpenAI()
result = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("voice.ogg", "rb"),
    language="ru"
)
```

---

### Approach 2C: Local whisper.cpp on CPU

**Source:** [Local vs Cloud Transcription comparison](https://openwhispr.com/blog/local-vs-cloud-transcription) | [Russian STT CPU benchmark](https://habr.com/ru/articles/1002260/)

#### Description
Run `whisper.cpp` locally on VDS CPU. Download `ggml-large-v3.bin` model (~1.5GB), serve via HTTP or subprocess call. No external API dependency. Russian accuracy: whisper-large-v3 achieves ~3-5% WER on Russian (Habr benchmark, Feb 2026).

#### Pros
- Zero API cost after setup
- No data leaves VDS — full privacy
- No rate limits, no external dependency
- Works offline

#### Cons
- CPU inference: ~15-60s for a 30s voice message (VDS with 2-4 cores)
- Requires 1.5GB RAM for large model (or use medium: 750MB, lower accuracy)
- Setup complexity: compile whisper.cpp, download model, manage subprocess
- Haiku benchmark (Habr 2026): CPU whisper-large on Russian = 3.3% WER but 10-15s latency for short clips

#### Complexity
**Estimate:** Hard — 8-12 hours
**Why:** Compile whisper.cpp, model download, subprocess wrapper, error handling, performance tuning. Latency likely unacceptable for real-time bot UX.

#### Example Source
```bash
# whisper.cpp subprocess approach
./whisper -m models/ggml-large-v3.bin -f voice.ogg -l ru --output-txt
```

---

### Comparison Matrix — Whisper Integration

| Criteria | 2A: Groq API | 2B: OpenAI API | 2C: Local whisper.cpp |
|----------|-------------|---------------|----------------------|
| Complexity | Low | Low | High |
| Latency | 2-5s | 5-15s | 15-60s |
| Cost/hour audio | ~$0.002 | ~$0.006 | $0 |
| Russian accuracy | High | High | High (but slow) |
| Rate limits | 20 req/min (free) | Higher paid | None |
| Dependencies | Groq API | OpenAI API | whisper.cpp binary |
| Privacy | Low | Low | High |
| Setup time | 2h | 2h | 10h |

---

### Recommendation — Whisper Integration

**Selected:** Approach 2A (Groq Whisper API)

**Rationale:** For a Telegram orchestrator bot used by one person (10 projects), voice messages are infrequent and short. Groq's 2-5s latency is acceptable for real-time UX; local CPU would make the bot feel broken. The free tier (2h audio/day) covers typical usage. If rate limits become an issue, upgrade to paid ($0.002/hour is negligible).

**Trade-off accepted:** Audio data leaves VDS. For an orchestrator bot (dev commands, not sensitive personal data), this is acceptable.

---

---

## Pattern 3: QA Fix Loop (Closed Cycle)

---

### Approach 3A: QA Writes to Inbox → Spark Processes → Autopilot Fixes → QA Retests

**Source:** [When working with agent, close the loop](https://szykonkrajewski.pl/when-working-with-agent-close-the-loop/) | [Self-healing AI agents patterns](https://dev.to/techfind777/building-self-healing-ai-agents-7-error-handling-patterns-that-keep-your-agent-running-at-3-am-5h81)

#### Description
QA agent discovers bugs → writes structured bug reports to `qa-inbox/` folder → Spark processes each report through full spec pipeline → Autopilot implements fix → QA reruns the original test scenario. Loop continues until all bugs resolved or max iterations reached. Loop guard: hash-based deduplication (same bug hash = skip), max 3 iterations per bug.

#### Pros
- Full spec pipeline per bug = highest quality fixes (follows existing DLD discipline)
- Deduplication by content hash prevents infinite loops
- Parallelizable: multiple bugs processed simultaneously
- Aligns with existing autopilot/spark infrastructure

#### Cons
- Full Spark pipeline per bug is expensive for simple/trivial bugs
- Slower cycle time: Spark spec → Autopilot → QA retest = 15-30 minutes per bug
- Complex orchestration: QA → Spark → Autopilot → QA requires careful state tracking

#### Complexity
**Estimate:** Hard — 12-16 hours
**Why:** New QA subagent, inbox watcher, loop state in SQLite, hash deduplication, max-iteration guard, QA retest trigger. Many integration points.

#### Example Source
Loop guard pattern (gantz.ai, Jan 2026):
```python
# Failure memory pattern
bug_attempts = {}
def try_fix(bug: Bug):
    key = hash(bug.file + bug.description)
    if bug_attempts.get(key, 0) >= MAX_ATTEMPTS:
        escalate_to_human(bug)
        return
    bug_attempts[key] = bug_attempts.get(key, 0) + 1
    launch_fix_pipeline(bug)
```

---

### Approach 3B: QA Directly Creates Fix Specs (Bypass Spark for Simple Bugs)

**Source:** [A Dual-Loop Agent Framework for Automated Vulnerability Reproduction](https://arxiv.org/html/2602.05721v1) | [Ralph Wiggum Loop — autonomous iteration](https://agentfactory.panaversity.org/docs/General-Agents-Foundations/general-agents/ralph-wiggum-loop)

#### Description
QA classifies each bug by complexity: `trivial` (1-5 LOC fix) vs `complex`. Trivial bugs → QA writes a minimal fix spec directly (bypassing Spark) → Autopilot implements immediately. Complex bugs → full Spark pipeline. Two-speed system: fast lane for simple regressions, slow lane for architectural bugs.

#### Pros
- Fast cycle for trivial bugs (typos, missing null checks, off-by-one): 3-5 min
- Mirrors the DLD "Hotfix < 5 LOC" fast path
- Lower cost per trivial bug (skips expensive Spark research phase)

#### Cons
- QA must reliably classify trivial vs complex — LLM classification errors can bypass Spark for bugs that need it
- Two code paths to maintain
- "Simple" bugs that generate bad fixes can loop faster (quicker cycle = more iterations before human notices)

#### Complexity
**Estimate:** Medium — 8-10 hours
**Why:** Classifier prompt, two spec templates, routing logic, same loop guard as 3A. Classification is the risky part.

#### Example Source
Dual-loop architecture (arXiv 2602.05721): "plan-execute-evaluate pattern separates exploration (complex) from implementation fixes (trivial), preventing unproductive debugging loops."

---

### Approach 3C: QA Creates Batch Fix Spec (All Bugs in One)

**Source:** [Multi-Model Convergence Loops](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence)

#### Description
After a QA run, all bugs are collected into a single batch spec. One Spark run, one Autopilot run, one QA retest cycle. Simple and sequential.

#### Pros
- Simplest orchestration — one spec per QA run
- No parallel coordination complexity
- Easiest to debug when something goes wrong

#### Cons
- One large spec = high risk that Autopilot partially fails and partially succeeds — hard to retry selectively
- QA retest must rerun all scenarios even if only one bug was fixed
- Cannot process bugs in parallel

#### Complexity
**Estimate:** Easy-Medium — 4-6 hours
**Why:** Least orchestration complexity. Risk is in partial-failure handling.

#### Example Source
Convergence loop research: "Single-model review in one pass leads to cross-contamination of findings. Isolated per-finding processing converges faster."

---

### Comparison Matrix — QA Fix Loop

| Criteria | 3A: Full Pipeline | 3B: Two-Speed | 3C: Batch Spec |
|----------|------------------|--------------|---------------|
| Complexity | High | Medium | Low |
| Fix Quality | Highest | High | Medium |
| Cycle Time | Slow (15-30m) | Fast+Slow | Medium |
| Loop Safety | Hash dedup + max iter | Hash dedup + max iter | Simpler (1 loop) |
| Parallelism | High | High | None |
| Partial failure recovery | Easy (per-bug) | Easy (per-bug) | Hard |
| Infrastructure reuse | High | High | High |

---

### Recommendation — QA Fix Loop

**Selected:** Approach 3B (Two-Speed: classify trivial vs complex)

**Rationale:** Most bugs found in QA are trivial regressions (wrong text, missing validation, off-by-one). Sending all of them through full Spark is expensive and slow. The two-speed pattern mirrors DLD's own hotfix rule ("< 5 LOC → fix directly"). The classification risk is managed: QA is conservative — when in doubt, route to full Spark pipeline.

Key loop safety rules regardless of approach:
1. Bug ID = SHA256(file + line + description) — deduplication
2. Max 3 attempts per bug ID — escalate to human after
3. "Fixed" state persists across QA restarts — no re-processing solved bugs

**Trade-off accepted:** Risk of misclassification routing complex bugs to fast lane. Mitigated: fast-lane spec template forces minimal diff (≤5 LOC), Autopilot review will reject if change is too large.

---

---

## Pattern 4: Telegram Approve/Reject Flow

---

### Approach 4A: Per-Message Inline Keyboard (PTB ConversationHandler)

**Source:** [python-telegram-bot inline keyboard examples](https://docs.python-telegram-bot.org/en/v21.5/examples.inlinekeyboard2.html) | [PTB CallbackQuery docs](https://docs.python-telegram-bot.org/en/latest/telegram.callbackquery.html)

#### Description
Each finding is sent as a separate Telegram message with `InlineKeyboardMarkup([Approve, Reject, Details])`. `CallbackQueryHandler` maps callback data to finding ID in SQLite. Batch operations ("Approve All", "Reject All") sent as a final summary message. No `ConversationHandler` needed — callbacks are stateless (finding ID is in callback_data).

#### Pros
- Native PTB pattern — well-documented, 29K stars repo
- Stateless callbacks: `callback_data="approve:finding_id_123"` carries all state
- PTB `arbitrary_callback_data` handles complex objects natively (no string encoding needed)
- Batch messages support: after 25 individual messages, send "Approve All / Reject All" summary

#### Cons
- 25 messages = Telegram chat becomes noisy
- Telegram throttles `sendMessage` at ~30 msg/sec — need `asyncio.sleep(0.05)` between messages
- Callback buttons expire after bot restart unless using `PicklePersistence` or DB-backed state

#### Complexity
**Estimate:** Medium — 4-6 hours
**Why:** PTB pattern is straightforward, but 25 messages × inline keyboard + batch operations + SQLite state = real implementation work.

#### Example Source
```python
async def send_finding(bot, chat_id: int, finding: Finding):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve", callback_data=f"approve:{finding.id}"),
        InlineKeyboardButton("Reject",  callback_data=f"reject:{finding.id}"),
    ]])
    await bot.send_message(
        chat_id=chat_id,
        text=f"[{finding.severity}] `{finding.file}:{finding.line}`\n{finding.description}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await asyncio.sleep(0.05)  # Rate limit guard
```

---

### Approach 4B: Single Summary Message with Paginated Review

**Source:** [PTB arbitrary callback data](https://docs.python-telegram-bot.org/en/latest/examples.arbitrarycallbackdatabot.html)

#### Description
Send one summary message with "Review findings (1/25)" pagination. User navigates through findings one at a time via Prev/Next buttons. Approve/Reject recorded in SQLite. Final "Confirm Batch" sends all approved findings to Spark.

#### Pros
- Chat stays clean — one message instead of 25
- Easier to re-review: just scroll back to one message
- No Telegram rate limiting issues

#### Cons
- UX is slower: must tap through 25 findings sequentially
- Pagination state must be tracked per-user per-session
- Cannot act on multiple findings simultaneously

#### Complexity
**Estimate:** Medium — 5-7 hours
**Why:** Pagination state, edit_message_text calls, more complex state machine.

#### Example Source
Edit-in-place pagination pattern:
```python
await query.edit_message_text(
    text=render_finding(findings[idx]),
    reply_markup=nav_keyboard(idx, total)
)
```

---

### Approach 4C: Grouped Messages by Severity (Sections)

**Source:** [PTB JobQueue + message batching](https://github-wiki-see.page/m/python-telegram-bot/python-telegram-bot/wiki/Extensions---JobQueue)

#### Description
Group findings by severity: one Telegram message per severity group (critical/high/medium/low). Each group message lists findings as numbered items. Group-level approve/reject buttons plus per-item overrides via `/approve 3 5 7` text commands.

#### Pros
- 4 messages instead of 25 = much cleaner chat
- Critical findings always at top — natural triage
- Mixed button+command UX is flexible

#### Cons
- Text command UX (`/approve 3 5 7`) is less discoverable than buttons
- Group-level approval is coarser — user may want to approve 3 of 7 in a group
- Parsing `/approve` with item IDs is error-prone

#### Complexity
**Estimate:** Medium — 5-6 hours
**Why:** Grouping logic, mixed command+callback handling, item numbering across groups.

---

### Comparison Matrix — Telegram Approval Flow

| Criteria | 4A: Per-Message | 4B: Paginated | 4C: Severity Groups |
|----------|----------------|---------------|---------------------|
| Complexity | Medium | Medium-High | Medium |
| UX Clarity | High (immediate) | Low (slow) | High |
| Chat Noise | High (25 msgs) | Low (1 msg) | Low (4 msgs) |
| Batch Operations | Easy | Medium | Easy |
| State Persistence | Easy (PTB callback) | Medium | Easy |
| Rate Limit Risk | Medium | Low | Low |

---

### Recommendation — Telegram Approval Flow

**Selected:** Approach 4C (Grouped by Severity)

**Rationale:** 25 individual messages will make the chat unusable over weeks of nightly reviews. Grouping by severity (critical/high/medium/low) maps exactly to how a developer triage works: fix critical first, evaluate high, skip low noise. Group-level approve/reject covers 90% of workflow; per-item `/approve ID` handles exceptions.

**Trade-off accepted:** Slightly more complex than 4A (need grouping + mixed UX). Per-message (4A) is simpler to build but creates chat spam that will cause review fatigue, which defeats the entire purpose of the night reviewer.

---

---

## Pattern 5: Claude CLI Headless on VDS

---

### Approach 5A: ANTHROPIC_API_KEY (API Credits)

**Source:** [Claude Code Headless Docs](https://code.claude.com/docs/en/headless) | [Claude Code CI/CD Cheatsheet](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/cheatsheet/)

#### Description
Set `ANTHROPIC_API_KEY` in VDS environment. Run `claude -p "prompt" --cwd /path/to/project --allowedTools Read,Write,Bash`. Each project invocation uses `--cwd` for CLAUDE.md context. Multiple concurrent processes are safe — no OAuth token race condition.

#### Pros
- No token expiry issues — API keys don't expire
- No OAuth race condition with concurrent processes (confirmed issue in OAuth mode: #27933)
- Simple: one env var, standard auth
- `--cwd` flag loads project CLAUDE.md automatically
- CLAUDE.md hierarchy: global (`~/.claude/CLAUDE.md`) → project (`{cwd}/CLAUDE.md`) both loaded

#### Cons
- Pay-per-token billing (vs flat-rate Claude Max subscription)
- Cost: $5-15 per full autopilot run on Opus — adds up with 10 projects
- No access to Claude Max subscription features (if user has Max)

#### Complexity
**Estimate:** Easy — 1 hour
**Why:** Just set env var. Already documented. No new code.

#### Example Source
```bash
# Per-project invocation
ANTHROPIC_API_KEY=sk-ant-... claude -p "$(cat spec.md)" \
  --cwd /home/user/projects/myapp \
  --allowedTools Read,Write,Bash \
  --output-format json \
  --max-turns 30
```

---

### Approach 5B: OAuth Token (Claude Max Subscription)

**Source:** [Automating Claude Code Setup on Headless VPS](https://gist.github.com/coenjacobs/d37adc34149d8c30034cd1f20a89cce9) | [OAuth race condition bug #27933](https://github.com/anthropics/claude-code/issues/27933)

#### Description
Generate long-lived OAuth token via `claude setup-token` on a local machine. Copy to VDS as `CLAUDE_CODE_OAUTH_TOKEN` env var. Skip API billing — uses Claude Max subscription.

#### Pros
- Uses existing Claude Max subscription (no per-token billing)
- Effectively unlimited within Max rate limits

#### Cons
- **Critical known bug**: multiple concurrent `claude` processes race on OAuth token refresh (issue #27933, #24317, confirmed March 2026, still open)
- Token expires (access token: ~10-15min; OAuth setup-token: ~1 year — but refresh is broken for concurrent processes)
- Workaround required: serialize all claude invocations (no parallelism), or use separate `~/.claude/` dirs per process
- Refresh token is single-use — race condition permanently breaks auth

#### Complexity
**Estimate:** Medium — 4-6 hours (including race condition workaround)
**Why:** Token setup is easy; surviving concurrent usage requires a file-lock wrapper or process serialization layer.

#### Example Source
Race condition confirmed (GitHub #27933, Feb 2026):
> "The loser of the race gets a 404 and loses authentication with no automatic recovery. Multiple processes read the same refresh_token from `~/.claude/.credentials.json` without any file locking."

Workaround pattern:
```bash
# Serialize claude invocations via flock
flock /tmp/claude.lock claude -p "..." --cwd /project
```

---

### Approach 5C: Isolated Credential Directories Per Process

**Source:** [CLAUDE_CODE_CONFIG_DIR environment variable](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/cheatsheet/)

#### Description
Set `CLAUDE_CODE_CONFIG_DIR=/home/user/.claude-project-N` per invocation. Each concurrent process has its own credentials file — no race condition. Each dir gets a copy of the OAuth credentials (or API key). Used in combination with 5A or 5B.

#### Pros
- Eliminates OAuth race condition entirely (separate credential files)
- Supports true parallelism (2-3 concurrent autopilots)
- Can mix auth types per project (some API key, some OAuth)

#### Cons
- Must provision N credential directories at setup time
- OAuth tokens expire → must refresh all N copies
- CLAUDE.md hierarchy still works (global `~/.claude/` + project `{cwd}/CLAUDE.md`)

#### Complexity
**Estimate:** Easy-Medium — 2-4 hours
**Why:** Shell wrapper + directory provisioning. No new code beyond orchestrate.sh changes.

#### Example Source
```bash
# Per-slot credential isolation
CLAUDE_CODE_CONFIG_DIR=/home/user/.claude-slot-${SLOT_ID} \
  claude -p "..." --cwd /path/to/project
```

---

### Comparison Matrix — Claude CLI Headless

| Criteria | 5A: API Key | 5B: OAuth Token | 5C: Isolated Dirs |
|----------|------------|----------------|-------------------|
| Complexity | Low | Medium | Easy-Medium |
| Concurrent Safety | High | Low (known bug) | High |
| Cost | Per-token | Flat (Max sub) | Flat (Max sub) |
| Token Expiry | Never | Race condition risk | Manageable |
| --cwd support | Full | Full | Full |
| Setup time | 1h | 4-6h | 2-4h |

---

### Recommendation — Claude CLI Headless

**Selected:** Approach 5A (ANTHROPIC_API_KEY) for reliability; migrate to 5C when Max cost matters

**Rationale:** OAuth race condition (issue #27933) is confirmed open as of March 10, 2026 with no fix ETA. Running 2-3 concurrent autopilots = guaranteed auth failures with OAuth. The API key approach has zero race condition risk. For 10 projects × 2-3 concurrent runs, cost is manageable (each autopilot run = $5-15 on Opus; nightly reviewer uses Sonnet at $0.50-2/run).

If Claude Max subscription savings become important at scale, migrate to 5C (isolated credential dirs) — it's the only OAuth-based approach that's truly safe for concurrent use.

**Trade-off accepted:** Per-token billing. Night reviewer uses Sonnet to minimize cost. Autopilots use Opus (the quality is worth it per CLAUDE.md cost guidelines: $200/month = negligible vs $200/hour human time).

---

---

## Pattern 6: Evening Review Prompt (Scheduled Telegram Prompt)

---

### Approach 6A: PTB JobQueue run_daily + Inline Keyboard

**Source:** [PTB JobQueue Wiki](https://github-wiki-see.page/m/python-telegram-bot/python-telegram-bot/wiki/Extensions---JobQueue) | [JobQueue run_daily docs](https://docs.python-telegram-bot.org/en/v22.0/telegram.ext.jobqueue.html)

#### Description
Use PTB's built-in `JobQueue` (APScheduler backend) to call `run_daily(callback, time=datetime.time(22, 0, tzinfo=tz))`. Callback sends a message with inline keyboard listing all active projects as checkboxes. User selects projects → confirms → triggers night reviewer for selected projects.

#### Pros
- Native PTB, zero extra dependencies (already using PTB for bot)
- `run_daily` with timezone-aware `datetime.time` — configurable time
- Multi-select checkboxes via callback_data state stored in `bot_data`
- Trivial to add: `pip install "python-telegram-bot[job-queue]"` + ~20 lines

#### Cons
- Job state does not persist across bot restarts (PTB limitation — APScheduler jobs not serialized)
- Configurable time requires either slash command or DB setting (not built-in)
- `run_daily` uses APScheduler backend which may drift slightly over time

#### Complexity
**Estimate:** Easy — 2-3 hours
**Why:** PTB has timerbot.py example. Inline keyboard for checkboxes is straightforward. Main work: multi-select state management.

#### Example Source
```python
import datetime, pytz

tz = pytz.timezone("Europe/Moscow")
evening_time = datetime.time(22, 0, tzinfo=tz)

async def evening_prompt(context: ContextTypes.DEFAULT_TYPE):
    projects = await db.get_all_projects()
    keyboard = [[InlineKeyboardButton(p.name, callback_data=f"toggle:{p.id}")]
                for p in projects]
    keyboard.append([InlineKeyboardButton("Launch Selected", callback_data="launch_review")])
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Launch nightly review? Select projects:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

app.job_queue.run_daily(evening_prompt, time=evening_time)
```

---

### Approach 6B: External Cron → Trigger via Bot API

**Source:** [Cron + Telegram Bot API pattern](https://community.latenode.com/t/scheduling-hourly-messages-with-python-telegram-bot/9258)

#### Description
System cron job calls `curl https://api.telegram.org/bot{TOKEN}/sendMessage` at 10pm. Bot receives message as a regular update, triggers project selection flow.

#### Pros
- Cron is battle-tested, survives bot restarts
- No in-process scheduler — simpler bot code
- Easy to change schedule without touching bot code

#### Cons
- Cron sends to bot as external HTTP call — adds complexity vs internal job
- Two systems to configure (cron + bot) instead of one
- No easy way to pass "which projects" context from cron to bot

#### Complexity
**Estimate:** Easy — 1-2 hours
**Why:** Simple cron + curl. Bot handler is standard PTB message handler.

---

### Approach 6C: APScheduler Directly (Without PTB Wrapper)

**Source:** [APScheduler 3.x docs](https://apscheduler.readthedocs.io/)

#### Description
Add APScheduler as direct dependency, bypass PTB's JobQueue wrapper. More control over job persistence (SQLAlchemyJobStore for SQLite), misfire handling, coalescing.

#### Pros
- Job persistence across restarts (SQLAlchemyJobStore)
- Advanced misfire handling: if bot was down at 10pm, run at next startup
- Full APScheduler API: cron expressions, timezone, jitter

#### Cons
- Adds direct APScheduler dependency (PTB already uses it internally — version conflicts possible)
- Significantly more complex than PTB's `run_daily`
- Overkill: a 10pm daily job doesn't need persistent scheduler

#### Complexity
**Estimate:** Medium — 4-5 hours
**Why:** APScheduler setup, SQLite job store, integration with PTB async loop.

---

### Comparison Matrix — Evening Review Prompt

| Criteria | 6A: PTB JobQueue | 6B: External Cron | 6C: APScheduler Direct |
|----------|-----------------|-------------------|----------------------|
| Complexity | Low | Low | Medium |
| Restart survival | No (jobs lost) | Yes | Yes |
| Configurability | Medium | Low | High |
| Dependencies | PTB job-queue extra | None | APScheduler |
| Code location | Bot process | System cron | Bot process |
| Inline keyboard UX | Full | Full | Full |

---

### Recommendation — Evening Review Prompt

**Selected:** Approach 6A (PTB JobQueue) + job re-registration on startup

**Rationale:** PTB JobQueue is already the right tool — it's built into the framework we're already using (telegram-bot.py, FTR-146). The job persistence gap is solved trivially: register the daily job in `post_init` callback, so it's recreated on every bot restart. At 10pm daily, if bot is running, job fires. If bot was down, it fires next day.

**Trade-off accepted:** No misfire recovery (if bot was down exactly at 10pm, review prompt is skipped for that day). This is acceptable for a nightly dev tool — developer can always manually trigger via `/review` command.

---

---

## Comparison Matrix — All Patterns

| Pattern | Selected Approach | Complexity | Key Risk | Mitigation |
|---------|------------------|------------|----------|------------|
| Night Reviewer | 1B: Night Critic Agent | Medium-Hard | Context overflow on large repos | ADR-008 background fan-out |
| Whisper | 2A: Groq API | Easy | Rate limits | 20 req/min free, upgrade if needed |
| QA Fix Loop | 3B: Two-Speed | Medium | Trivial/complex misclassification | Conservative classifier, fast-lane ≤5 LOC guard |
| Telegram Approval | 4C: Severity Groups | Medium | Text command discoverability | Hybrid: buttons + `/approve ID` fallback |
| Claude Headless | 5A: API Key | Easy | Per-token cost | Sonnet for reviewer, Opus for autopilot only |
| Evening Prompt | 6A: PTB JobQueue | Easy | Job lost on restart | Re-register in post_init |

---

## Research Sources

- [Groq Speech-to-Text Docs](https://console.groq.com/docs/speech-to-text) — Whisper API integration, supported formats, rate limits, language codes
- [Multi-Model AI Code Review: Convergence Loops](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence) — Night reviewer architecture, convergence behavior, false positive handling
- [Claude Code OAuth race condition #27933](https://github.com/anthropics/claude-code/issues/27933) — Confirmed concurrent process auth bug, root cause analysis
- [Automating Claude Code on Headless VPS](https://gist.github.com/coenjacobs/d37adc34149d8c30034cd1f20a89cce9) — CLAUDE_CODE_OAUTH_TOKEN setup, workarounds
- [Claude Code Headless/CI Cheatsheet](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/cheatsheet/) — All CLI flags, ANTHROPIC_API_KEY, CLAUDE_CODE_CONFIG_DIR
- [python-telegram-bot JobQueue Wiki](https://github-wiki-see.page/m/python-telegram-bot/python-telegram-bot/wiki/Extensions---JobQueue) — run_daily, APScheduler backend, restart behavior
- [PTB inline keyboard examples](https://docs.python-telegram-bot.org/en/v21.5/examples.inlinekeyboard2.html) — CallbackQueryHandler, callback_data patterns
- [dshills/prism](https://github.com/dshills/prism) — Structured JSON findings from LLM code review, per-file/line/severity output format
- [Why Agents Get Stuck in Loops](https://gantz.ai/blog/post/agent-loops/) — Failure memory, deduplication, max iterations, escalation patterns
- [A Dual-Loop Agent Framework](https://arxiv.org/html/2602.05721v1) — Plan-execute-evaluate for QA loop, separating exploration vs implementation
- [Batch Groq Whisper transcription](https://gist.github.com/sebington/c2e6c6ef7bb32fb8bcb1f2cd062b4bdc) — Python code example for whisper-large-v3-turbo
- [Russian CPU STT benchmark](https://habr.com/ru/articles/1002260/) — whisper.cpp CPU latency on Russian (15-60s), GigaAM comparison
- [Self-Healing AI Agents patterns](https://dev.to/techfind777/building-self-healing-ai-agents-7-error-handling-patterns-that-keep-your-agent-running-at-3-am-5h81) — Retry storm prevention, circuit breaker, rate limit handling
