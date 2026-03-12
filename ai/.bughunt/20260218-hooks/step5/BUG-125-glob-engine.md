# BUG-125 — Glob Engine Bugs

**Priority:** P1
**Group:** Glob Engine
**Findings:** F-018 (`**` zero-segment mismatch), F-019 (bracket class escaping), F-020 (unmatched `]` DoS)
**Affected files:**
- `.claude/hooks/utils.mjs` (lines 244–255)

---

## Summary

The custom `minimatch()` glob engine in `utils.mjs` has three bugs that break the file allowlist pattern matching:

1. **F-018:** `**` requires at least one intermediate directory — `src/**/*.py` does not match `src/foo.py`. This contradicts standard glob semantics and breaks the most common allowlist pattern.
2. **F-019:** Special characters are escaped before bracket class conversion — `[abc]` patterns become broken regex character sets.
3. **F-020:** Unmatched `]` in a glob pattern causes `new RegExp()` to throw a syntax error, crashing `extractAllowedFiles()` and denying all file writes for the session.

Since `minimatch()` is called inside `isFileAllowed()`, these bugs directly affect the spec allowlist — the primary hook safety mechanism.

---

## Root Cause Analysis

### F-018: `**` requires intermediate directory — zero-segment mismatch

```javascript
// utils.mjs:244-254 — CURRENT (BROKEN)
function minimatch(str, pattern) {
  let re = pattern
    .replace(/[.+^${}()|\\]/g, '\\$&')     // step 1: escape regex specials
    .replace(/\*\*/g, '\x00GLOBSTAR\x00')   // step 2: protect **
    .replace(/\*/g, '[^/]*')               // step 3: single * = no slash
    .replace(/\?/g, '[^/]')
    .replace(/\x00GLOBSTAR\x00/g, '.*');   // step 4: ** = .* (any chars including /)
  re = `^${re}$`;
  return new RegExp(re).test(str);
}
```

**The transformation for `src/**/*.py`:**

| Step | Result |
|------|--------|
| After escape | `src/**/*.py` (no change for these chars) |
| After `**` → placeholder | `src/\x00GLOBSTAR\x00/*.py` |
| After `*` → `[^/]*` | `src/\x00GLOBSTAR\x00/[^/]*\.py` |
| After placeholder → `.*` | `src/.*/[^/]*\.py` |
| Final regex | `^src/.*/[^/]*\.py$` |

**Why `src/foo.py` does not match `^src/.*/[^/]*\.py$`:**
- `src/` matches `src/`
- `.*` matches empty string
- Then the regex needs a literal `/` next (from the `/` between `**` and `*`)
- But `foo.py` has no leading `/`
- Match fails

**Standard glob semantics:** `**` should match zero or more path segments. `src/**/*.py` should match both `src/foo.py` (zero intermediate dirs) and `src/sub/foo.py` (one dir).

**Real-world impact:** Any spec using the common `src/**/*.py` or `src/**` pattern will silently fail for files directly inside the target directory. This is the most common glob pattern for "allow edits in this directory tree."

**Concrete example:**
```
Spec: ## Allowed Files
      `src/**/*.py`

Edit: src/models.py
Expected: allowed = true
Actual:   allowed = false (requires at least one subdir)

Edit: src/sub/models.py
Actual:   allowed = true  (has subdir, matches)
```

This creates asymmetric enforcement where deeper files are allowed but top-level files in the pattern directory are denied — a non-obvious and hard-to-diagnose false denial.

### F-019: Bracket character class escaping breaks `[abc]` patterns

```javascript
// utils.mjs:248 — CURRENT (BROKEN)
let re = pattern
  .replace(/[.+^${}()|\\]/g, '\\$&')   // ← escapes . BEFORE bracket handling
  ...
```

**The transformation for `[.py]`:**

| Step | Result |
|------|--------|
| Escape specials | `[\.py]` (`.` is escaped to `\.` INSIDE the bracket) |
| No `**` or `*` in this part | unchanged |
| Final regex | `^[\.py]$` |

**`[\.py]` as a regex character class:**
- `[\.py]` matches: `\`, `.`, `p`, or `y`
- Intended: `[.py]` should match: `.`, `p`, or `y` (literal dot in a character class)

Additionally, `^` inside brackets (intended as negation) gets escaped to `\^`, breaking negated classes like `[^/]`.

**Documented contract violation:** The `minimatch()` JSDoc comment states:
```
* Supports: *, **, ? and character classes [abc].
```
`[abc]` support is documented as a feature but does not work correctly.

**Affected patterns:**
- `[.py]` — match by extension (common pattern)
- `[abc]` — character alternatives
- `[!abc]` or `[^abc]` — negated classes (broken by `^` escaping)
- Any bracket expression containing `.`, `+`, `^`, `$`, `{`, `}`, `(`, `)`, `|`, `\`

### F-020: Unmatched `]` causes `new RegExp()` throw — DoS of file write capability

```javascript
// utils.mjs:253-254 — CURRENT (BROKEN)
re = `^${re}$`;
return new RegExp(re).test(str);  // throws SyntaxError if re is invalid regex
```

**How it reaches here:**

A spec with an entry like `` `src/]evil.py` `` goes through `extractAllowedFiles()` which returns `['src/]evil.py']`. Then `isFileAllowed()` calls `minimatch('src/foo.py', 'src/]evil.py')`.

After the minimatch transformation:
- `src/]evil.py` → `^src/]evil\.py$`
- `new RegExp('^src/]evil\\.py$')` → `SyntaxError: Invalid regular expression`

The throw propagates up through `isFileAllowed()` → `extractAllowedFiles()`'s outer `try/catch`:

```javascript
// utils.mjs:283-285
  } catch {
    return { files: [], error: true }; // read error = deny all  ← catches the throw
  }
