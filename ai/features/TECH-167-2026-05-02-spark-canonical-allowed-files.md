---
id: TECH-167
type: TECH
status: done
priority: P0
risk: R1
created: 2026-05-02
---

# TECH-167 — Spark canonical `## Allowed Files` section + emit-time linter

**Status:** done
**Priority:** P0
**Risk:** R1 (cross-cutting — затрагивает все будущие спеки во всех проектах)

---

## Problem

Парсер callback'а (TECH-166) ловит **80%** спек, остальные 20% демоутятся в `blocked` ложно из-за format drift:

| Вариант | Где встречается | Парсер ловит |
|---|---|---|
| `## Allowed Files` | большинство | ✓ |
| `## Allowed Files (whitelist|canonical|STRICT|...)` | awardybot, gipotenuza | ✓ (после TECH-166 hotfix) |
| `## Updated Allowed Files` | gipotenuza | ✓ |
| `## Files Allowed to Modify` | dowry, plpilot | ✓ |
| `## Files` | FTR-846 awardybot | ✗ |
| `## Affected Files` | TECH-840 awardybot | ✗ |
| `### Allowed Files (whitelist)` (H3) | FTR-851 awardybot | ✗ |
| Секции нет вообще | ~170 спек legacy | ✗ |
| Paths внутри ` ``` ` fenced без backticks | FTR-882 awardybot | ✗ (regex теряет paths) |

Решать regex-погоней — анти-паттерн, новые формы появятся завтра. **Корень: Spark не имеет жёсткого контракта на формат allowlist'а.**

---

## Goal

1. **Canonical format** — один-единственный шаблон секции, обязательный для всех новых спек:

   ```markdown
   ## Allowed Files

   <!-- callback-allowlist v1: backticked paths only, one per row -->

   - `path/to/file1.py`
   - `path/to/file2.sql`
   - `tests/path/to/test.py`
   ```

   Маркер `callback-allowlist v1` нужен для версионирования формата (v2 если когда-то поменяем).

2. **Spark emit-time linter** — pre-write hook в spark facilitator:
   - Section heading exactly `## Allowed Files` (case-sensitive, single H2, no suffix).
   - Marker `<!-- callback-allowlist v1 -->` присутствует.
   - Минимум 1 backticked path в bullet list внутри секции.
   - Каждая bullet строка — формат `` - `path` `` (опц. комментарий после).
   - При нарушении — **fail Spark output**, не пишем спеку, escalate в Telegram.

3. **Callback парсер v2** — переключаемся на маркер `<!-- callback-allowlist v1 -->`. Если маркера нет → degrade-closed (как сейчас). Если маркер есть → парсим строго: bullet + backtick. Никаких heading-вариантов больше.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `.claude/skills/spark/SKILL.md`
- `.claude/skills/spark/feature-mode.md`
- `.claude/skills/spark/completion.md`
- `.claude/agents/spark/facilitator.md`
- `template/.claude/skills/spark/SKILL.md`
- `template/.claude/skills/spark/feature-mode.md`
- `template/.claude/skills/spark/completion.md`
- `scripts/vps/callback.py`
- `tests/unit/test_callback_allowlist_v1.py`

---

## Tasks

1. **Spec template update**: в `feature-mode.md` (и template-mirror) — раздел Output Format добавить canonical block с маркером и пример.
2. **Spark facilitator pre-write check**: regex-валидатор в facilitator.md, fail с понятным сообщением.
3. **Spark `completion.md`**: явное правило "не писать spec файл если linter не прошёл — escalate в Telegram".
4. **Callback parser v2**: новые `_ALLOWED_FILES_V1_MARKER_RE`, `_ALLOWED_FILES_BULLET_RE`. Старые heading-вариантные regex остаются как fallback для legacy специй (degrade-open для них) — НО для спек с маркером v1 — strict mode, no fallback.
5. **Tests**: парсинг canonical + invalid форматов + legacy без маркера.
6. **Документация в CLAUDE.md** (DLD root + template): краткая выжимка формата для людей.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Parser v2 извлекает paths из канонической секции с маркером |
| EC-2 | deterministic | Parser v2 для legacy спеки без маркера → fallback на старую логику |
| EC-3 | deterministic | Parser v2 для спеки с маркером но broken bullets → degrade-closed |
| EC-4 | integration | Spark facilitator валит output без маркера/секции |
| EC-5 | integration | Spark facilitator валит output с пустой секцией |
| EC-6 | integration | Spark facilitator пропускает корректную секцию |
| EC-7 | deterministic | Existing спеки awardybot/dowry/etc. парсятся v2 как и раньше (regression) |

