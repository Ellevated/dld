"""
Module: runner_models
Role: which models one autopilot run is supposed to use — the main loop's default,
      what the CLI must resolve frontmatter aliases to, the set model-drift telemetry
      checks against, and the canonical form of a reported model id.
Uses: os, re

Used by:
  - claude-runner.py (MODEL default, ALIAS_PINS)
  - runner_result.py (_EXPECTED_MODELS, the drift check)
  - runner_cost.py (price lookup by canonical id)
"""

import os
import re

# The main loop's model when AUTOPILOT_MODEL is unset. claude-runner and the expected
# set below read the same env name with this default, so they cannot disagree.
DEFAULT_MAIN_MODEL = "claude-opus-5"

# Suffixes that are not part of the model's identity: the context-window tag newer
# CLIs append to model_usage keys (`claude-opus-5[1m]`, seen on 2.1.280) and a build
# date (`claude-haiku-4-5-20251001`). A version number IS part of the identity, which
# is why matching by prefix was wrong: `claude-opus-5-5` starts with `claude-opus-5`.
_WINDOW_TAG = re.compile(r"\[[^\]]*\]$")
_BUILD_DATE = re.compile(r"-\d{8}$")


def canonical_model(model: str) -> str:
    """Strip the suffixes that do not change which model ran; keep the version."""
    name = _WINDOW_TAG.sub("", (model or "").strip())
    return _BUILD_DATE.sub("", name)


def alias_pins(main_model: str, env=None) -> dict:
    """What the CLI must resolve `opus` / `sonnet` / `haiku` to for this run.

    Frontmatter says `model: opus`, and the CLI resolves that alias to whatever its
    own release calls current — CLI 2.1.280 already answers `claude-opus-5-5` while
    the main loop is pinned to `claude-opus-5`. Passing these through the run's env
    holds every subagent on the main loop's generation until someone moves the pin on
    purpose. The opus alias follows an Opus main loop, so moving AUTOPILOT_MODEL
    moves the whole run; each variable can still be set on its own.
    """
    env = os.environ if env is None else env
    opus = main_model if main_model.startswith("claude-opus") else DEFAULT_MAIN_MODEL
    defaults = {
        "ANTHROPIC_DEFAULT_OPUS_MODEL": opus,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001",
    }
    return {name: env.get(name) or value for name, value in defaults.items()}


def expected_models(env=None) -> frozenset:
    """The main loop plus the three pinned aliases, unless AUTOPILOT_EXPECTED_MODELS
    names the set explicitly."""
    env = os.environ if env is None else env
    main = env.get("AUTOPILOT_MODEL", DEFAULT_MAIN_MODEL)
    default = ",".join(sorted({main, *alias_pins(main, env).values()}))
    return frozenset(
        m.strip() for m in env.get("AUTOPILOT_EXPECTED_MODELS", default).split(",") if m.strip()
    )