```

Wait — actually the throw happens inside `isFileAllowed`, not inside `extractAllowedFiles`. Tracing the call stack:

```
isFileAllowed() [line 377]
  → minimatch() [line 254: new RegExp(re) throws]
  ← SyntaxError propagates
```

`isFileAllowed()` has no try/catch, so the SyntaxError propagates to `pre-edit.mjs`'s main try/catch (fail-safe), which calls `allowTool()`. This means a malformed pattern does NOT cause deny-all — it causes **allow-all** (the fail-safe). But the hook also logs nothing, so this failure is invisible.

**Impact:** A spec author who accidentally types an unmatched `]` in a file path gets silently no-enforcement for all files that would have matched patterns after the broken entry. The confusion is compounding: the entry before the broken one may work, entries after it do not get evaluated because `minimatch` throws early.

---

## Affected Files

| File | Line | Role |
|------|------|------|
| `.claude/hooks/utils.mjs` | 244–255 | `minimatch()` — the entire glob engine |
| `.claude/hooks/utils.mjs` | 349–351 | `matchesPattern()` — calls minimatch for always-allowed |
| `.claude/hooks/utils.mjs` | 370–379 | `isFileAllowed()` inner loop — calls minimatch for spec entries |

---

## Fix Description

### Fix F-018: Make `**` match zero or more path segments

```javascript
// utils.mjs:244-255 — FIXED
function minimatch(str, pattern) {
  // Protect bracket classes before escaping specials
  // (Extract them, replace with placeholder, restore after escape)
  const brackets = [];
  let safe = pattern.replace(/\[([^\]]*)\]/g, (_, inner) => {
    brackets.push(inner);
    return `\x00BRACKET${brackets.length - 1}\x00`;
  });

  // Escape regex specials (now brackets are protected)
  safe = safe.replace(/[.+^${}()|\\]/g, '\\$&');

  // Restore bracket classes (unescaped, as literal regex bracket expressions)
  safe = safe.replace(/\x00BRACKET(\d+)\x00/g, (_, i) => `[${brackets[i]}]`);

  // Convert glob syntax to regex
  let re = safe
    .replace(/\*\*/g, '\x00GLOBSTAR\x00')  // protect ** before single *
    .replace(/\*/g, '[^/]*')               // * = anything except /
    .replace(/\?/g, '[^/]')               // ? = any single char except /
    .replace(/\x00GLOBSTAR\x00\//g, '(?:.*/)?')  // **/ = zero or more dirs  ← F-018 FIX
    .replace(/\x00GLOBSTAR\x00/g, '.*');   // ** (not followed by /) = any sequence

  re = `^${re}$`;

  // F-020: Catch invalid regex from malformed patterns (e.g., unmatched ])
  try {
    return new RegExp(re).test(str);
  } catch {
    // Malformed pattern = no match (safe fail: deny this pattern, try others)
    return false;
  }
}
```

**Key changes for F-018:**
- `**/` (globstar followed by slash) → `(?:.*/)?` — matches zero or more `dir/` segments
- `**` (globstar not followed by slash) → `.*` — unchanged, matches any remaining path

**Verification:**
```
src/**/*.py  →  ^src/(?:.*/)? [^/]*\.py$
```
- `src/foo.py`: `src/` + `` (zero dirs) + `foo.py` → matches
- `src/sub/foo.py`: `src/` + `sub/` (one dir) + `foo.py` → matches
- `src/a/b/foo.py`: `src/` + `a/b/` (two dirs) + `foo.py` → matches

### Fix F-019: Protect bracket classes before escaping (combined in Fix F-018 above)

The fix above uses a pre-pass to extract bracket expressions before special-character escaping:

```javascript
// Pre-pass: protect [abc] bracket classes
const brackets = [];
let safe = pattern.replace(/\[([^\]]*)\]/g, (_, inner) => {
  brackets.push(inner);
  return `\x00BRACKET${brackets.length - 1}\x00`;
});

// Now escape regex specials — brackets are safe
safe = safe.replace(/[.+^${}()|\\]/g, '\\$&');

