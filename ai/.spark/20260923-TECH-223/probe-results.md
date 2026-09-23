# Live probes on the VPS — 2026-09-23 (spark session TECH-223)

All on tietokettu-claude (`dld@5.61.91.190`), CLI `~/.local/bin/claude` → `versions/2.1.280`.

## P1. Env vars the 2.1.280 binary knows

`strings -n 8 $(readlink -f ~/.local/bin/claude) | grep -oE '…'` →
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`,
`CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS`, `BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`,
`CLAUDE_CODE_DISABLE_BG_EXIT_HANDOFF`, `CLAUDE_CODE_BG_TASKS_REPORT_RUNNING`, …
Binary source: `function zl(){return xq().backgroundTasksDisabled||a.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS}`
with message `"Background tasks are disabled in this session."`

## P2. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, `claude -p … --model claude-sonnet-5`

| Call | Result (verbatim head) | Verdict |
|---|---|---|
| Bash `run_in_background: true` | `InputValidationError: … An unexpected parameter \`run_in_background\` was provided` | closed |
| Agent `run_in_background: true` | `[Subagent hand-back] The text below is the final report of a subagent …` — ran synchronously | closed |
| ScheduleWakeup | `Next wakeup scheduled for 22:38:00 (in 66s). Nothing more to do this turn …` | **still open** |
| Monitor (ToolSearch select:Monitor) | `MON=yes` | **still open** |

## P3. Same env + `--disallowedTools "ScheduleWakeup" "Monitor" "CronCreate"`

ToolSearch `select:ScheduleWakeup,Monitor,CronCreate` → `AVAILABLE=NONE`. Deny list works.

## P4. What actually killed FTR-1515 run #2 (awardybot, 23.09)

Transcript `~/.claude/projects/-home-dld-projects-awardybot/99811244-68c5-41cc-a800-1adf984cd3b4.jsonl`, tail:
- 09:52:34/09:52:45 — two `Agent` calls returned "Async agent launched successfully" (coder Task 3 and Task 4 in background)
- 09:52:57 — `ScheduleWakeup {"delaySeconds":1800, "prompt":"/autopilot FTR-1515 — продолжить: дождаться coder Task 3/Task 4 …"}`
- 09:52:59 — "Coder'ы Task 3 и Task 4 работают в фоне. Продолжу, как только придут их результаты."
- Stop hook caught undelivered commits; branch pushed; then CLI stderr: `Background tasks still running after 600s; terminating.`

So the autopilot case is **background subagents + ScheduleWakeup**, not a background pytest. The QA case (e.g. dowry QA BUG-520, session 58406c3f) is Bash `run_in_background` on an `until grep … dowry-ci.log` CI-wait loop with timeout 1800000.

## P5. SDK in the runner venv

`scripts/vps/run-agent.sh:73` → `scripts/vps/venv/bin/python3`; installed
`claude_agent_sdk-0.1.63` (`requirements.txt`: `claude-agent-sdk>=0.1.63,<0.2.0`) — not 0.1.81 as
`model-capabilities.md` says. 0.1.63 already parses `rate_limit_event` into
`RateLimitEvent(rate_limit_info=RateLimitInfo(status, resets_at, rate_limit_type, utilization,
overage_status, overage_resets_at, overage_disabled_reason, raw), uuid, session_id)`
(`types.py:1044-1078`, `_internal/message_parser.py:233-252`). `status` ∈ allowed / allowed_warning / rejected.
`ResultMessage` in 0.1.63 has `is_error`, no `api_error_status`.

## P6. SendMessage continuation (for the separate "one coder per spec" question)

Headless 2.1.280: haiku subagent refused a SendMessage follow-up as injection; a sonnet subagent told
up front "task 2 will arrive as a follow-up message" continued and remembered context (`RESULT=PELICAN-47`).
