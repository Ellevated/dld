#!/usr/bin/env python3
"""
Module: claude-runner
Role: Claude Code Agent SDK wrapper for programmatic task execution with Skills.
Uses: claude-agent-sdk, db.py
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
import sys
import time
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_TURNS = 120
TIMEOUT_SECONDS = 5400  # 90 min hard limit (R1 specs with 8+ tasks need >60m)

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("claude-runner")

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run_task(project_dir: str, task: str, skill: str) -> dict:
    """Run a Claude Code task with Skills via Agent SDK.

    Returns dict with exit_code, project, skill, task, cost_usd, turns.
    """
    project_path = Path(project_dir).resolve()
    project_name = project_path.name
    log_file = LOG_DIR / f"{project_name}-{time.strftime('%Y%m%d-%H%M%S')}.log"

    # Build prompt with skill prefix
    if task.startswith("/"):
        prompt = task
    else:
        prompt = f"/{skill} {task}"

    logger.info(
        "project=%s skill=%s prompt=%s cwd=%s",
        project_name,
        skill,
        prompt,
        project_path,
    )

    # Agent SDK options
    options = ClaudeAgentOptions(
        cwd=str(project_path),
        setting_sources=["user", "project"],  # Loads CLAUDE.md + .claude/skills/
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=MAX_TURNS,
        env={
            "PROJECT_DIR": str(project_path),
            "CLAUDE_PROJECT_DIR": str(project_path),
            "CLAUDE_CURRENT_SPEC_PATH": os.environ.get("CLAUDE_CURRENT_SPEC_PATH", ""),
            "ENABLE_PROMPT_CACHING_1H": os.environ.get("ENABLE_PROMPT_CACHING_1H", "1"),
        },
    )

    result_text = ""
    last_assistant_text = ""
    turns = 0
    cost_usd = 0.0
    exit_code = 0
    usage_metrics = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_1h_input_tokens": 0,
        "cache_creation_5m_input_tokens": 0,
    }
    model_usage: dict = {}

    try:
        async for message in query(prompt=prompt, options=options):
            # Log all messages
            msg_line = str(message)
            if len(msg_line) > 500:
                msg_line = msg_line[:500] + "..."
            logger.debug(msg_line)

            # Capture assistant text (last response before ResultMessage)
            if isinstance(message, AssistantMessage):
                text_parts = []
                for block in getattr(message, "content", []):
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                if text_parts:
                    last_assistant_text = "\n".join(text_parts)

            # Capture task completion summary (autopilot uses Agent tool → Tasks)
            if isinstance(message, TaskNotificationMessage):
                summary = getattr(message, "summary", "")
                if summary:
                    result_text = summary

            # Track final result
            if isinstance(message, ResultMessage):
                result_text = getattr(message, "result", "") or result_text
                turns = getattr(message, "num_turns", 0)
                cost_usd = getattr(message, "total_cost_usd", 0.0) or 0.0
                is_error = getattr(message, "is_error", False)
                if is_error:
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

    except asyncio.TimeoutError:
        logger.error("Timeout after %ds", TIMEOUT_SECONDS)
        exit_code = 124  # timeout exit code
        result_text = f"Timeout after {TIMEOUT_SECONDS}s"
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
        else:
            result_text = f"Process error: {e}"
    except Exception as e:
        # Catch SDK init timeouts ("Control request timeout: initialize")
        err_str = str(e)
        stderr = getattr(e, "stderr", None)
        if stderr:
            err_str = f"{err_str}\nSTDERR:\n{stderr}"
        if "timeout" in err_str.lower():
            logger.error("SDK init timeout: %s", e)
            exit_code = 124
        else:
            logger.error("SDK error: %s", e, exc_info=True)
            exit_code = 1
        result_text = err_str

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
        "input_tokens": usage_metrics["input_tokens"],
        "output_tokens": usage_metrics["output_tokens"],
        "cache_creation_input_tokens": usage_metrics["cache_creation_input_tokens"],
        "cache_creation_1h_input_tokens": usage_metrics["cache_creation_1h_input_tokens"],
        "cache_creation_5m_input_tokens": usage_metrics["cache_creation_5m_input_tokens"],
        "cache_read_input_tokens": usage_metrics["cache_read_input_tokens"],
        "cache_hit_rate": cache_hit_rate,
        "model_usage": model_usage,
        "result_preview": result_text[:1000] if result_text else "",
    }
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

    result = asyncio.run(
        asyncio.wait_for(
            run_task(project_dir, task, skill),
            timeout=TIMEOUT_SECONDS,
        )
    )

    # Output structured JSON (same contract as bash version)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