---

## Implementation Plan

> **Convention:** all paths below are relative to worktree root
> `/home/dld/projects/dld/.worktrees/TECH-167/`. Coder must use absolute paths
> in tool calls.

### Drift Notes (Phase 1.5)

- `callback.py` line numbers in spec match HEAD: `_ALLOWED_FILE_EXT_RE` at L560,
  `_ALLOWED_FILES_HEADING_RE` at L567, `_NEXT_H2_RE` at L571,
  `_parse_allowed_files` at L574, `_has_implementation_commits` at L622.
- Existing tests reference `callback._append_blocked_reason`, but callback.py
  HEAD has `_apply_blocked_reason`. Test file
  `tests/unit/test_callback_implementation_guard.py` already exists for
  TECH-166 — Task 4 below adds an alias to keep it green (do NOT rename
  the old function, just expose `_append_blocked_reason = _apply_blocked_reason`
  at module scope).
- `template/.claude/skills/spark/{SKILL.md, feature-mode.md, completion.md}`
  exist and are byte-identical to root copies for relevant sections — the
  spark skill files are in the auto-sync set.
- No `tests/unit/__init__.py`, no `conftest.py` in tree; tests in
  `tests/unit/test_callback_implementation_guard.py` already use the same
  `sys.path.insert` shim pattern → reuse it in the new test file.

---

### Task 1 — Add canonical Allowed Files block to Spark Spec Template (root + template)

**Goal:** make the `## Allowed Files` section in the Phase 5 spec template a
canonical block with marker + bullet+backtick rule, so every new spec is
parseable by callback v2.

**Files:**
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/.claude/skills/spark/feature-mode.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/template/.claude/skills/spark/feature-mode.md`

**Replacement target (both files, identical text):**
Lines 366–378 of `.claude/skills/spark/feature-mode.md` (and matching block in
template) currently read:

```markdown
---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `path/to/file1.py` — reason
2. `path/to/file2.py` — reason
3. `path/to/file3.py` — reason

**New files allowed:**
- `path/to/new_file.py` — reason

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---
```

**Replace with (verbatim):**

```markdown
---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row -->

ONLY the files listed below may be modified during implementation.

- `path/to/file1.py` — reason (modify)
- `path/to/file2.py` — reason (modify)
- `path/to/new_file.py` — reason (NEW)
- `tests/path/to/test_file.py` — reason (NEW)

**Format contract (enforced by Spark linter — see Phase 5.5):**
- Heading is exactly `## Allowed Files` (case-sensitive H2, no suffix, no
  qualifier in parentheses).
- The HTML comment marker `<!-- callback-allowlist v1 -->` (or
  `<!-- callback-allowlist v1: ... -->`) is REQUIRED and must appear
  before the first path.
- Each path lives on its own bullet `- ` line, wrapped in single backticks.
  Optional free-text after the closing backtick is allowed.
- No fenced code blocks, no nested lists, no tables. One path per line.
- Minimum one path. Empty Allowed Files = block the spec (Spark refuses to
  write).

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---
```

**Acceptance:**
- `grep -nE '^## Allowed Files\b' .claude/skills/spark/feature-mode.md` → exactly 1 match.
- `grep -n 'callback-allowlist v1' .claude/skills/spark/feature-mode.md` → exactly 1 match.
- Same for `template/.claude/skills/spark/feature-mode.md`.
- `diff .claude/skills/spark/feature-mode.md template/.claude/skills/spark/feature-mode.md`
  must remain empty after this task (the two files are kept in sync).

---

### Task 2 — Add Phase 5.5 (Allowlist Linter) to feature-mode.md

**Goal:** introduce a HARD-GATE between Phase 5 (WRITE) and Phase 6 (VALIDATE)
that runs a deterministic linter against the freshly-written `## Allowed Files`
section. Failure → unlink spec file, escalate, do NOT proceed.

**Files:**
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/.claude/skills/spark/feature-mode.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/template/.claude/skills/spark/feature-mode.md`

**Insertion point:** immediately AFTER the existing Phase 5 `<HARD-GATE>`
block (currently L593–L600 of root file, ending with `</HARD-GATE>` followed
by a `---` divider). Insert BEFORE the `## Phase 6: VALIDATE` heading.

