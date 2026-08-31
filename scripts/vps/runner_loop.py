#!/usr/bin/env python3
"""
Module: runner_loop
Role: the SDK message loop — build options, drain the stream into run state, and map
      an SDK exception onto an exit code.
Uses: claude_agent_sdk, runner_cli (ALLOWED_TOOLS), runner_heartbeat, runner_refusal,
      runner_result
Used by: claude-runner.py (run_task)

Split out of claude-runner.py by TECH-213. The runner keeps the pinned constants,
run_task and main; everything about HOW the stream is consumed lives here.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TaskNotificationMessage,
        query,
    )
    from claude_agent_sdk._errors import CLIConnectionError, ProcessError
except ImportError:  # pragma: no cover — the runner itself reports this
    raise

import runner_heartbeat
import runner_refusal
import runner_result
from runner_cli import ALLOWED_TOOLS

logger = logging.getLogger("claude-runner")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def make_stderr_collector(stderr_path: Path | None = None):
    """BUG-188 Layer 2: capture subprocess CLI stderr via SDK callback.

    Returns (stderr_lines, collector); the in-memory tail stays capped at 200
    lines to bound memory on a misbehaving CLI.

    Аудит 30.08.2026, причина 3: четыре прогона умерли с
    `Command failed with exit code 1 … Check stderr output for details`, а
    собранный этим коллектором stderr в логах был ПУСТ — то есть единственная
    улика существовала только в памяти процесса, который к тому моменту уже
    сворачивался. Поэтому каждая строка теперь пишется на диск НЕМЕДЛЕННО, а не
    доживает до сборки run-лога.

    Файл создаётся сразу, с шапкой. Пустой файл с одной шапкой — это тоже
    показание: он отличает «CLI ничего не сказал» от «мы забыли подписаться».
    Раньше эти два случая выглядели одинаково — никак.
    """
    stderr_lines: list[str] = []
    handle = None
    if stderr_path is not None:
        try:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            handle = stderr_path.open("a", encoding="utf-8", buffering=1)
            handle.write(f"# claude-runner stderr — opened {_now_iso()}\n")
            handle.flush()
        except OSError as exc:
            # Диагностика не имеет права ронять прогон.
            logger.warning("stderr log unavailable (%s): %s", stderr_path, exc)
            handle = None

    def _collector(line: str) -> None:
        if len(stderr_lines) < 200:
            stderr_lines.append(line)
        if handle is not None:
            try:
                handle.write(line + "\n")
            except (OSError, ValueError):
                pass

    return stderr_lines, _collector


def build_options(project_path: Path, stderr_collector, *, model, effort, cli_path, max_turns):
    """Assemble ClaudeAgentOptions for one run."""
    return ClaudeAgentOptions(
        cwd=str(project_path),
        model=model,  # pinned by the caller (env: AUTOPILOT_MODEL)
        effort=effort,  # pinned by the caller (default high); see ADR-028
        cli_path=cli_path,  # system CLI, not the stale bundled one (model pin drifts)
        setting_sources=["user", "project"],  # Loads CLAUDE.md + .claude/skills/
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=max_turns,
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
                "SKIP", "trailing-whitespace,end-of-file-fixer,mixed-line-ending"
            ),
            # 2026-08-30 audit: CLI default Bash timeout is 120 s (max 600 s).
            # awardybot tests/architecture alone takes 325-423 s on the VPS, so
            # tester agents saw their pytest killed at 5:01, waited on pgrep and
            # re-ran it — three 5-minute suites per tester, 82 of 180 min in the
            # FTR-1467 run that TIMEOUT_SECONDS then killed. Raising the run
            # timeout (23.08) could not help: the loop is inside the tool call.
            "BASH_DEFAULT_TIMEOUT_MS": os.environ.get("BASH_DEFAULT_TIMEOUT_MS", "900000"),
            "BASH_MAX_TIMEOUT_MS": os.environ.get("BASH_MAX_TIMEOUT_MS", "1800000"),
        },
        stderr=stderr_collector,
    )


async def consume(
    state: dict,
    prompt: str,
    options,
    *,
    log_dir: Path,
    project_name: str,
    ts_label: str,
    started_mono: float,
    started_at_iso: str,
    model: str,
    timeout_seconds: int,
) -> None:
    """Drain the SDK message stream into `state`.

    `state` is mutated in place so that a TimeoutError raised by asyncio.timeout
    still leaves the partial turn_count / cost_usd visible to run_task.
    """
    async with asyncio.timeout(timeout_seconds):
        async for message in query(prompt=prompt, options=options):
            msg_line = str(message)
            if len(msg_line) > 500:
                msg_line = msg_line[:500] + "..."
            logger.debug(msg_line)

            # TECH-198 Layer A: heartbeat on EVERY message (not just
            # AssistantMessage) so updated_at stays fresh during long
            # tool-execution phases between assistant turns.
            runner_heartbeat._write_heartbeat(
                log_dir,
                project_name,
                ts_label,
                state["turn_count"],
                int(time.monotonic() - started_mono),
                state["last_tool_name"],
                started_at_iso,
                model,
            )

            # A classifier decline arrives inside a normal HTTP 200, so it
            # never reaches an except-branch. Check every message: the raw
            # decline lands on the assistant turn or on the result, while
            # the fallback notice is a `system` message and is the only
            # carrier of the refusal category (_refusal_from_message).
            refusal_event = runner_refusal._refusal_from_message(message)
            if refusal_event is not None:
                state["refusal_events"].append(refusal_event)

            if isinstance(message, AssistantMessage):
                runner_result.apply_assistant_message(state, message)
            if isinstance(message, TaskNotificationMessage):
                runner_result.apply_task_notification(state, message)
            if isinstance(message, ResultMessage):
                runner_result.apply_result_message(state, message)

    # Fallback: use last assistant message if no result_text
    if not state["result_text"] and state["last_assistant_text"]:
        state["result_text"] = state["last_assistant_text"]


def handle_sdk_exception(
    exc: Exception,
    state: dict,
    stderr_lines: list,
    task: str,
    project_name: str,
    db,
    stderr_path: Path | None = None,
) -> None:
    """Map an SDK exception onto exit_code / result_text, honouring ADR-024.

    Dispatches CLIConnectionError, ProcessError and everything else the SDK raises
    without a dedicated class (including "Control request timeout: initialize").
    The one branch that is NOT a failure: an exception raised after a successful
    ResultMessage — the work is done and its metrics are already in `state`, so
    overriding exit_code would re-block a finished spec and pay for the retry
    (BUG-188).
    """
    if isinstance(exc, CLIConnectionError):
        logger.error("CLI connection error: %s", exc)
        state["exit_code"] = 2
        state["result_text"] = f"Connection error: {exc}"
        return

    if isinstance(exc, ProcessError):
        logger.error("Process error: %s", exc)
        state["exit_code"] = 3
        stderr = getattr(exc, "stderr", None)
        if stderr:
            state["result_text"] = f"Process error: {exc}\nSTDERR:\n{stderr}"
        elif stderr_lines:
            captured = "\n".join(stderr_lines[-100:])
            state["result_text"] = f"Process error: {exc}\nSTDERR (captured):\n{captured}"
        else:
            # Аудит 30.08.2026, причина 3: именно сюда приходили четыре прогона,
            # и «Check stderr output for details» отсылало ровно никуда. Теперь
            # отсылает к файлу — пустому или нет, но существующему.
            where = f" (stderr log: {stderr_path})" if stderr_path else ""
            state["result_text"] = f"Process error: {exc}{where}"
        return

    err_str = str(exc)
    stderr_from_exc = getattr(exc, "stderr", None)
    if stderr_from_exc:
        err_str = f"{err_str}\nSTDERR:\n{stderr_from_exc}"
    elif stderr_lines:
        # Layer 2: fall back to lines captured via SDK stderr callback
        captured = "\n".join(stderr_lines[-100:])  # last 100 lines
        err_str = f"{err_str}\nSTDERR (captured):\n{captured}"

    result_received = state["result_received"]
    result_is_error = state["result_is_error"]
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
        runner_result.log_post_result_error(
            exc,
            state,
            db=db,
            task=task,
            project_name=project_name,
            stderr_lines=stderr_lines,
        )
    elif "timeout" in err_str.lower():
        logger.error("SDK init timeout: %s", exc)
        state["exit_code"] = 124
        state["result_text"] = err_str
    else:
        logger.error("SDK error: %s", exc, exc_info=True)
        state["exit_code"] = 1
        state["result_text"] = err_str
