# Callback regression corpus

This directory holds 25 frozen real-world DLD specs (5 per project) used as
golden inputs for `callback._parse_allowed_files`. Any regex change to the
parser must keep these fixtures passing or be flagged as an intentional
breaking change.

## Layout

```
{project}_{spec_id}[__{shape}].md           — frozen copy of a real spec
{project}_{spec_id}[__{shape}].expected.json — hand-verified parser output
```

## Shapes covered

| Shape | Description | Example |
|-------|-------------|---------|
| canonical | `## Allowed Files` + numbered/bullet list with backtick paths | `dowry_BUG-394.md` |
| heading-variant | `## Allowed Files (whitelist)` / `## Updated Allowed Files` / `## Files Allowed to Modify` / `## Allowed Files (STRICT)` | `awardybot_FTR-909__heading-variant.md` |
| fenced-block | Paths inside a fenced code block inside the section; parser may return `[]` if paths lack backtick wrapping | `awardybot_FTR-882__fenced-block.md` |
| no-section | No `## Allowed Files` heading at all — parser returns `None` | `gipotenuza_FTR-098.md` |
| multi-section | Section split by H3 subheadings (`### New files`, `### Existing files`) | `wb_ARCH-176a.md` |

## Projects

| Project | Specs |
|---------|-------|
| awardybot | FTR-897 (canonical), FTR-909 (heading-variant), FTR-882 (fenced-block), BACK-0001 (no-section), ARCH-713 (multi-section) |
| dowry | BUG-394 (canonical), BUG-383 (heading-variant), FTR-390 (fenced-block), ARCH-073 (no-section), TECH-207 (multi-section) |
| gipotenuza | ARCH-055 (canonical), FTR-092 (canonical), TECH-081 (heading-variant), FTR-098 (no-section), BUG-084 (multi-section) |
| plpilot | BUG-326 (canonical), BUG-182 (canonical), ARCH-001 (heading-variant), ARCH-147 (no-section), BUG-181 (multi-section) |
| wb | ARCH-176a (multi-section), ARCH-176b (canonical), ARCH-176d (heading-variant), BUG-038 (no-section), TECH-178 (fenced-block) |

## Expected JSON schema

```json
{
  "shape": "canonical | heading-variant | fenced-block | no-section | multi-section",
  "v1_marker": false,
  "expected_paths": ["src/foo.py", "src/bar.py"],
  "expected_return_type": "list",
  "_comment": "Generated YYYY-MM-DD from /path/to/source"
}
```

For `no-section` specs:

```json
{
  "shape": "no-section",
  "v1_marker": false,
  "expected_paths": null,
  "expected_return_type": "None",
  "_comment": "..."
}
```

## Adding a new fixture

1. Pick a real spec. Copy it as `{project}_{spec_id}[__{shape}].md`.
2. Manually inspect the `## Allowed Files` block (or its absence).
3. Run the parser:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'scripts/vps')
   from pathlib import Path
   import callback
   print(callback._parse_allowed_files(Path('tests/regression/spec_corpus/{your_file}.md')))
   "
   ```
4. Write the sidecar `{project}_{spec_id}[__{shape}].expected.json` using the output above.
5. Run `pytest tests/regression/test_callback_spec_corpus.py -v`. The new fixture is auto-discovered via glob.

## What counts as a breaking change

A parser change is **breaking** if:

- Any fixture's `expected_paths` list changes (item added, removed, or reordered).
- Any fixture's `expected_return_type` flips between `"list"` and `"None"`.

If the change is intentional (e.g., a bug-fix to the legacy regex):

1. Update the affected fixture's `.expected.json` in the same PR.
2. Document the change in the spec's `## Drift Log` (or relevant TECH task).
3. Reviewers must confirm the change is desired for all 5 projects.

## Re-syncing fixtures from upstream

Fixtures are **frozen**. They do NOT track upstream spec edits. If a real
project updates its spec file, the fixture stays at the snapshot date.
Re-snapshot only when adding a new shape or coverage scenario.