**Insert verbatim (both files identical):**

```markdown
---

## Phase 5.5: ALLOWLIST LINTER (Pre-Validate Hard Gate)

After Write, before Validate. Deterministic check against the spec's
`## Allowed Files` section. ANY failure here → DELETE spec file, escalate
to Telegram with the exact error code, do NOT advance to Phase 6.

### Linter rules (regex SSOT — must match callback.py v2)

```
HEADING_RE   = ^##[ \t]+Allowed Files[ \t]*$            (case-sensitive, exact)
MARKER_RE    = <!--\s*callback-allowlist\s+v1\b[^>]*-->
BULLET_RE    = ^-[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$
SECTION_END  = ^##[ \t]+\S          (next H2 heading)
```

### Algorithm

1. Read the just-written spec file.
2. Find the FIRST line matching `HEADING_RE`. If absent → fail
   `ALLOWLIST_E001_NO_HEADING`.
3. Forbid duplicates: if more than one line matches `HEADING_RE` → fail
   `ALLOWLIST_E002_DUPLICATE_HEADING`.
4. Slice section = lines after heading until first `SECTION_END` (or EOF).
5. Search section for `MARKER_RE`. Absent → fail `ALLOWLIST_E003_NO_MARKER`.
6. Iterate non-blank, non-comment lines in section. For each line:
   - If line starts with `- ` (bullet) and does NOT match `BULLET_RE` → fail
     `ALLOWLIST_E004_BAD_BULLET` with offending line.
   - Lines that are not bullets and not the marker comment and not free
     prose paragraphs (heuristic: contain a backtick) → fail
     `ALLOWLIST_E005_PATH_OUTSIDE_BULLET` (catches "paths in fenced code
     blocks" anti-pattern).
7. Collect all paths captured by `BULLET_RE`. If count == 0 → fail
   `ALLOWLIST_E006_EMPTY_LIST`.

### On failure

1. `Bash`: `rm -f ai/features/{TASK_ID}-*.md` (delete the bad spec).
2. Roll back the backlog edit if it was already added (Edit tool to remove
   the row).
3. Set `state.json: write = failed, error = <code>`.
4. Return JSON to caller:

```yaml
status: blocked
error_code: ALLOWLIST_E00X
error_message: "Spark allowlist linter rejected spec: <human description>"
remediation: "Re-run /spark and follow the canonical Allowed Files format
              documented in feature-mode.md Phase 5.5."
```

5. Telegram notification (via `result_preview`):
   `Spark linter blocked spec — <error_code>. Manual fix needed.`

### On success

- state.json: `lint = done, allowlist_paths = [<list>]`.
- Proceed to Phase 6.

<HARD-GATE>
DO NOT proceed to Phase 6 until:
- [ ] Phase 5.5 linter run on freshly-written spec file
- [ ] Linter exit = success (no E001..E006)
- [ ] state.json updated: lint = done, allowlist_paths = [<paths>]
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "the section looks fine to me"
</HARD-GATE>

---
```

**Acceptance:**
- `grep -c '^## Phase 5.5: ALLOWLIST LINTER' .claude/skills/spark/feature-mode.md` → 1.
- `grep -c 'ALLOWLIST_E00' .claude/skills/spark/feature-mode.md` → ≥ 6 (E001..E006 + the example block).
- File sync diff with template still empty.

---

### Task 3 — Wire linter into Spark Facilitator + Completion + SKILL.md

**Goal:** make the facilitator agent call the Phase 5.5 linter, and the
completion logic refuse to write/commit on linter failure. Also surface the
contract in the top-level SKILL.md.

**Files:**
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/.claude/agents/spark/facilitator.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/.claude/skills/spark/completion.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/template/.claude/skills/spark/completion.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/.claude/skills/spark/SKILL.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/template/.claude/skills/spark/SKILL.md`

**Change A — facilitator.md (root only — agent file is not in template/):**

Locate L191–L202 (the `## Phase 5: WRITE (Spec by Template)` section, ending
just before `## Phase 6: VALIDATE (5 Structural Gates)`).

After the existing Phase 5 block, INSERT a new section verbatim:

```markdown
## Phase 5.5: ALLOWLIST LINTER (Pre-Validate Hard Gate)

After Phase 5 writes the spec — BEFORE Phase 6 — run the deterministic
linter described in `feature-mode.md` Phase 5.5.

### What you do

1. Read the freshly written spec (`Read` tool).
2. Apply the four regexes from `feature-mode.md` Phase 5.5:
   - `HEADING_RE = ^##[ \t]+Allowed Files[ \t]*$`
   - `MARKER_RE = <!--\s*callback-allowlist\s+v1\b[^>]*-->`
   - `BULLET_RE = ^-[ \t]+\`([^\s\`\n]+\.[A-Za-z][\w-]*)\`(?:[ \t]+.*)?$`
   - section ends at next `^##[ \t]+\S` heading.
3. Map any failure to error codes E001..E006 (see feature-mode.md).
4. On failure: `Bash rm -f ai/features/{TASK_ID}-*.md`, undo backlog row,
   set `state.json: lint = failed`, return:
   `status: blocked, error_code: ALLOWLIST_E00X`.
5. On success: `state.json: lint = done`, proceed to Phase 6.

### What you DO NOT do

- Do NOT silently auto-fix the spec. Founder must understand why Spark refused.
- Do NOT proceed to Phase 6 with a failing linter. The sole exit on failure
  is `status: blocked`.
- Do NOT push the bad spec — Phase 5.5 runs BEFORE the auto-commit in Phase 8.
```

Then UPDATE the responsibilities list at L14–L22 — replace existing line:

```markdown
6. **VALIDATE** — Run 5 structural validation gates (Phase 6)
```

with:

```markdown
6. **LINT** — Run Allowlist Linter on `## Allowed Files` (Phase 5.5)
7. **VALIDATE** — Run 6 structural validation gates (Phase 6)
8. **REFLECT** — Generate LOCAL + UPSTREAM + PROCESS signals (Phase 7)
9. **COMPLETION** — ID + backlog + commit + handoff (Phase 8)
```

(also DELETE the now-duplicated original lines 21 and 22 referring to
REFLECT and COMPLETION as 7 and 8.)

**Change B — completion.md (both root + template, identical edits):**

Locate the "Pre-Completion Checklist (BLOCKING)" block (root L37–L51,
template same). After item 5 (`Status = queued`) and before item 6 (`Function
overlap check`), INSERT a new item:

```markdown
6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns 1 line, and `## Allowed Files` heading exists exactly once
```

…and renumber the existing items 6 and 7 to 7 and 8.

Then INSERT a new section AFTER "Auto-Commit + Push" and BEFORE
"Completion — No Handoff" (after root L218 / template L218):

```markdown
---

## Linter Failure → Do Not Commit (MANDATORY)

If Phase 5.5 (Allowlist Linter) returned a failure code (E001..E006):

1. Spec file MUST already be deleted by facilitator (if not — delete now via
   `rm -f ai/features/{TASK_ID}*.md`).
2. Backlog row for `{TASK_ID}` MUST be removed (use Edit tool).
3. **DO NOT run `git add` / `git commit` / `git push`** for this task.
4. Return final status:
   ```yaml
   status: blocked
   spec_path: null
   spec_status: not_created
   pushed: false
   error_code: ALLOWLIST_E00X
   error_message: "<human-readable description>"
   ```
5. The orchestrator/operator surfaces the error to the founder via Telegram —
   no auto-recovery.

⛔ Pushing a spec that fails the linter defeats the whole point of TECH-167.
The callback parser will reject it on the autopilot side, and the founder will
have to debug the same drift again.
```

**Change C — SKILL.md (both root + template, identical edits):**

Locate the "Principles" list. After existing item 7
(`**Explicit Allowlist** — Spec must list ONLY files that can be modified`),
REPLACE it with:

```markdown
7. **Explicit Allowlist (Canonical Format)** — `## Allowed Files` section uses canonical block: H2 heading + `<!-- callback-allowlist v1 -->` marker + bullet+backtick paths. Phase 5.5 linter enforces this — see `feature-mode.md`.
```

**Acceptance:**
- `grep -c '^## Phase 5.5: ALLOWLIST LINTER' .claude/agents/spark/facilitator.md` → 1.
- `grep -c 'Allowlist Linter passed' .claude/skills/spark/completion.md` → 1.
- `grep -c 'Linter Failure → Do Not Commit' .claude/skills/spark/completion.md` → 1.
- `diff .claude/skills/spark/completion.md template/.claude/skills/spark/completion.md` → empty.
- `diff .claude/skills/spark/SKILL.md template/.claude/skills/spark/SKILL.md` → empty.
- `grep -c 'callback-allowlist v1' .claude/skills/spark/SKILL.md` → 1.

---

### Task 4 — Implement v1 marker parser in callback.py (additive, fallback-safe)

**Goal:** add a v2 path that prefers the canonical format when the marker is
present (strict mode), and keeps the existing heading-variant regex as
fallback for legacy specs without the marker. Also add the alias for
existing tests.

**Files:**
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/scripts/vps/callback.py`

**Edit A — add new module-level constants.**

Locate the comment block "TECH-166: Implementation guard helpers" at L554
followed by `_ALLOWED_FILE_EXT_RE` (L560), `_ALLOWED_FILES_HEADING_RE` (L567),
`_NEXT_H2_RE` (L571).

REPLACE the comment header at L554 and the constants L556–L571 with:

```python
# --- TECH-166 / TECH-167: Implementation guard helpers ----------------------

# Backticked path-shape: anything between backticks with a dot extension.
# Drops the extension whitelist — Go (.go), Astro (.astro), Terraform (.tf),
# Dockerfile, .env.example, etc. are all valid project files. False positives
# like `foo.bar` are harmless: git log finds no commits and they're ignored.
_ALLOWED_FILE_EXT_RE = re.compile(r"`([^\s`\n]+\.[a-zA-Z][\w-]*)`")

# --- TECH-167 v1 canonical format -------------------------------------------
# Strict heading: "## Allowed Files" (case-sensitive, no suffix, no qualifier).
_ALLOWED_FILES_V1_HEADING_RE = re.compile(r"^##[ \t]+Allowed Files[ \t]*$")
# Marker comment that opts a spec into v1 strict parsing.
_ALLOWED_FILES_V1_MARKER_RE = re.compile(
    r"<!--\s*callback-allowlist\s+v1\b[^>]*-->"
)
# Canonical bullet: "- `path/with.ext` optional trailing prose".
_ALLOWED_FILES_V1_BULLET_RE = re.compile(
    r"^-[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$"
)

# --- TECH-166 legacy fallback (kept for specs without the v1 marker) --------
# Heading variants seen across DLD projects (case-insensitive):
#   ## Allowed Files
#   ## Allowed Files (whitelist|canonical|STRICT|...)
#   ## Updated Allowed Files
#   ## Files Allowed to Modify
_ALLOWED_FILES_HEADING_RE = re.compile(
    r"^##\s+(?:(?:Updated\s+)?Allowed\s+Files\b|Files\s+Allowed\s+to\s+Modify\b)",
    re.IGNORECASE,
)
_NEXT_H2_RE = re.compile(r"^##\s+\S")
```

**Edit B — split parser into `_v1` and `_legacy`, dispatch in `_parse_allowed_files`.**

REPLACE the existing `_parse_allowed_files` function (L574–L603) with:

```python
def _parse_allowed_files_v1(spec_text: str) -> list[str] | None:
    """Strict canonical v1 parser. Returns:

        list[str]: ≥1 paths (success).
        []        : marker present but ZERO valid bullets — degrade-closed.
        None      : v1 marker not present (caller should try legacy fallback).
    """
    lines = spec_text.splitlines()

    # Locate the canonical heading (must be EXACT — case-sensitive, no suffix).
    heading_idxs = [i for i, ln in enumerate(lines)
                    if _ALLOWED_FILES_V1_HEADING_RE.match(ln)]
    if not heading_idxs:
        return None  # caller falls back to legacy
    # Use the first canonical heading; section ends at next H2.
    start = heading_idxs[0] + 1
    end = len(lines)
    for j in range(start, len(lines)):
        if _NEXT_H2_RE.match(lines[j]):
            end = j
            break
    section = lines[start:end]
    section_text = "\n".join(section)

    # Marker is the v1 opt-in. Without it, spec is legacy; defer.
    if not _ALLOWED_FILES_V1_MARKER_RE.search(section_text):
        return None

    # Strict mode: only canonical bullets count. No fenced blocks, no
    # backtick-paths outside bullets, no fallback to _ALLOWED_FILE_EXT_RE.
    paths: list[str] = []
    for ln in section:
        m = _ALLOWED_FILES_V1_BULLET_RE.match(ln)
        if m:
            paths.append(m.group(1))
    # Empty list with marker present = degrade-closed (explicit empty allowlist).
    return paths


def _parse_allowed_files_legacy(spec_text: str) -> list[str] | None:
    """Pre-TECH-167 parser: heading variants + any backticked-path-shape.

    Used only when v1 marker is absent (legacy specs). Same semantics as the
    pre-TECH-167 implementation: section heading match → extract every
    backticked path inside the section.
    """
    lines = spec_text.splitlines()
    in_section = False
    section_buf: list[str] = []
    for line in lines:
        if not in_section:
            if _ALLOWED_FILES_HEADING_RE.match(line):
                in_section = True
            continue
        if _NEXT_H2_RE.match(line):
            break
        section_buf.append(line)
    if not in_section:
        return None
    return _ALLOWED_FILE_EXT_RE.findall("\n".join(section_buf))


def _parse_allowed_files(spec_path: Path) -> list[str] | None:
    """Extract allowlist for the implementation guard.

    Strategy (TECH-167):
        1. If spec has the v1 marker → strict canonical parse (no fallback).
        2. Else → legacy parser (heading variants, any backticked paths).
        3. Section absent entirely → None (degrade-open sentinel).

    Returns:
        list[str]: explicit list (may be empty if v1 marker present but
                   bullets malformed → degrade-closed).
        None:      no Allowed Files section at all (legacy spec without
                   any allowlist — caller decides degrade-open semantics).
    """
    try:
        text = spec_path.read_text(errors="replace")
    except OSError as exc:
        log.warning("ALLOWED_FILES: read failed for %s: %s", spec_path, exc)
        return None

    v1 = _parse_allowed_files_v1(text)
    if v1 is not None:
        log.info(
            "ALLOWED_FILES: v1 canonical parse for %s → %d path(s)",
            spec_path.name,
            len(v1),
        )
        return v1

    legacy = _parse_allowed_files_legacy(text)
    if legacy is not None:
        log.info(
            "ALLOWED_FILES: legacy fallback parse for %s → %d path(s)",
            spec_path.name,
            len(legacy),
        )
    return legacy
```

**Edit C — alias for existing test.**

After the new `_parse_allowed_files` definition, add at module scope (right
before the `_get_started_at` function at current L606):

```python
# TECH-167: tests written for TECH-166 used the verb "_append_blocked_reason".
# Keep the old name working as an alias to avoid churning unrelated tests.
_append_blocked_reason = _apply_blocked_reason
```

Wait — `_apply_blocked_reason` operates on text, not on a Path. The existing
test at `tests/unit/test_callback_implementation_guard.py:154-171` calls
`callback._append_blocked_reason(spec, "no_implementation_commits")` where
`spec` is a `Path`. That means the existing test EXPECTS a Path-taking
function. Inspect the test, then implement the alias as:

```python
def _append_blocked_reason(spec_path: Path, reason: str) -> bool:
    """Path-taking wrapper around _apply_blocked_reason — preserves the
    pre-TECH-167 helper signature used by existing unit tests.

    Reads spec_path, applies _apply_blocked_reason, writes back if changed.
    Idempotent: calling twice with the same reason produces only one
    `**Blocked Reason:**` line (re.subn count=1 ensures replacement, not
    append).
    """
    text = spec_path.read_text(errors="replace")
    changed, new_text = _apply_blocked_reason(text, reason)
    if changed and new_text != text:
        spec_path.write_text(new_text)
    return changed
```

**Acceptance:**
- `python3 -c "import sys; sys.path.insert(0, 'scripts/vps'); import callback;
  print(callback._ALLOWED_FILES_V1_MARKER_RE.pattern)"` prints the marker regex.
- `python3 -m pytest tests/unit/test_callback_implementation_guard.py -q` →
  all existing tests still pass (regression).
- `python3 -m py_compile scripts/vps/callback.py` → exit 0.

---

### Task 5 — New test file `tests/unit/test_callback_allowlist_v1.py`

**Goal:** lock down v1 parser behaviour: marker dispatch, strict mode, empty
list, legacy fallback, EC-7 regression on real-world heading variants.

**Files:**
- create: `/home/dld/projects/dld/.worktrees/TECH-167/tests/unit/test_callback_allowlist_v1.py`

**Full file contents (verbatim):**

```python
"""TECH-167 — unit tests for callback.py v1 canonical Allowed Files parser.

Covers EC-1 (canonical), EC-2 (legacy fallback), EC-3 (degrade-closed),
EC-7 (regression on heading variants from awardybot/dowry/gipotenuza/etc).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


def _spec(tmp_path: Path, body: str, name: str = "TECH-XXX.md") -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# --- EC-1: canonical v1 marker → strict parse --------------------------------


def test_ec1_v1_canonical_basic(tmp_path):
    spec = _spec(tmp_path, """\
# TECH-XXX

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `tests/unit/test_x.py`
- `db/schema.sql` — schema bump

## Tests
""")
    assert callback._parse_allowed_files(spec) == [
        "scripts/vps/callback.py",
        "tests/unit/test_x.py",
        "db/schema.sql",
    ]


def test_ec1_v1_marker_with_inline_comment(tmp_path):
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row -->

- `a.py`
- `b/c.py`

## Next
""")
    assert callback._parse_allowed_files(spec) == ["a.py", "b/c.py"]


def test_ec1_v1_extra_prose_after_marker_is_ignored(tmp_path):
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

This intro line is fine.

- `x.py`

## End
""")
    assert callback._parse_allowed_files(spec) == ["x.py"]


# --- EC-3: marker present, malformed bullets → degrade-closed ----------------


def test_ec3_v1_marker_no_bullets_returns_empty(tmp_path):
    """v1 marker but zero canonical bullets → [] (caller blocks done)."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

(no files specified yet)

## Next
""")
    assert callback._parse_allowed_files(spec) == []


def test_ec3_v1_marker_paths_in_fence_ignored(tmp_path):
    """Paths inside a fenced code block are NOT bullets → ignored under v1."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

```
src/foo.py
src/bar.py
```

## Next
""")
    assert callback._parse_allowed_files(spec) == []


def test_ec3_v1_marker_numbered_list_ignored(tmp_path):
    """v1 strictly requires `- ` bullets; numbered list does not match."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

1. `foo.py`
2. `bar.py`

## Next
""")
    assert callback._parse_allowed_files(spec) == []


# --- EC-2: legacy spec without marker → fallback parser ----------------------


def test_ec2_legacy_no_marker_uses_old_parser(tmp_path):
    """No v1 marker → fall back to TECH-166 heading-variant parser."""
    spec = _spec(tmp_path, """\
## Allowed Files

1. `scripts/vps/callback.py` — modify
2. `tests/unit/test_x.py` — NEW

## Tests
""")
    assert callback._parse_allowed_files(spec) == [
        "scripts/vps/callback.py",
        "tests/unit/test_x.py",
    ]


def test_ec2_legacy_section_absent_returns_none(tmp_path):
    spec = _spec(tmp_path, "# Spec\n\n## Tests\n\n- foo\n")
    assert callback._parse_allowed_files(spec) is None


# --- EC-7: regression — real-world heading variants still work ---------------


@pytest.mark.parametrize("heading", [
    "## Allowed Files (whitelist)",
    "## Allowed Files (canonical)",
    "## Allowed Files (STRICT)",
    "## Updated Allowed Files",
    "## Files Allowed to Modify",
])
def test_ec7_legacy_heading_variants_regression(tmp_path, heading):
    """awardybot/dowry/gipotenuza heading variants must still parse via legacy."""
    body = (
        f"{heading}\n\n"
        "1. `src/a.py`\n"
        "2. `src/b.py`\n\n"
        "## Tests\n"
    )
    spec = _spec(tmp_path, body)
    assert callback._parse_allowed_files(spec) == ["src/a.py", "src/b.py"]


# --- v1 marker takes precedence over legacy parser ---------------------------


def test_v1_marker_wins_over_legacy_heading(tmp_path):
    """If a spec uses a legacy-style heading suffix BUT also includes the v1
    marker, callback should treat it as v1 strict (no legacy fallback)."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

- `only/this.py`

## Tests

(legacy parser would also have caught `decoy.py` here outside section)
""")
    assert callback._parse_allowed_files(spec) == ["only/this.py"]


# --- v1 marker outside the section: should NOT trigger v1 mode ---------------


def test_v1_marker_outside_section_ignored(tmp_path):
    """Marker must appear INSIDE the ## Allowed Files section to count."""
    spec = _spec(tmp_path, """\
<!-- callback-allowlist v1 -->

## Allowed Files

1. `legacy.py`

## Tests
""")
    # Marker is above the heading → v1 dispatch does not fire → legacy parser
    # picks `legacy.py`.
    assert callback._parse_allowed_files(spec) == ["legacy.py"]


# --- _append_blocked_reason backwards-compat alias (TECH-167 Task 4) ---------


def test_append_blocked_reason_alias_exists():
    """Test 4's alias is callable and accepts (Path, str)."""
    assert callable(getattr(callback, "_append_blocked_reason", None))
```

**Acceptance:**
- `python3 -m pytest tests/unit/test_callback_allowlist_v1.py -v` → all
  tests pass.
- `python3 -m pytest tests/unit/ -q` → no existing-test regressions.

---

### Task 6 — Document canonical format in CLAUDE.md (root + template)

**Goal:** human-readable summary of the contract so founders/operators can
spot-check specs without reading callback.py.

**Files:**
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/CLAUDE.md`
- modify: `/home/dld/projects/dld/.worktrees/TECH-167/template/CLAUDE.md`

**Insertion point:** in BOTH files, locate `## Backlog Rules` heading. INSERT
a new section IMMEDIATELY BEFORE it.

**Insert verbatim (root + template, identical):**

```markdown
## Spec Allowed Files Contract (TECH-167)

Every new spec created by `/spark` MUST include a canonical
`## Allowed Files` section with the following exact structure:

```markdown
## Allowed Files

<!-- callback-allowlist v1 -->

- `path/to/file1.py` — reason
- `path/to/file2.sql` — reason
- `tests/path/to/test.py` — NEW
```

**Rules:**
- Heading is exactly `## Allowed Files` (case-sensitive H2, no suffix).
- The HTML comment marker `<!-- callback-allowlist v1 -->` is required.
- Each path on its own `- ` bullet, wrapped in single backticks.
- No fenced code blocks, no numbered lists, no nested bullets.
- Minimum one path. Empty list = Spark refuses to write the spec.

**Why:** `scripts/vps/callback.py` parses this section after every autopilot
task to verify implementation commits actually touched a declared file. If the
section is missing or malformed, the callback degrades closed (`done →
blocked`). The marker version-locks the format so future changes can be
introduced as `v2` without breaking older specs.

For legacy specs (no marker), callback falls back to a heading-variant
parser (`## Allowed Files (whitelist)`, `## Updated Allowed Files`, etc.) —
this fallback is frozen and will not gain new variants.

---
```

**Acceptance:**
- `grep -c '^## Spec Allowed Files Contract' CLAUDE.md` → 1.
- `grep -c '^## Spec Allowed Files Contract' template/CLAUDE.md` → 1.
- `grep -c 'callback-allowlist v1' CLAUDE.md` → ≥ 2 (heading example + rule prose).

---

## Task Dependency Graph

```
Task 1 ──┐
         ├──► Task 2 ──► Task 3 ──► (Spark side complete)
         │
Task 4 ──┴──► Task 5 ──► (callback side complete)
                │
                └──► Task 6 (docs — independent, run last)
```

**Execution order:** 1 → 2 → 3 → 4 → 5 → 6.

- Tasks 1 & 4 are independent (separate concerns).
- Task 2 depends on Task 1 (linter regex must mirror the template format).
- Task 3 depends on Task 2 (facilitator/completion reference Phase 5.5).
- Task 5 depends on Task 4 (tests need the new functions).
- Task 6 has no code dependencies but should run last so all behaviour is
  pinned before docs claim it works.

---

## Implementation Notes for Coder

1. **Template sync:** root `.claude/skills/spark/*` and
   `template/.claude/skills/spark/*` MUST stay byte-identical for the affected
   files (per `.claude/rules/template-sync.md`). Run
   `diff -r .claude/skills/spark/ template/.claude/skills/spark/` after each
   skill-file edit; output must be empty.

2. **CLAUDE.md sync:** root and template CLAUDE.md diverge in many places —
   only the new "Spec Allowed Files Contract" section needs to match. Do NOT
   reconcile other diffs.

3. **Regex SSOT:** the four regexes in feature-mode.md Phase 5.5 and the
   constants in callback.py MUST encode the same grammar. If you change one,
   change the other in the same commit, then re-run
   `tests/unit/test_callback_allowlist_v1.py`.

4. **Backwards compatibility:** ALL specs currently in `ai/features/` of all
   DLD projects use the legacy format (no marker). They MUST continue to
   parse — Task 5's EC-7 parametrized test is the regression gate.

5. **The TECH-167 spec itself** uses the canonical v1 format (see lines
   65–77). After Task 4 ships, running
   `_parse_allowed_files(spec_path_for_TECH-167)` should return exactly the
   9 paths listed in the spec.

6. **No commit-as-you-go:** the Coder normally commits per task. For Task 1
   and Task 2, commit ONLY after both root and template are edited (otherwise
   the diff-empty acceptance check fails).

