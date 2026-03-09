# Skill Creator — JSON Schemas

Reference schemas for inter-agent communication in skill-creator eval pipeline.

---

## evals.json

Test cases for skill evaluation. Lives in `{skill-path}/evals/evals.json`.

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "Create a function that validates email addresses",
      "expected_output": "A function with regex validation and edge case handling",
      "files": [],
      "assertions": [
        {
          "id": "has-regex",
          "text": "Output includes a regex pattern for email validation",
          "type": "deterministic"
        },
        {
          "id": "handles-edge-cases",
          "text": "Function handles empty strings, missing @, and unicode domains",
          "type": "quality"
        }
      ]
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill_name` | string | yes | Name matching skill's frontmatter |
| `evals[].id` | number | yes | Unique integer identifier |
| `evals[].prompt` | string | yes | Task prompt to execute |
| `evals[].expected_output` | string | yes | Human description of expected result |
| `evals[].files` | string[] | no | Input files needed for the eval |
| `evals[].assertions` | object[] | yes | Testable claims about the output |
| `assertions[].id` | string | yes | Slug identifier (kebab-case) |
| `assertions[].text` | string | yes | Natural language check |
| `assertions[].type` | string | yes | `"deterministic"` or `"quality"` |

**Assertion types:**
- `deterministic` — binary pass/fail, verifiable by grep/file check/exit code
- `quality` — requires LLM judgment (eval-judge scores 1-5)

---

## grading.json

Output from eval-judge (grader) after evaluating a single run.

```json
{
  "eval_id": 1,
  "skill_name": "my-skill",
  "pass": true,
  "score": 4.2,
  "assertions": [
    {
      "id": "has-regex",
      "pass": true,
      "evidence": "Found regex pattern on line 15: /^[a-zA-Z0-9._%+-]+@..."
    },
    {
      "id": "handles-edge-cases",
      "pass": true,
      "score": 4,
      "evidence": "Tests empty string, missing @, and .рф domain"
    }
  ],
  "rubric": {
    "content_quality": 4,
    "structural_quality": 5,
    "completeness": 4,
    "clarity": 4,
    "overall": 4.2
  },
  "tokens_used": 3400,
  "elapsed_ms": 12500,
  "improvement_suggestions": [
    "Add explicit test for double-dot in local part"
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `eval_id` | number | Matches evals.json id |
| `pass` | boolean | Overall pass (all deterministic assertions pass + quality score >= 3) |
| `score` | number | Average rubric score (1-5) |
| `assertions[]` | object[] | Per-assertion results with evidence |
| `rubric` | object | 5-dimension rubric scores |
| `tokens_used` | number | Total tokens consumed |
| `elapsed_ms` | number | Wall-clock duration |
| `improvement_suggestions` | string[] | Optional actionable suggestions |

---

## comparison.json

Output from comparator agent (blind A/B).

```json
{
  "winner": "B",
  "reasoning": "Output B provides more comprehensive edge case handling...",
  "scores": {
    "a": { "content_quality": 3, "structural_quality": 4, "overall": 7 },
    "b": { "content_quality": 5, "structural_quality": 4, "overall": 9 }
  },
  "expectations": [
    { "text": "Includes regex validation", "a_pass": true, "b_pass": true },
    { "text": "Handles unicode domains", "a_pass": false, "b_pass": true }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `winner` | string | `"A"`, `"B"`, or `"tie"` |
| `reasoning` | string | Explanation with specific examples |
| `scores.{a,b}.content_quality` | number | 1-5 task achievement |
| `scores.{a,b}.structural_quality` | number | 1-5 organization/clarity |
| `scores.{a,b}.overall` | number | 1-10 (content + structural averaged) |
| `expectations[]` | object[] | Per-expectation pass/fail for each output |

---

## benchmark.json

Aggregated results from multiple runs, output by `aggregate-benchmark.mjs`.

```json
{
  "skill_name": "my-skill",
  "iterations": 3,
  "timestamp": "2026-03-08T12:00:00Z",
  "summary": {
    "pass_rate": { "mean": 0.85, "stddev": 0.05, "min": 0.80, "max": 0.90 },
    "tokens": { "mean": 12400, "stddev": 1200, "min": 11000, "max": 14000 },
    "elapsed_ms": { "mean": 45000, "stddev": 8000, "min": 38000, "max": 55000 }
  },
  "per_assertion": [
    {
      "id": "has-regex",
      "pass_rate": 1.0,
      "note": "Always passes — non-discriminating"
    },
    {
      "id": "handles-edge-cases",
      "pass_rate": 0.67,
      "note": "High variance"
    }
  ],
  "per_eval": [
    {
      "eval_id": 1,
      "pass_rate": 0.67,
      "avg_score": 3.8
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `iterations` | number | How many runs were aggregated |
| `summary.{metric}` | object | Statistical summary (mean, stddev, min, max) |
| `per_assertion[]` | object[] | Per-assertion pass rate across all runs |
| `per_eval[]` | object[] | Per-eval pass rate and average score |

---

## timing.json

Timing data captured during eval execution.

```json
{
  "eval_id": 1,
  "iteration": 1,
  "executor": {
    "start": "2026-03-08T12:00:00Z",
    "end": "2026-03-08T12:00:35Z",
    "elapsed_ms": 35000,
    "tokens_input": 2100,
    "tokens_output": 1300
  },
  "grader": {
    "start": "2026-03-08T12:00:36Z",
    "end": "2026-03-08T12:00:48Z",
    "elapsed_ms": 12000,
    "tokens_input": 1800,
    "tokens_output": 600
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `eval_id` | number | Matches evals.json id |
| `iteration` | number | Benchmark iteration number |
| `{phase}.start/end` | string | ISO 8601 timestamps |
| `{phase}.elapsed_ms` | number | Wall-clock duration |
| `{phase}.tokens_*` | number | Token counts for input/output |