// Restore bracket classes as proper regex bracket expressions
safe = safe.replace(/\x00BRACKET(\d+)\x00/g, (_, i) => `[${brackets[i]}]`);
```

**Result for `[.py]`:**
- Pre-pass: `\x00BRACKET0\x00` (saves inner `.py`)
- Escape: no `.` to escape (it's protected)
- Restore: `[.py]` — literal dot in bracket class, matches `.`, `p`, `y`

**Result for `[!abc]`:**
- Pre-pass: saves inner `!abc`
- Restore: `[!abc]` — negated class (or use `^` if preferred — note: F-019 finding uses `[abc]` not `[^abc]` notation)

### Fix F-020: Wrap `new RegExp()` in try/catch (included in Fix F-018 above)

```javascript
try {
  return new RegExp(re).test(str);
} catch {
  // Malformed pattern = no match for this specific pattern
  // Return false so the loop in isFileAllowed() continues to the next allowed entry
  return false;
}
```

**Why `false` not `true`:** Returning `false` means "this malformed pattern does not match". The caller (`isFileAllowed`) will continue checking other allowed entries. If no other entry matches, the file is denied — which is the safe default (the spec author intended to restrict edits). This is safer than allowing all (which would be returning `true`).

---

## Impact Tree

### Upstream (who calls minimatch?)
- `matchesPattern()` (utils.mjs:235) — checks always-allowed patterns
- `isFileAllowed()` (utils.mjs:377) — checks spec allowed file entries
- Both are called by `pre-edit.mjs` on every file write attempt

### Downstream (what does minimatch depend on?)
- `String.replace()` — standard built-in, no issues
- `new RegExp()` — now wrapped in try/catch (F-020 fix)
- No external dependencies

### Cascade effect of F-018

If a spec uses `src/**/*.py` and the developer works on files directly inside `src/` (not a subdirectory), every edit is denied. In an autopilot run, this causes:
1. First edit to `src/models.py` → denied by hook
2. Claude Code sees deny → stops or asks
3. Autopilot task blocked; human must intervene
4. Root cause is invisible (spec looks correct, pattern is standard)

### Files that trigger F-018 in practice

Any spec with patterns like:
- `src/**` — expects to match `src/foo.py`
- `tests/**/*.py` — expects to match `tests/test_foo.py`
- `.claude/**` — expects to match `.claude/hooks/utils.mjs` (one level only)
- `**/*.md` — expects to match top-level `README.md`

---

## Definition of Done

- [ ] `minimatch()`: `**/` converts to `(?:.*/)?` (zero-or-more path segments) — F-018
- [ ] `minimatch()`: bracket classes extracted and protected before special-char escaping — F-019
- [ ] `minimatch()`: `new RegExp()` wrapped in try/catch returning `false` on error — F-020
- [ ] Existing minimatch/glob tests pass
- [ ] New test: `src/**/*.py` matches `src/foo.py` (zero intermediate dirs) — F-018
- [ ] New test: `src/**/*.py` matches `src/sub/foo.py` (one dir) — F-018
- [ ] New test: `**/*.md` matches `README.md` (top-level) — F-018
- [ ] New test: `[.py]` pattern matches `.` and `p` and `y` (literal chars) — F-019
- [ ] New test: `[abc]` pattern matches `a`, `b`, `c` — F-019
- [ ] New test: `src/]bad.py` pattern in spec does not crash; returns false — F-020
- [ ] New test: after malformed pattern, subsequent patterns still match — F-020

---

## Test Requirements

```javascript
// F-018: Standard ** semantics
test('minimatch: **/ matches zero segments', () => {
  assert(minimatch('src/foo.py',        'src/**/*.py')); // zero intermediate dirs
  assert(minimatch('src/sub/foo.py',    'src/**/*.py')); // one dir
  assert(minimatch('src/a/b/foo.py',    'src/**/*.py')); // two dirs
  assert(minimatch('README.md',         '**/*.md'));     // top-level
  assert(!minimatch('src/foo.js',       'src/**/*.py')); // wrong extension
});

// F-019: Bracket character classes
test('minimatch: [abc] bracket class works', () => {
  assert(minimatch('a', '[abc]'));
  assert(minimatch('b', '[abc]'));
  assert(!minimatch('d', '[abc]'));
  assert(minimatch('src/file.py', 'src/file.[pj][sy]')); // compound bracket
});

test('minimatch: [.py] matches literal dot and chars', () => {
  assert(minimatch('.', '[.py]'));
  assert(minimatch('p', '[.py]'));
  assert(!minimatch('x', '[.py]'));
});

// F-020: Malformed pattern — no crash, no allow-all
test('minimatch: unmatched ] returns false, does not throw', () => {
  assert.doesNotThrow(() => minimatch('src/foo.py', 'src/]evil.py'));
  assert(!minimatch('src/foo.py', 'src/]evil.py'));
});

test('isFileAllowed: malformed pattern does not block subsequent valid patterns', () => {
  // spec: ['src/]bad.py', 'src/foo.py']
  // filePath: 'src/foo.py'
  // assert: allowed = true (second entry matches despite first being malformed)
});
```

---

## Change History

| Date | What | Task | Who |
|------|------|------|-----|
| 2026-02-18 | Spec created from Bug Hunt 20260218-hooks | BUG-125 | bughunt |
