#!/usr/bin/env python3
"""Prompt guard: suggests spark for complex tasks.

Soft block:
- Complex tasks without spark/autopilot

Detects patterns like:
- "create new feature", "implement X"
- "add endpoint", "write function"
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    approve_prompt,
    ask_tool,
    get_user_prompt,
    log_hook_error,
    read_hook_input,
)

# Max chars between keyword and target in complexity patterns
# Example: "implement a new user feature" — 12 chars between "implement" and "feature"
# 30 chars allows reasonable phrases while avoiding false positives on long text
KEYWORD_TARGET_GAP = 30

# Complexity indicators (keywords + explicit code requests)
COMPLEXITY_PATTERNS = [
    # Keywords + target (with gap limit to avoid false positives)
    rf"\b(implement|create|build|add|write)\b.{{0,{KEYWORD_TARGET_GAP}}}\b(feature|function|endpoint|api|service|handler)",
    r"\bnew\s+(feature|functionality)",
    # Direct code requests
    r"\bwrite\s+(a\s+)?(function|class|method|code|script)",
    r"\bcreate\s+(a\s+)?(endpoint|api|handler|service)",
]

# Skip if already using skills
SKILL_INDICATORS = [
    r"/spark",
    r"/autopilot",
    r"/audit",
    r"/plan",
    r"/council",
    r"\bspark\b",
    r"\bautopilot\b",
    r"\baudit\b",
]


def main() -> None:
    try:
        data = read_hook_input()
        prompt = get_user_prompt(data)
        prompt_lower = prompt.lower()

        # Skip if using skills
        for indicator in SKILL_INDICATORS:
            if re.search(indicator, prompt_lower):
                approve_prompt()
                return

        # Check for complexity patterns
        for pattern in COMPLEXITY_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                # Note: UserPromptSubmit doesn't support "ask", using ask_tool for UI prompt
                # Claude Code will show the message and require confirmation
                ask_tool(
                    "Complex task detected!\n\n"
                    "Consider using /spark for proper planning:\n"
                    "  /spark <task description>\n\n"
                    "Benefits:\n"
                    "  - Structured research (Exa)\n"
                    "  - Explicit file allowlist\n"
                    "  - Auto-handoff to autopilot\n"
                    "  - Deterministic workflow\n\n"
                    "Proceed without spark?"
                )
                return

        approve_prompt()
    except Exception as e:
        log_hook_error("prompt_guard", e)
        approve_prompt()


if __name__ == "__main__":
    main()
