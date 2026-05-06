#!/usr/bin/env python3
"""
Build lessons index from project archive.

Reads BUG tasks from ai/archive/ (or ai/features/ for closed BUGs),
classifies by root_cause_class, writes structured lessons to ai/lessons/.

Classification strategy:
  1. Keyword matching (fast, free). Confidence = number of matched keywords.
  2. If confidence < CONFIDENCE_MIN for domain OR root_cause → read the full
     spec and ask Claude Haiku to classify. Requires ANTHROPIC_API_KEY.
     Falls back to keyword result if API unavailable.

Usage:
    python3 scripts/build-lessons-index.py [--dry-run] [--domain DOMAIN] [--min-severity LEVEL]
    python3 scripts/build-lessons-index.py --dry-run --archive-dir ai/archive

Output:
    ai/lessons/<domain>/L-NNN.md   — individual lesson files
    ai/lessons/index.jsonl          — machine-readable index (append-only)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

CONFIDENCE_MIN = 2  # keyword hits below this → fall back to LLM


ROOT_CAUSE_TAXONOMY = {
    "money-precision": {
        "keywords": [
            "kopecks",
            "rub",
            "ruble",
            "float",
            "decimal",
            "amount",
            "price",
            "balance",
            "kopeck",
            "money",
            "currency",
        ],
        "severity": "critical",
    },
    "race-condition": {
        "keywords": [
            "concurrent",
            "race",
            "lock",
            "advisory",
            "simultaneous",
            "deadlock",
            "locking",
            "atomic",
            "transaction",
            "isolation",
        ],
        "severity": "critical",
    },
    "ssot-violation": {
        "keywords": [
            "ssot",
            "duplicate",
            "sync",
            "diverge",
            "inconsistent",
            "mismatch",
            "two sources",
            "multiple sources",
        ],
        "severity": "high",
    },
    "migration-drift": {
        "keywords": [
            "migration",
            "migrate",
            "schema",
            "column",
            "table",
            "alembic",
            "alter",
            "add column",
            "drop column",
        ],
        "severity": "critical",
    },
    "atomicity": {
        "keywords": [
            "partial",
            "rollback",
            "mid-flight",
            "halfway",
            "incomplete",
            "transaction",
            "multi-step",
        ],
        "severity": "high",
    },
    "idempotency": {
        "keywords": [
            "idempotent",
            "duplicate",
            "double",
            "twice",
            "replay",
            "retry",
            "webhook",
            "re-run",
        ],
        "severity": "high",
    },
    "boolean-trap": {
        "keywords": [
            "is_active",
            "is_deleted",
            "bool",
            "boolean",
            "flag",
            "status",
            "state",
            "nullable bool",
        ],
        "severity": "medium",
    },
    "fsm-deadlock": {
        "keywords": [
            "state machine",
            "fsm",
            "stuck",
            "transition",
            "slot",
            "pickup",
            "lifecycle",
            "status flow",
        ],
        "severity": "high",
    },
    "cross-layer-import": {
        "keywords": ["import", "circular", "layer", "domain", "api import", "shared", "direction"],
        "severity": "medium",
    },
    "pydantic-coercion": {
        "keywords": [
            "pydantic",
            "coerce",
            "coercion",
            "validation",
            "type cast",
            "string to int",
            "none to",
        ],
        "severity": "medium",
    },
    "case-mismatch": {
        "keywords": ["snake_case", "camelcase", "camel", "field name", "naming", "case"],
        "severity": "medium",
    },
    "null-safety": {
        "keywords": [
            "none",
            "null",
            "nullable",
            "missing",
            "undefined",
            "optional",
            "not found",
            "keyerror",
            "attributeerror",
        ],
        "severity": "medium",
    },
}

DOMAIN_PATTERNS = {
    "billing": ["billing", "balance", "payment", "invoice", "charge", "refund", "money", "kopeck"],
    "campaigns": ["campaign", "slot", "proof", "screenshot", "pickup", "substep", "buyer_task"],
    "buyer": ["buyer", "ugc", "creator", "identity", "onboarding", "merge"],
    "seller": ["seller", "brand", "advertiser", "offer"],
    "llm": ["llm", "gpt", "claude", "openai", "vision", "prompt", "tool_call", "agent"],
    "db": ["migration", "schema", "database", "sql", "postgres", "sqlite", "index", "table"],
    "security": ["auth", "token", "permission", "secret", "key", "csrf", "injection"],
    "api": ["api", "webhook", "endpoint", "handler", "route", "http"],
    "storage": ["file", "upload", "s3", "bucket", "media", "image", "storage"],
}

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1}

# Descriptions used in LLM prompt — human-readable, not keyword lists
ROOT_CAUSE_DESCRIPTIONS = {
    "money-precision": "Wrong type or unit for money (float instead of int kopecks, rub/rubles instead of kopecks)",
    "race-condition": "Concurrent writes without locking — two requests modify the same row simultaneously",
    "ssot-violation": "Same data stored in two places that can diverge; no single source of truth",
    "migration-drift": "DB schema migration out of sync with code; column exists in one but not the other",
    "atomicity": "Multi-step operation fails halfway, leaving data in partial state; missing transaction",
    "idempotency": "Same operation produces different results on retry; double-write, double-charge",
    "boolean-trap": "Ambiguous boolean field that can't represent all required states",
    "fsm-deadlock": "State machine gets stuck or makes illegal transition; slot/status lifecycle bug",
    "cross-layer-import": "Import direction violation — domain imports api, or circular imports",
    "pydantic-coercion": "Pydantic silently coerces a wrong type instead of raising a validation error",
    "case-mismatch": "snake_case vs camelCase mismatch between DB field and code/API field",
    "null-safety": "Unhandled None/null — missing check crashes at runtime",
}


def detect_domain(text: str) -> tuple[str, int]:
    """Returns (domain, confidence_score)."""
    text_lower = text.lower()
    scores = {}
    for domain, keywords in DOMAIN_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return "general", 0
    best = max(scores, key=scores.get)
    return best, scores[best]


def classify_root_cause(text: str) -> tuple[str, str, int]:
    """Returns (root_cause_class, severity, confidence_score)."""
    text_lower = text.lower()
    scores = {}
    for cls, meta in ROOT_CAUSE_TAXONOMY.items():
        score = sum(1 for kw in meta["keywords"] if kw in text_lower)
        if score > 0:
            scores[cls] = (score, meta["severity"])

    if not scores:
        return "general", "medium", 0

    best = max(scores, key=lambda c: (scores[c][0], SEVERITY_ORDER[scores[c][1]]))
    return best, scores[best][1], scores[best][0]


def classify_with_llm(text: str, task_id: str) -> dict | None:
    """
    Read the full spec with Claude Haiku and extract structured classification.
    Returns dict with domain/root_cause_class/prevention_rule/severity/keywords,
    or None if API unavailable.
    """
    try:
        import anthropic
    except ImportError:
        print(f"  [LLM] anthropic not installed — pip install anthropic", file=sys.stderr)
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"  [LLM] ANTHROPIC_API_KEY not set — skipping LLM fallback", file=sys.stderr)
        return None

    taxonomy_desc = "\n".join(f'  "{cls}": {desc}' for cls, desc in ROOT_CAUSE_DESCRIPTIONS.items())
    domain_list = ", ".join(DOMAIN_PATTERNS.keys()) + ", general"

    prompt = f"""You are classifying a bug report for a knowledge base.

