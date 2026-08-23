#!/usr/bin/env python3
"""
Module: claude-runner
Role: Claude Code Agent SDK wrapper for programmatic task execution with Skills.
Uses: claude-agent-sdk, db.py, datetime (heartbeat timestamps)
Used by: run-agent.sh (via Pueue)

Key design (2026-03-11):
  Skills (/spark, /autopilot, /council etc.) only work when the Skill tool
  is enabled AND setting_sources includes "project" so that .claude/skills/
  is discovered.  The Agent SDK gives us this natively — no TTY/pipe hacks.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def load_env() -> None:
    """Load KEY=VALUE pairs from .env file next to this script into os.environ.

    Uses setdefault so existing env vars win (e.g., systemd EnvironmentFile).
    """
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_env()

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TaskNotificationMessage,
        query,
    )
    from claude_agent_sdk._errors import CLIConnectionError, ProcessError
except ImportError:
    sys.exit("claude-agent-sdk not installed. Run: pip install claude-agent-sdk")

# BUG-188 Layer 4: lazy import for telemetry (tests w/o VPS deps still run)
try:
    import db as _orch_db
except ImportError:
    _orch_db = None

# Work preservation on abnormal exit. Optional import for the same reason as db:
# the runner must still start on a box without the full VPS module set.
try:
    import salvage as _salvage
except ImportError:
    _salvage = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Both constants were set on 2026-03-12 and never revisited. They were calibrated
# against a run that no longer exists: until 2026-07-26 (a710cf5) pueue resolved a
# March-frozen CLI 2.1.72 off systemd's PATH, which predates Opus 5 and silently ran
# claude-opus-4-6 with a 200K window. Measured over 1087 joined runs:
#
#                        median turns   median wall-clock   s/turn   timeout rate
#   before 2026-07-26         11             8.7 min         15.5         1%
#   from   2026-07-26         49            47.1 min         50.3        32%
#
# 4.5x the turns and 3.2x the seconds per turn — real Opus 5 on a 1M window thinks
# longer per turn and is no longer forced to converge by autocompact every ~155K.
# Nothing about spec sizing changed; the cost of executing a spec did.
#
# At 5400s the p90 of runs that DID finish was 81.7 min and the slowest was 86.9 —
# the distribution's upper decile was sitting on the wall, which is what a 32%
# failure rate looks like from the inside. 90 min was ~10x the median run in March;
# it was ~1.9x by August.
#
# 10800s restores roughly 4x headroom over the current median. It is a measured step,
# not a final answer: re-run scripts/vps/ analysis against task_log after a few weeks
# and move it again if the tail still crosses. Two deferred improvements were blocked
# on this number and can now be re-evaluated — planner held at high instead of xhigh
# (BUG-1101) and ADR-028's "xhigh-for-agentic upside deferred pending TIMEOUT_SECONDS
# increase". A dead run is not lost work: salvage.py pushes the branch either way.
TIMEOUT_SECONDS = 10800  # 3 h. Was 5400 (2026-03-12 → 2026-08-23); see above.
# Backstop, not a target — the wall-clock timeout is the real limit. Only 2 of 67
# post-cutover runs came within 5 turns of 120, but they finished in ~47 min; at
# 10800s a legitimate run has time for ~3x that, so 120 would become the new binding
# constraint. A run that exhausts max_turns still returns a ResultMessage and is
# recorded as a SUCCESS, so this ceiling fails silently — keep it well clear of normal.
MAX_TURNS = 300
# Main autopilot loop model. Explicit (not settings-alias "opus") so the SDK is
# pinned deterministically. Override per-task via AUTOPILOT_MODEL env. Subagents
# resolve their own model from agent frontmatter. See rules/model-capabilities.md.
MODEL = os.environ.get("AUTOPILOT_MODEL", "claude-opus-5")
# Main loop effort level.  SDK enum: low|medium|high|max (the "extra-high" level
# accepted by CLI/frontmatter is NOT part of the SDK enum and would be rejected
# by ClaudeAgentOptions).  Subagents resolve effort from frontmatter.  ADR-028.
# Opus 5: thinking is ON by default and CANNOT be disabled at effort xhigh/max
# (HTTP 400).  We never pass `thinking`, so any effort here is safe — but do not
# add a thinking-disable option without capping effort at high.  ADR-029.
AUTOPILOT_EFFORT = os.environ.get("AUTOPILOT_EFFORT", "high")
_VALID_EFFORT = {"low", "medium", "high", "max"}
if AUTOPILOT_EFFORT not in _VALID_EFFORT:
    AUTOPILOT_EFFORT = "high"  # fail-safe: unknown value → default


# A CLI older than this does not know the Opus 5 / Sonnet 5 model IDs and will
# silently run its own era's default model instead of the one we pin. 2.1.190 is
# the floor we have verified resolves `claude-opus-5` correctly.
_MIN_CLI_VERSION = (2, 1, 190)

# Distro-style install location, probed last. Named so tests can point it
# somewhere hermetic instead of at whatever the host happens to have.
_SYSTEM_CLI_FALLBACK = "/usr/local/bin/claude"


def _cli_version(path: str) -> tuple[int, int, int] | None:
    """Ask a CLI binary which version it is. None if it won't answer."""
    try:
        p = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", p.stdout or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _resolve_cli_path() -> tuple[str | None, tuple[int, int, int] | None]:
    """Pick the NEWEST Claude Code CLI on the box, not the first one on PATH.

    Ordering by PATH is what broke this for four months (found 2026-07-26). Under
    pueue the daemon inherits systemd's PATH — `/usr/local/sbin:/usr/local/bin:…`
    with no `~/.local/bin` at all — so `shutil.which("claude")` returned a
    root-owned 2.1.72 binary frozen since March, while the installer's
    self-updating launcher at ~/.local/bin/claude sat at 2.1.220 unused. 2.1.72
    predates Opus 5, so `model="claude-opus-5"` silently ran claude-opus-4-6:
    a 200K window instead of 1M, autocompact every ~155K, 34 compactions in one
    90-minute run, and a timeout with nothing merged.

    Version comparison is the only ordering that self-heals — whichever install
    the operator keeps current wins, no matter how PATH is arranged. An explicit
    CLAUDE_CLI_PATH still overrides everything. Candidates that refuse to report
    a version are kept only as a last-resort fallback, and returning (None, None)
    lets the SDK use its bundled CLI rather than crash.
    """
    pinned = os.environ.get("CLAUDE_CLI_PATH")
    if pinned and Path(pinned).exists():
        return pinned, _cli_version(pinned)

    candidates = [
        shutil.which("claude"),
        str(Path.home() / ".local" / "bin" / "claude"),
        _SYSTEM_CLI_FALLBACK,
    ]
    seen: set[str] = set()
    best: tuple[str, tuple[int, int, int]] | None = None
    unversioned: str | None = None

    for candidate in candidates:
        if not candidate:
            continue
        real = str(Path(candidate).resolve()) if Path(candidate).exists() else ""
        if not real or real in seen:
            continue
        seen.add(real)
        version = _cli_version(candidate)
        if version is None:
            unversioned = unversioned or candidate
        elif best is None or version > best[1]:
            best = (candidate, version)

    if best:
        return best
    return unversioned, None


