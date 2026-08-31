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
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import runner_cli  # noqa: E402 — CLI resolution + ALLOWED_TOOLS (TECH-213)
import runner_env  # noqa: E402 — .env loader (TECH-213)
import runner_heartbeat  # noqa: E402 — per-turn heartbeat file (TECH-213)
import runner_loop  # noqa: E402 — the SDK message loop (TECH-213)
import runner_refusal  # noqa: E402 — classifier-decline detection (TECH-213)
import runner_result  # noqa: E402 — run state, usage rollup, run log (TECH-213)

# Re-exports. The siblings are called as module attributes so a monkeypatch on the
# owning module takes effect; these names exist because the runner's tests reach
# them as `runner.<name>` and predate the split (same contract as the orchestrator
# and callback splits — TECH-215/216).
load_env = runner_env.load_env
_cli_version = runner_cli._cli_version
_resolve_cli_path = runner_cli._resolve_cli_path
_MIN_CLI_VERSION = runner_cli._MIN_CLI_VERSION
_SYSTEM_CLI_FALLBACK = runner_cli._SYSTEM_CLI_FALLBACK
ALLOWED_TOOLS = runner_cli.ALLOWED_TOOLS
_write_heartbeat = runner_heartbeat._write_heartbeat
_message_text = runner_refusal._message_text
_refusal_from_message = runner_refusal._refusal_from_message
_refusal_summary = runner_refusal._refusal_summary
_REFUSAL_STOP_REASON = runner_refusal._REFUSAL_STOP_REASON
_REFUSAL_TEXT_LIMIT = runner_refusal._REFUSAL_TEXT_LIMIT
_REFUSAL_EVENT_LIMIT = runner_refusal._REFUSAL_EVENT_LIMIT
_EXIT_REASONS = runner_result._EXIT_REASONS
_extract_task_status = runner_result._extract_task_status
_session_totals = runner_result._session_totals
_usage_field = runner_result._usage_field


load_env()

try:
    # Presence check only — the message loop (runner_loop) imports the names it needs.
    # Kept here so a missing dependency fails at the entry point with an instruction,
    # rather than as an ImportError from a module the operator has never heard of.
    import claude_agent_sdk  # noqa: F401
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


CLI_PATH, CLI_VERSION = _resolve_cli_path()

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("claude-runner")


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
    """Run a Claude Code task with Skills via Agent SDK. Returns the run-log dict."""
    project_path = Path(project_dir).resolve()
    project_name = project_path.name
    ts_label = time.strftime("%Y%m%d-%H%M%S")
    log_file = LOG_DIR / f"{project_name}-{ts_label}.log"
    # Аудит 30.08.2026, причина 3: stderr CLI ложится на диск рядом с логом
    # прогона, а не только в память процесса, который в этот момент умирает.
    # Расширение НЕ .log намеренно: callback_logs._find_log_file берёт свежайший
    # `{project}-*.log` по mtime, а stderr пишется во время прогона — он оказался
    # бы новее run-лога, и callback стал бы разбирать его как JSON.
    stderr_file = LOG_DIR / f"{project_name}-{ts_label}.stderr.txt"
    started_at_iso = datetime.now(tz=timezone.utc).isoformat()
    started_mono = time.monotonic()

    prompt = task if task.startswith("/") else f"/{skill} {task}"

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
    runner_cli.warn_if_stale(CLI_PATH, CLI_VERSION, MODEL)

    stderr_lines, stderr_collector = runner_loop.make_stderr_collector(stderr_file)
    options = runner_loop.build_options(
        project_path,
        stderr_collector,
        model=MODEL,
        effort=AUTOPILOT_EFFORT,
        cli_path=CLI_PATH,
        max_turns=MAX_TURNS,
    )

    state = runner_result.new_run_state()
    try:
        await runner_loop.consume(
            state,
            prompt,
            options,
            log_dir=LOG_DIR,
            project_name=project_name,
            ts_label=ts_label,
            started_mono=started_mono,
            started_at_iso=started_at_iso,
            model=MODEL,
            timeout_seconds=TIMEOUT_SECONDS,
        )
    except TimeoutError:
        # asyncio.timeout() (Python 3.11+) — partial metrics are already in `state`
        elapsed = int(time.monotonic() - started_mono)
        logger.error(
            "Timeout after %ds (partial: %d turns, $%.4f)",
            elapsed,
            state["turn_count"],
            state["cost_usd"],
        )
        state["exit_code"] = 124  # Unix timeout convention
        state["result_text"] = (
            f"Timeout after {elapsed}s (partial: {state['turn_count']} turns, "
            f"${state['cost_usd']:.4f}, last_tool={state['last_tool_name']!r})"
        )
    except Exception as e:  # noqa: BLE001 — mapped to an exit code, never swallowed
        runner_loop.handle_sdk_exception(
            e, state, stderr_lines, task, project_name, _orch_db, stderr_file
        )

    # A run that dies before ResultMessage reports turns=0 and cost=0.0, because
    # both come from that message. That is how a 575-turn, 90-minute timeout came
    # to be logged as "$0.00, 0 turns" — the most expensive runs were the ones
    # reporting nothing. The cost genuinely isn't available, but the turn count is.
    if not state["turns"]:
        state["turns"] = state["turn_count"]

    refusal = runner_refusal._refusal_summary(state["refusal_events"])
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
    if refusal["unrecovered"] and state["exit_code"] == 0:
        # ADR-024 governs SDK exceptions raised AFTER a successful ResultMessage;
        # this is an in-stream observation and that branch is left untouched. Only
        # upgrade from 0, so a timeout or a process error keeps its own code.
        state["exit_code"] = 4

    salvage_info = _salvage_if_needed(project_path, state["exit_code"])

    log_data = runner_result.build_log_data(
        state,
        project_name=project_name,
        skill=skill,
        task=task,
        prompt=prompt,
        cli_path=CLI_PATH,
        cli_version=".".join(map(str, CLI_VERSION)) if CLI_VERSION else "",
        model=MODEL,
        effort=AUTOPILOT_EFFORT,
        salvage_info=salvage_info,
        refusal=refusal,
        stderr_log=str(stderr_file),
        stderr_line_count=len(stderr_lines),
    )
    runner_result.log_refusal_telemetry(
        refusal,
        db=_orch_db,
        task=task,
        skill=skill,
        project_name=project_name,
        model=MODEL,
        exit_code=state["exit_code"],
    )
    runner_result.write_run_log(log_file, log_data)

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