<bug_spec>
{text[:4000]}
</bug_spec>

Task ID: {task_id}

Classify this bug using ONLY the taxonomy below. Read the spec carefully — title alone is not enough.

Root cause classes:
{taxonomy_desc}

Available domains: {domain_list}

Respond with valid JSON only, no commentary:
{{
  "domain": "<domain from list above>",
  "root_cause_class": "<class from taxonomy above>",
  "prevention_rule": "<one concrete actionable sentence — what to do differently next time>",
  "severity": "<critical|high|medium>",
  "keywords": ["<3-6 specific terms from this bug>"]
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        # Validate required fields
        required = {"domain", "root_cause_class", "prevention_rule", "severity", "keywords"}
        if not required.issubset(result.keys()):
            raise ValueError(f"Missing fields: {required - result.keys()}")
        if (
            result["root_cause_class"] not in ROOT_CAUSE_DESCRIPTIONS
            and result["root_cause_class"] != "general"
        ):
            result["root_cause_class"] = "general"
        if result["severity"] not in SEVERITY_ORDER:
            result["severity"] = "medium"
        return result
    except Exception as e:
        print(f"  [LLM] Failed for {task_id}: {e}", file=sys.stderr)
        return None


def extract_prevention_rule(text: str, root_cause: str) -> str:
    """Try to extract a one-line prevention rule from task body."""
    for pattern in [
        r"(?:resolution|fix|solution|prevent|правило|решение)[:\s]+(.+?)(?:\n|$)",
        r"(?:use|always|never|must|should|использовать|никогда)[^\n]{10,}(?:\n|$)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            rule = m.group(0 if re.search(r"use\|always", pattern) else 1).strip()
            if len(rule) > 10:
                return rule[:200]

    defaults = {
        "money-precision": "Использовать int (kopecks), никогда float/Decimal для денег",
        "race-condition": "Использовать advisory lock или transaction isolation перед concurrent writes",
        "ssot-violation": "Один источник правды — не хранить одно и то же в двух местах",
        "migration-drift": "Миграция и код меняются в одном PR, CI применяет миграцию",
        "atomicity": "Все шаги — в одной транзакции или с компенсирующей операцией",
        "idempotency": "Проверять на duplicate перед записью, использовать upsert",
        "fsm-deadlock": "Описать все легальные переходы FSM явно, запретить остальные",
        "general": "Добавить тест на граничный случай",
    }
    return defaults.get(root_cause, defaults["general"])


def parse_task_file(path: Path) -> dict | None:
    """Parse a task spec file (BUG- prefix expected)."""
    text = path.read_text(encoding="utf-8")
    name = path.stem  # e.g. BUG-350-2026-02-15-kopecks-migration

    # Only process BUG tasks
    if not re.match(r"BUG-\d+", name, re.IGNORECASE):
        return None

    task_id = re.match(r"(BUG-\d+)", name, re.IGNORECASE).group(1).upper()

    # Extract title from first H1 or filename
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else name

    domain, domain_conf = detect_domain(text)
    root_cause, severity, rc_conf = classify_root_cause(text)

    method = "kw"  # classification method used

    # Fall back to LLM when keyword confidence is low
    if domain_conf < CONFIDENCE_MIN or rc_conf < CONFIDENCE_MIN:
        llm_result = classify_with_llm(text, task_id)
        if llm_result:
            domain = llm_result["domain"]
            root_cause = llm_result["root_cause_class"]
            severity = llm_result["severity"]
            prevention = llm_result["prevention_rule"]
            keywords = llm_result["keywords"][:8]
            method = "llm"
        else:
            # LLM unavailable — keep keyword result, note low confidence
            prevention = extract_prevention_rule(text, root_cause)
            keywords = [
                kw
                for kw in ROOT_CAUSE_TAXONOMY.get(root_cause, {}).get("keywords", [])
                if kw in text.lower()
            ][:8] or root_cause.split("-")
            method = "kw-low"
    else:
        prevention = extract_prevention_rule(text, root_cause)
        keywords = [
            kw
            for kw in ROOT_CAUSE_TAXONOMY.get(root_cause, {}).get("keywords", [])
            if kw in text.lower()
        ][:8] or root_cause.split("-")

    return {
        "task_id": task_id,
        "title": title[:100],
        "domain": domain,
        "root_cause_class": root_cause,
        "severity": severity,
        "prevention_rule": prevention,
        "keywords": keywords,
        "_method": method,  # for logging only, not written to lesson
    }


def next_lesson_id(lessons_dir: Path) -> str:
    existing = [f.stem for f in lessons_dir.glob("L-*.md") if re.match(r"L-\d+", f.stem)]
    nums = [int(re.search(r"\d+", s).group()) for s in existing if re.search(r"\d+", s)]
    n = max(nums, default=0) + 1
    return f"L-{n:03d}"


def write_lesson(lessons_dir: Path, lesson_id: str, data: dict, dry_run: bool) -> Path:
    domain_dir = lessons_dir / data["domain"]
    lesson_file = domain_dir / f"{lesson_id}.md"

    content = f"""---
id: {lesson_id}
domain: {data["domain"]}
root_cause_class: {data["root_cause_class"]}
severity: {data["severity"]}
created: {__import__("datetime").date.today()}
occurrence_count: 1
related: [{data["task_id"]}]
---

# {data["root_cause_class"]}: {data["title"][:60]}

## Prevention Rule
{data["prevention_rule"]}

## Context
Extracted from {data["task_id"]}.

## Keywords
{", ".join(data["keywords"])}
"""
    if not dry_run:
        domain_dir.mkdir(parents=True, exist_ok=True)
        lesson_file.write_text(content, encoding="utf-8")

    return lesson_file


def update_index(index_file: Path, entry: dict, dry_run: bool):
    line = json.dumps(entry, ensure_ascii=False)
    if not dry_run:
        with index_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(description="Build ai/lessons/ from archive")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--domain", help="Process only this domain")
    parser.add_argument("--min-severity", choices=["critical", "high", "medium"], default="medium")
    parser.add_argument("--archive-dir", default="ai/archive", help="Source directory")
    parser.add_argument("--lessons-dir", default="ai/lessons", help="Output directory")
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    lessons_dir = Path(args.lessons_dir)
    index_file = lessons_dir / "index.jsonl"

    if not archive_dir.exists():
        print(f"Archive directory not found: {archive_dir}", file=sys.stderr)
        print("Create ai/archive/ with BUG task spec files first.")
        sys.exit(0)  # Not an error — project may not have archive yet

    min_sev = SEVERITY_ORDER[args.min_severity]
    processed = skipped = written = 0
    counts = {"kw": 0, "llm": 0, "kw-low": 0}

    for path in sorted(archive_dir.glob("*.md")):
        data = parse_task_file(path)
        if data is None:
            skipped += 1
            continue

        processed += 1
        method = data.pop("_method", "kw")

        if SEVERITY_ORDER[data["severity"]] < min_sev:
            skipped += 1
            continue

        if args.domain and data["domain"] != args.domain:
            skipped += 1
            continue

        domain_dir = lessons_dir / data["domain"]
        lesson_id = next_lesson_id(domain_dir)

        write_lesson(lessons_dir, lesson_id, data, args.dry_run)
        index_entry = {
            "id": lesson_id,
            "domain": data["domain"],
            "root_cause_class": data["root_cause_class"],
            "prevention_rule": data["prevention_rule"],
            "keywords": data["keywords"],
            "severity": data["severity"],
            "related": [data["task_id"]],
            "created": str(__import__("datetime").date.today()),
            "occurrence_count": 1,
        }
        update_index(index_file, index_entry, args.dry_run)

        action = "DRY-RUN" if args.dry_run else "WRITTEN"
        tag = {"kw": "KW ", "llm": "LLM", "kw-low": "LOW"}.get(method, "???")
        print(
            f"[{action}][{tag}] {lesson_id} {data['domain']}/{data['root_cause_class']} ← {data['task_id']}"
        )
        counts[method] = counts.get(method, 0) + 1
        written += 1

    verb = "would be written" if args.dry_run else "written"
    print(f"\nDone: {written} lessons {verb}, {skipped} skipped, {processed} processed")
    print(
        f"  KW (confident): {counts['kw']}  |  LLM (fallback): {counts['llm']}  |  LOW (uncertain, no LLM): {counts['kw-low']}"
    )


if __name__ == "__main__":
    main()