CLI_PATH, CLI_VERSION = _resolve_cli_path()

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("claude-runner")


def _write_heartbeat(
    log_dir: Path,
    project_name: str,
    ts_label: str,
    turn: int,
    elapsed_s: int,
    last_tool: str | None,
    started_at_iso: str,
    model: str,
) -> None:
    """Atomic per-turn heartbeat (best-effort, ADR-004). cost_usd omitted (SDK: ResultMessage only)."""
    try:
        hb_path = log_dir / f"{project_name}-{ts_label}.heartbeat.json"
        tmp_path = hb_path.with_suffix(".tmp")
        data = {
            "turn": turn,
            "elapsed_s": elapsed_s,
            "last_tool": last_tool,
            "started_at": started_at_iso,
            "model": model,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        tmp_path.write_text(json.dumps(data, ensure_ascii=False))
        os.replace(str(tmp_path), str(hb_path))
    except Exception:  # noqa: BLE001 — heartbeat is best-effort (ADR-004 style)
        pass


# All tools that DLD skills may need
ALLOWED_TOOLS = [
    "Skill",
    "Agent",
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "NotebookEdit",
]


# Autopilot's structured completion signal. The agent is told to emit a final
# JSON object with `task_status`, but Opus 4.x often wraps it in a markdown
# report (```json fence inside prose). Scan the full result text for the token
# so the callback gets the signal regardless of formatting / truncation.
_TASK_STATUS_RE = re.compile(r'"task_status"\s*:\s*"([a-z_]+)"')


def _extract_task_status(result_text: str) -> str:
    """Best-effort extraction of task_status from the agent's final text.

    Robust to the value being embedded in a markdown ```json fence rather than
    a bare top-level JSON object. Returns "" if not found. Lifted to a
    top-level log field so callback._parse_log_file never depends on the
    (truncated) result_preview being valid JSON.
    """
    if not result_text:
        return ""
    m = _TASK_STATUS_RE.search(result_text)
    return m.group(1) if m else ""


# --- Safety-classifier refusals -------------------------------------------
# Opus 5 (and Fable 5) carry safety classifiers that can decline a request. The
# decline is `stop_reason: "refusal"` inside a normal HTTP 200 with an empty
# `content` — not an exception, not a 4xx, nothing raises. Two agents in this
# repo are prompted for exactly the `cyber` category (`council-security`,
# `bughunt-security-auditor`), and Anthropic's own note on that category is
# "benign cybersecurity work can also trigger this category". A declined
# security review that flows on as a successful run is indistinguishable from
# a clean one.
_REFUSAL_STOP_REASON = "refusal"
_REFUSAL_TEXT_LIMIT = 400
_REFUSAL_EVENT_LIMIT = 10


def _message_text(message) -> str:
    """Join the text blocks of a message. Empty string when it carries none."""
    parts = []
    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def _refusal_from_message(message) -> dict | None:
    """Recognise a classifier decline in one SDK message. None when there is none.

    Two shapes reach us and they mean different things:

    1. `stop_reason == "refusal"` on an AssistantMessage or on the ResultMessage
       — the raw decline. Content is empty or partial and must not be trusted.
    2. A `system` message with subtype `model_refusal_fallback` — the CLI arms
       server-side fallback (`server-side-fallback-2026-07-01`) and re-runs the
       declined request on the model Anthropic maps that refusal category to.
       The answer is real, but it came from a model we did not pin.

    `stop_details.category` never survives claude_agent_sdk's typed messages:
    `AssistantMessage`/`ResultMessage` are dataclasses with a `stop_reason`
    field and no `stop_details` one, so the parser drops it. The fallback
    system message is the only place the category reaches us, under
    `data["apiRefusalCategory"]` — SDK message parsing keeps unknown `system`
    subtypes whole as `SystemMessage(subtype=..., data=<raw dict>)`.

    Duck-typed rather than isinstance-based on purpose: it has to stay callable
    against a stub message in a test process with no Agent SDK installed.
    """
    subtype = getattr(message, "subtype", None)
    data = getattr(message, "data", None)
    if isinstance(subtype, str) and _REFUSAL_STOP_REASON in subtype and isinstance(data, dict):
        explanation = data.get("apiRefusalExplanation") or data.get("content") or None
        if isinstance(explanation, str):
            explanation = explanation[:_REFUSAL_TEXT_LIMIT]
        else:
            explanation = None
        return {
            "source": subtype,
            "category": data.get("apiRefusalCategory"),
            "explanation": explanation,
            "original_model": data.get("originalModel"),
            "fallback_model": data.get("fallbackModel"),
            "served_by_fallback": bool(data.get("fallbackModel")),
        }

    stop_reason = getattr(message, "stop_reason", None)
    if isinstance(stop_reason, str) and stop_reason.strip().lower() == _REFUSAL_STOP_REASON:
        return {
            "source": type(message).__name__,
            "category": None,
            "explanation": _message_text(message)[:_REFUSAL_TEXT_LIMIT] or None,
            "original_model": getattr(message, "model", None),
            "fallback_model": None,
            "served_by_fallback": False,
        }
    return None


def _refusal_summary(events: list) -> dict:
    """Fold refusal events into the run-log block and the pass/fail decision.

    A decline the CLI re-ran on a fallback model produced real output, so
    failing the run would re-execute a finished spec for nothing — the BUG-188
    lesson. It is still an unannounced model swap, so it is surfaced the same
    way `model_drift` is: loud in the log, telemetry row, exit code untouched.

    A decline with no fallback behind it produced nothing, and that is the case
    that must not read as a clean run.

    A recovered episode can emit both shapes (the partially streamed assistant
    turn is retracted, then the fallback notice arrives), so the count of
    fallbacks served cancels the count of declines rather than adding to it.
    """
    declines = sum(1 for e in events if not e.get("served_by_fallback"))
    served = sum(1 for e in events if e.get("served_by_fallback"))
    return {
        "detected": bool(events),
        "declines": declines,
        "fallbacks_served": served,
        "unrecovered": max(0, declines - served),
        "categories": sorted({str(e["category"]) for e in events if e.get("category")}),
        "events": events[:_REFUSAL_EVENT_LIMIT],
    }


# Models this generation is supposed to use. Subagents resolve `opus`/`sonnet`
# aliases through the CLI, so a stale binary silently serves a previous
# generation to every subagent while the main loop's explicit pin looks correct.
# Production logs from 2026-07-16..18 show exactly that: main loop on
# claude-opus-4-8 with claude-opus-4-6 and claude-sonnet-4-6 subagents underneath.
_EXPECTED_MODELS = frozenset(
    m.strip()
    for m in os.environ.get(
        "AUTOPILOT_EXPECTED_MODELS",
        "claude-opus-5,claude-sonnet-5,claude-haiku-4-5-20251001",
    ).split(",")
    if m.strip()
)


def _usage_field(usage: dict, *names: str) -> int:
    """Read a usage counter under either camelCase or snake_case."""
    for n in names:
        if n in usage:
            try:
                return int(usage[n] or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _session_totals(model_usage: dict) -> dict:
    """Roll model_usage up into session-wide totals, and flag model drift.

    The top-level counters come from ResultMessage and describe the MAIN LOOP
    only, while cost_usd covers the whole session — main loop plus every
    subagent. Comparing them mixes scopes silently: production logs carry runs
    with `turns: 1` next to `cost_usd: 26.19`, because the main loop resumed,
    read a background result and stopped, while its subagents had already spent
    the money. State both scopes instead of leaving the reader to guess.
    """
    totals = {
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "session_cache_creation_input_tokens": 0,
        "session_cache_read_input_tokens": 0,
        "session_cache_hit_rate": 0.0,
        "cost_by_model": {},
        "model_drift": [],
    }
    if not isinstance(model_usage, dict):
        return totals

    for model, usage in model_usage.items():
        if not isinstance(usage, dict):
            usage = getattr(usage, "__dict__", {}) or {}
        totals["session_input_tokens"] += _usage_field(usage, "inputTokens", "input_tokens")
        totals["session_output_tokens"] += _usage_field(usage, "outputTokens", "output_tokens")
        totals["session_cache_creation_input_tokens"] += _usage_field(
            usage, "cacheCreationInputTokens", "cache_creation_input_tokens"
        )
        totals["session_cache_read_input_tokens"] += _usage_field(
            usage, "cacheReadInputTokens", "cache_read_input_tokens"
        )
        cost = usage.get("costUSD", usage.get("cost_usd", 0)) or 0
        try:
            totals["cost_by_model"][model] = round(float(cost), 4)
        except (TypeError, ValueError):
            totals["cost_by_model"][model] = 0.0
        if model not in _EXPECTED_MODELS:
            totals["model_drift"].append(model)

    denom = (
        totals["session_cache_read_input_tokens"]
        + totals["session_cache_creation_input_tokens"]
        + totals["session_input_tokens"]
    )
    if denom:
        totals["session_cache_hit_rate"] = round(
            totals["session_cache_read_input_tokens"] / denom, 4
        )
    return totals


_EXIT_REASONS = {
    124: "timeout",
    2: "cli_connection_error",
    3: "cli_process_error",
    4: "classifier_refusal",
    143: "sigterm",
}


def _salvage_if_needed(project_path, exit_code: int) -> dict | None:
    """Push what the run managed to build, if it died before it could.

    Autopilot pushes once, at the end of PHASE 3. Any abnormal exit therefore
    strands finished task commits on a local worktree branch that nothing else
    will ever look at. Runs only on failure, so the one-push-per-spec rule that
    keeps CI cheap (TECH-085) is unaffected.
    """
    if exit_code == 0 or _salvage is None:
        return None
    spec_id = _salvage.spec_id_from_path(os.environ.get("CLAUDE_CURRENT_SPEC_PATH", ""))
    if not spec_id:
        # Without a spec ID there is no way to tell which worktree belongs to
        # this run, and guessing would push another slot's branch.
        return {"attempted": False, "error": "no_spec_id"}
    try:
        return _salvage.salvage_run(
            str(project_path), spec_id, _EXIT_REASONS.get(exit_code, f"exit {exit_code}")
        )
    except Exception as e:  # ADR-004: never turn a failed run into a crashed runner
        logger.warning("salvage failed: %s", e)
        return {"attempted": True, "error": str(e)[:300], "pushed": False}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run_task(project_dir: str, task: str, skill: str) -> dict:
    """Run a Claude Code task with Skills via Agent SDK.

    Returns dict with exit_code, project, skill, task, cost_usd, turns.
    """
    project_path = Path(project_dir).resolve()
    project_name = project_path.name
    ts_label = time.strftime("%Y%m%d-%H%M%S")
    log_file = LOG_DIR / f"{project_name}-{ts_label}.log"
    started_at_iso = datetime.now(tz=timezone.utc).isoformat()
    started_mono = time.monotonic()

    # Build prompt with skill prefix
    if task.startswith("/"):
        prompt = task
    else:
        prompt = f"/{skill} {task}"

    logger.info(
        "project=%s skill=%s prompt=%s cwd=%s cli=%s v=%s model=%s effort=%s",
        project_name,
        skill,
        prompt,
        project_path,
        CLI_PATH,
        ".".join(map(str, CLI_VERSION)) if CLI_VERSION else "unknown",
        MODEL,
        AUTOPILOT_EFFORT,
    )
    # A CLI that predates the pinned model does not error — it quietly runs its
    # own default instead, and the only visible symptom is a shrunken context
    # window and a compaction storm. Say so out loud.
    if CLI_VERSION is not None and CLI_VERSION < _MIN_CLI_VERSION:
        logger.warning(
            "CLI %s at %s is older than %s and may not know %s — it will run its "
            "own default model with that model's (smaller) context window. "
            "Point CLAUDE_CLI_PATH at a current install.",
            ".".join(map(str, CLI_VERSION)),
            CLI_PATH,
            ".".join(map(str, _MIN_CLI_VERSION)),
            MODEL,
        )

    # Layer 2: capture subprocess CLI stderr via SDK callback (BUG-188)
    stderr_lines: list[str] = []

    def _stderr_collector(line: str) -> None:
        # Cap at 200 lines / ~50KB to bound memory on misbehaving CLI
        if len(stderr_lines) < 200:
            stderr_lines.append(line)

    # Agent SDK options
    options = ClaudeAgentOptions(
        cwd=str(project_path),
        model=MODEL,  # pin main loop to Opus 5 (env: AUTOPILOT_MODEL)
        effort=AUTOPILOT_EFFORT,  # pin effort (default high); see ADR-028
        cli_path=CLI_PATH,  # use system CLI, not stale bundled (else model pin drifts)
        setting_sources=["user", "project"],  # Loads CLAUDE.md + .claude/skills/
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=MAX_TURNS,
        env={
            "PROJECT_DIR": str(project_path),
            "CLAUDE_PROJECT_DIR": str(project_path),
            "CLAUDE_CURRENT_SPEC_PATH": os.environ.get("CLAUDE_CURRENT_SPEC_PATH", ""),
            "ENABLE_PROMPT_CACHING_1H": os.environ.get("ENABLE_PROMPT_CACHING_1H", "1"),
            # TECH-178: bypass cosmetic pre-commit fixers that auto-fix + exit 1
            # (trailing-whitespace, end-of-file-fixer, mixed-line-ending) so that
            # research-md commits don't trigger autopilot retry-loops. Lint-only
            # hooks (ruff/mypy/etc.) remain active. Operators can override per-task
            # by exporting SKIP="" before pueue add.
            "SKIP": os.environ.get(
                "SKIP",
                "trailing-whitespace,end-of-file-fixer,mixed-line-ending",
            ),
        },
        stderr=_stderr_collector,
    )

    result_text = ""
    last_assistant_text = ""
    turns = 0
    cost_usd = 0.0
    exit_code = 0
    turn_count = 0  # per AssistantMessage (available before ResultMessage)
    last_tool_name: str | None = None  # last tool used (for heartbeat + timeout report)
    usage_metrics = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_1h_input_tokens": 0,
        "cache_creation_5m_input_tokens": 0,
    }
    model_usage: dict = {}
    result_received = False
    result_is_error = False
    refusal_events: list = []

    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            async for message in query(prompt=prompt, options=options):
                # Log all messages
                msg_line = str(message)
                if len(msg_line) > 500:
                    msg_line = msg_line[:500] + "..."
                logger.debug(msg_line)

                # TECH-198 Layer A: heartbeat on EVERY message (not just
                # AssistantMessage) so updated_at stays fresh during long
                # tool-execution phases between assistant turns.
                _write_heartbeat(
                    LOG_DIR,
                    project_name,
                    ts_label,
                    turn_count,
                    int(time.monotonic() - started_mono),
                    last_tool_name,
                    started_at_iso,
                    MODEL,
                )

                # A classifier decline arrives inside a normal HTTP 200, so it
                # never reaches an except-branch. Check every message: the raw
                # decline lands on the assistant turn or on the result, while
                # the fallback notice is a `system` message and is the only
                # carrier of the refusal category (_refusal_from_message).
                refusal_event = _refusal_from_message(message)
                if refusal_event is not None:
                    refusal_events.append(refusal_event)

                # Capture assistant text (last response before ResultMessage)
                if isinstance(message, AssistantMessage):
                    turn_count += 1
                    text_parts = []
                    for block in getattr(message, "content", []):
                        if hasattr(block, "text"):
                            text_parts.append(block.text)
                        if getattr(block, "name", None):  # tool use block
                            last_tool_name = block.name
                    if text_parts:
                        last_assistant_text = "\n".join(text_parts)

                # Capture task completion summary (autopilot uses Agent tool → Tasks)
                if isinstance(message, TaskNotificationMessage):
                    summary = getattr(message, "summary", "")
                    if summary:
                        result_text = summary

                # Track final result
                if isinstance(message, ResultMessage):
                    result_received = True
                    result_is_error = bool(getattr(message, "is_error", False))
                    result_text = getattr(message, "result", "") or result_text
                    turns = getattr(message, "num_turns", 0)
                    cost_usd = getattr(message, "total_cost_usd", 0.0) or 0.0
                    if result_is_error:
                        exit_code = 1
                    usage = getattr(message, "usage", None) or {}
                    if not isinstance(usage, dict):
                        usage = getattr(usage, "__dict__", {}) or {}
                    # Flat keys (Anthropic API contract: input_tokens, output_tokens,
                    # cache_read_input_tokens). cache_creation is nested — see below.
                    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
                        usage_metrics[key] = int(usage.get(key, 0) or 0)
                    # cache_creation moved to nested dict in 2026 API revision:
                    # usage.cache_creation.ephemeral_{1h,5m}_input_tokens
                    cc = usage.get("cache_creation", {}) if isinstance(usage, dict) else {}
                    if isinstance(cc, dict):
                        h1 = int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
                        m5 = int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
                        usage_metrics["cache_creation_1h_input_tokens"] = h1
                        usage_metrics["cache_creation_5m_input_tokens"] = m5
                        usage_metrics["cache_creation_input_tokens"] = h1 + m5
                    # Per-model breakdown (Opus vs Sonnet vs Haiku in one run)
                    mu = getattr(message, "model_usage", None)
                    if isinstance(mu, dict):
                        model_usage = mu

        # Fallback: use last assistant message if no result_text
        if not result_text and last_assistant_text:
            result_text = last_assistant_text

    except TimeoutError:
        # asyncio.timeout() (Python 3.11+) — partial metrics (turn_count/cost_usd) are in scope
        elapsed = int(time.monotonic() - started_mono)
        logger.error("Timeout after %ds (partial: %d turns, $%.4f)", elapsed, turn_count, cost_usd)
        exit_code = 124  # Unix timeout convention
        result_text = f"Timeout after {elapsed}s (partial: {turn_count} turns, ${cost_usd:.4f}, last_tool={last_tool_name!r})"
    except CLIConnectionError as e:
        logger.error("CLI connection failed: %s", e)
        exit_code = 2
        result_text = f"CLI connection error: {e}"
    except ProcessError as e:
        logger.error("CLI process error: %s", e)
        exit_code = 3
        stderr = getattr(e, "stderr", None)
        if stderr:
            result_text = f"Process error: {e}\nSTDERR:\n{stderr}"
        elif stderr_lines:
            captured = "\n".join(stderr_lines[-100:])
            result_text = f"Process error: {e}\nSTDERR (captured):\n{captured}"
        else:
            result_text = f"Process error: {e}"
    except Exception as e:
        # Catch SDK init timeouts ("Control request timeout: initialize")
        err_str = str(e)
        stderr_from_exc = getattr(e, "stderr", None)
        if stderr_from_exc:
            err_str = f"{err_str}\nSTDERR:\n{stderr_from_exc}"
        elif stderr_lines:
            # Layer 2: fall back to lines captured via SDK stderr callback
            captured = "\n".join(stderr_lines[-100:])  # last 100 lines
            err_str = f"{err_str}\nSTDERR (captured):\n{captured}"

        if result_received and not result_is_error:
            # BUG-188: SDK threw AFTER successful ResultMessage. Work is done
            # (turns/cost/result_text already captured). Do NOT override
            # exit_code to 1 — that would re-block an already-done spec
            # and burn another $5+/run on retry.
            logger.warning(
                "SDK post-ResultMessage exception (work completed): %s",
                err_str[:500],
            )
            # exit_code stays 0; result_text already populated from ResultMessage
            # BUG-188 Layer 4: telemetry for SDK post-ResultMessage drift.
            if _orch_db is not None:
                try:
                    captured_stderr = "\n".join(stderr_lines[-100:]) if stderr_lines else None
                    _orch_db.log_sdk_post_result_error(
                        project_id=project_name,
                        task=task,
                        turns=turns,
                        cost_usd=cost_usd,
                        error_msg=str(e)[:2000],
                        stderr=captured_stderr,
                    )
                except Exception as log_exc:
                    # Telemetry must never break the runner (ADR-004 fail-safe).
                    logger.warning("Failed to log sdk_post_result_error: %s", log_exc)
        elif "timeout" in err_str.lower():
            logger.error("SDK init timeout: %s", e)
            exit_code = 124
            result_text = err_str
        else:
            logger.error("SDK error: %s", e, exc_info=True)
            exit_code = 1
            result_text = err_str

    # A run that dies before ResultMessage reports turns=0 and cost=0.0, because
    # both come from that message. That is how a 575-turn, 90-minute timeout came
    # to be logged as "$0.00, 0 turns" — the most expensive runs were the ones
    # reporting nothing. The cost genuinely isn't available, but the turn count is.
    if not turns:
        turns = turn_count

    refusal = _refusal_summary(refusal_events)
    if refusal["detected"]:
        logger.warning(
            "CLASSIFIER REFUSAL: %d decline(s), %d served by a fallback model, "
            "categories=%s. A decline is an HTTP 200 with empty content, so it "
            "arrives looking like a finished answer — from council-security or "
            "bughunt-security-auditor an empty report reads as a clean one. "
            "Anthropic's note on the `cyber` category: benign cybersecurity "
            "work can also trigger it.",
            refusal["declines"],
            refusal["fallbacks_served"],
            ", ".join(refusal["categories"]) or "unknown",
        )
    if refusal["unrecovered"] and exit_code == 0:
        # ADR-024 governs SDK exceptions raised AFTER a successful
        # ResultMessage; this is an in-stream observation and the BUG-188
        # branch is left untouched. Only upgrade from 0, so a timeout or a
        # process error keeps its own, more specific code.
        exit_code = 4

    salvage_info = _salvage_if_needed(project_path, exit_code)

    # Cache hit rate: fraction of total input that came from cache read.
    # Denominator = direct input + cache creation + cache read (total paid input-ish).
    cache_read = usage_metrics["cache_read_input_tokens"]
    cache_total = (
        cache_read + usage_metrics["cache_creation_input_tokens"] + usage_metrics["input_tokens"]
    )
    cache_hit_rate = round(cache_read / cache_total, 4) if cache_total > 0 else 0.0
    log_data = {
        "exit_code": exit_code,
        "project": project_name,
        "skill": skill,
        "task": task,
        "prompt": prompt,
        "turns": turns,
        "cost_usd": round(cost_usd, 4),
        # Drift telemetry: which binary actually ran, and what we asked it for.
        # A run whose model_usage disagrees with `model` means the CLI ignored
        # the pin (see _resolve_cli_path).
        "cli_path": CLI_PATH,
        "cli_version": ".".join(map(str, CLI_VERSION)) if CLI_VERSION else "",
        "model": MODEL,
        "effort": AUTOPILOT_EFFORT,
        "input_tokens": usage_metrics["input_tokens"],
        "output_tokens": usage_metrics["output_tokens"],
        "cache_creation_input_tokens": usage_metrics["cache_creation_input_tokens"],
        "cache_creation_1h_input_tokens": usage_metrics["cache_creation_1h_input_tokens"],
        "cache_creation_5m_input_tokens": usage_metrics["cache_creation_5m_input_tokens"],
        "cache_read_input_tokens": usage_metrics["cache_read_input_tokens"],
        "cache_hit_rate": cache_hit_rate,
        "model_usage": model_usage,
        "task_status": _extract_task_status(result_text),
        # Always present, even when nothing was declined: an absent key cannot
        # be told apart from a runner that predates the check.
        "refusal": refusal,
        "salvage": salvage_info,
        "result_preview": result_text[:1000] if result_text else "",
    }
    # `turns` and the counters above are MAIN-LOOP scope; cost_usd is session
    # scope. Publish the session scope explicitly rather than leaving the two
    # to be compared as if they matched.
    log_data.update(_session_totals(model_usage))
    if log_data["model_drift"]:
        logger.warning(
            "MODEL DRIFT: subagents ran %s — expected %s. A CLI that predates the "
            "pinned generation resolves `opus`/`sonnet` aliases to its own era, so "
            "the main loop's pin can look correct while every subagent is a "
            "generation behind.",
            ", ".join(sorted(log_data["model_drift"])),
            ", ".join(sorted(_EXPECTED_MODELS)),
        )
    # Refusal telemetry. Its own table rather than sdk_post_result_errors: that
    # table is read to measure post-ResultMessage SDK drift (BUG-188) and its
    # columns carry no room for category / fallback model, so mixing the two
    # signals would corrupt both counts.
    if refusal["detected"] and _orch_db is not None:
        try:
            _orch_db.log_classifier_refusal(
                project_id=project_name,
                task=task,
                skill=skill,
                model=MODEL,
                category=", ".join(refusal["categories"]) or None,
                declines=refusal["declines"],
                fallbacks_served=refusal["fallbacks_served"],
                unrecovered=refusal["unrecovered"],
                exit_code=exit_code,
                detail=json.dumps(refusal["events"], ensure_ascii=False)[:2000],
            )
        except Exception as log_exc:
            # Telemetry must never break the runner (ADR-004 fail-safe).
            logger.warning("Failed to log classifier_refusal: %s", log_exc)
    log_file.write_text(json.dumps(log_data, ensure_ascii=False, indent=2))
    logger.info(
        "done project=%s exit=%d turns=%d cost=$%.4f in=%d out=%d cache_read=%d cache_hit=%.2f",
        project_name,
        exit_code,
        turns,
        cost_usd,
        usage_metrics["input_tokens"],
        usage_metrics["output_tokens"],
        usage_metrics["cache_read_input_tokens"],
        cache_hit_rate,
    )

    return log_data


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: claude-runner.py <project_dir> <task> [skill]",
            file=sys.stderr,
        )
        sys.exit(1)

    project_dir = sys.argv[1]
    task = sys.argv[2]
    skill = sys.argv[3] if len(sys.argv) > 3 else "autopilot"

    # Prevent nested session detection
    for var in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        os.environ.pop(var, None)

    # `pueue kill` (heartbeat_reaper.py reaping a wedged session) arrives as
    # SIGTERM, which would otherwise end the process with the worktree's work
    # still unpushed — the same loss as a timeout, by a different route.
    # Salvage shells out to git from the handler: not async-signal-safe in
    # principle, but the process is ending either way and the alternative is
    # losing the run's output entirely.
    if hasattr(signal, "SIGTERM"):

        def _on_sigterm(_signum, _frame):
            logger.error("SIGTERM received — salvaging worktree before exit")
            try:
                logger.info("salvage: %s", _salvage_if_needed(Path(project_dir), 143))
            except Exception as e:
                logger.warning("salvage on SIGTERM failed: %s", e)
            os._exit(143)

        signal.signal(signal.SIGTERM, _on_sigterm)

    # Timeout is inside run_task (asyncio.timeout context). No wait_for here.
    result = asyncio.run(run_task(project_dir, task, skill))

    # Output structured JSON (same contract as bash version)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
