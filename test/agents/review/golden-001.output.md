# Reference Review — golden-001

For human comparison only. The judge scores against `golden-001.rubric.md`, not
against this text. Every defect below was a real bug in this repository; the
decoys are real patterns the project deliberately allows.

---

## Findings

**D1 — `lifecycle.py:_run`, `text=True` translates newlines on stdin. HIGH.**
`text=True` puts the stdin pipe in text mode, so every `\n` in the yaml blob
becomes `\r\n` on Windows before `git hash-object` ever sees it. The object
store receives CRLF, which `.gitattributes eol=lf` cannot undo — it governs
checkout/checkin of working-tree files, not bytes fed to plumbing on stdin.
`ai/lifecycle/` then reads as permanently modified, and any startup assertion
that the lifecycle tree is clean aborts. Pass bytes: encode the blob UTF-8 and
drop `text=True`.

**D2 — `lifecycle.py:_run`, git output decoded with the locale codec. HIGH.**
The same `text=True` decodes stdout/stderr using the platform's preferred
encoding. `blocked_reason` is routinely Russian, so on a cp1251 host reading
that value back raises `UnicodeDecodeError` and the caller treats a valid yaml
as malformed. Decode explicitly as UTF-8 with `errors="replace"`.

**D3 — `claude-runner.py:_resolve_cli_path`, PATH order outranks the current
install. HIGH.** Candidates are tried in order and `shutil.which("claude")`
comes before `~/.local/bin/claude`. Under the daemon's PATH there is no
`~/.local/bin` entry at all, so `which` resolves whatever sits in
`/usr/local/bin` — potentially a binary frozen months ago — and the
self-updating launcher is never reached. A CLI too old to know the pinned model
does not fail; it silently runs its own default, with that model's smaller
context window. Order by version, not by position.

**D4 — `orchestrator.py`, `get_available_slots(...) >= 0` is vacuous. MEDIUM.**
The function returns `COUNT(*)`, which is never negative, so the condition is
always true whenever the regex matches. The guard expresses an intent it does
not enforce: the spec's `provider:` line always wins, capacity or not. Either
compare against `>= 1`, or delete the check and state that the spec's provider
is authoritative.

**D5 — `render_backlog.py:render`, silent swallow of a failed write. MEDIUM.**
`except Exception: pass` discards write errors, so a full disk or a permission
fault leaves a stale `backlog.md` while every caller believes the render
succeeded. ADR-004 permits fail-safe swallowing in `.claude/hooks/` only; this
is not a hook. Log the exception at minimum.

**D6 — `deploy.sh`, `git add -A` stages more than intended. MEDIUM.**
`-A` sweeps every untracked file in the tree, including daemon runtime state
(pid and heartbeat files) that happens to be present at deploy time. Once such a
file is tracked, a later `git pull` on the machine writing it refuses to run
rather than clobber it, and the deploy jams. Stage the generated view by path.

---

## Explicitly NOT defects

- **`.claude/hooks/pre-edit-guard.mjs`** — the bare `catch` with `exit(0)` is
  required behaviour, not an oversight. A hook that throws breaks the session,
  so ADR-004 mandates exactly this shape.
- **`pricing.py:apply_discount`** — integer cents with floor division is the
  mandated money pattern (ADR-001). No float is involved and no rounding rule is
  violated. Recommending `Decimal` here contradicts the project's own rule.
- **File sizes** — the largest file in the input is 390 LOC, under the 400 limit.

## Bonus observations (neither rewarded nor penalised)

- `_run` returns `CompletedProcess` with `check=False` and no caller inspects
  `returncode`; a failed `hash-object` yields an empty `sha` that is then written
  into `update-index` as a valid-looking argument.
- `write_lifecycle` builds the `--cacheinfo` argument by f-string without
  validating that `sha` is a 40-char hex object id.
