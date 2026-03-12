# Pattern Research — /upgrade skill (DLD template deterministic sync)

## Context

Users create projects from the DLD GitHub template. When DLD releases updates to `.claude/` skills,
agents, hooks, and rules — users need a way to pull those changes into their existing project.
The core constraint: **LLM is non-deterministic, cannot be trusted to copy N files reliably.**
The solution must be deterministic and verifiable.

---

## Approach 1: Script-First (bash/Node.js does all file operations)

**Source:** [SvelteKit update-template-repo.sh](https://github.com/sveltejs/kit/blob/main/packages/create-svelte/scripts/update-template-repo.sh)

### Description
A shell or Node.js script performs all file operations — download latest template from GitHub,
compare with installed version, copy safe files, flag user-modified files. The skill prompt
only explains results to the user after the script has run. The script is the single source of truth.
This is the pattern used by SvelteKit's own template maintenance tooling.

### Pros
- 100% deterministic — same input, same output, every time
- Fully auditable — user can read the script before running
- No git history dependency — works even if user has no git history
- Node.js already required by DLD (hooks are `.mjs`) — no new runtime
- Easy to test in CI against known fixture directories

### Cons
- 3-way merge requires additional tooling (`diff3`, `node-diff3` package, or manual conflict markers)
- Bash portability issues on Windows (requires Git Bash or WSL)
- Node.js version solves portability but adds ~50 LOC for file operations
- Merge conflict UX is inferior to git's conflict markers unless deliberately implemented
- Script must be kept up-to-date alongside template changes (meta-maintenance cost)

### Complexity
**Estimate:** Medium — 6-10 hours
**Why:** Core detection logic is straightforward (compare files). The hard part is merge conflict
presentation for user-modified files. Need to generate readable conflict output, not just "file
differs". If using Node.js: `crypto.createHash('sha256')` for detection + `diff3` or `node-diff3`
for merge generation.

### Example Source
```bash
# SvelteKit pattern — script clones template, updates contents, commits
git clone --depth 1 --single-branch --branch main \
  git@github.com:dld/template.git /tmp/dld-template

node scripts/upgrade.mjs --source /tmp/dld-template --target .
```

```js
// upgrade.mjs (simplified detection logic)
import { createHash } from 'crypto'
import { readFileSync } from 'fs'

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

// Compare against stored manifest
const manifest = JSON.parse(readFileSync('.dld-manifest.json'))
for (const [file, originalHash] of Object.entries(manifest.files)) {
  const currentHash = sha256(file)
  if (currentHash === originalHash) {
    // safe to overwrite — user hasn't touched it
  } else {
    // user modified — needs merge
  }
}
```

---

## Approach 2: Git Upstream Remote

**Source:** [Syncing a fork — GitHub Docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork) | [Configuring GitHub Templates to Merge From Upstream](https://sciri.net/blog/configuring-github-templates-to-merge-from-upstream)

### Description
Treat the DLD template as a git upstream remote. Add `git remote add dld-upstream
https://github.com/Ellevated/dld.git`, then `git fetch dld-upstream && git merge
dld-upstream/main --allow-unrelated-histories`. Git performs native 3-way merge using its history
graph. Conflict markers are inserted into files for manual resolution. This is how GitHub's own
"Sync fork" button works and how blue-build.org recommends syncing template repos.

### Pros
- Git handles 3-way merge natively — proven at billions of repos
- Conflict resolution workflow users already know (merge markers, `git mergetool`)
- No extra scripts to maintain — two git commands
- History is preserved — `git log` shows what changed and when
- Works with any git client (CLI, VS Code, GitHub Desktop)

### Cons
- Template was created via `Use this template` (not fork) — histories are unrelated, `--allow-unrelated-histories` required, which is confusing
- `.claude/` is in `.gitignore` for some users — git will not track those files, making this approach fail silently
- User needs to understand git remotes and merge conflicts — higher cognitive bar
- If user's project is not a git repo, approach is impossible
- Merge brings in ALL template commits including unrelated ones (README, docs, etc.)

### Complexity
**Estimate:** Easy as script (2-3 commands) — Hard as UX (explaining to non-git-expert users)
**Why:** The git commands themselves are 4 lines. But the failure modes — unrelated histories,
`.gitignore` conflicts, detached HEAD after merge — require significant documentation and defensive
handling. Real-world evidence from cruft maintainers shows 3-way merge failure is common in
automated/CI contexts ("repository lacks the necessary blob to perform 3-way merge").

### Example Source
```bash
# One-time setup
git remote add dld-upstream https://github.com/Ellevated/dld.git

# Upgrade
git fetch dld-upstream
git merge dld-upstream/main --allow-unrelated-histories
# Resolve conflicts in editor, then:
git commit
```

The `--allow-unrelated-histories` flag is required because GitHub template repos start with a
single orphan commit, not a fork of upstream. See: [sciri.net post](https://sciri.net/blog/configuring-github-templates-to-merge-from-upstream) — "This is where things get tricky, because a template is not a fork."

---

## Approach 3: Checksum Manifest + Patch Apply (Hybrid)

**Source:** [cruft — Fight Back Against the Boilerplate Monster](https://cruft.github.io/cruft/) | [Node.js SHA256 directory comparison](https://andidittrich.com/2017/10/node-js-compare-two-directories-with-file-checksums-asynchronously.html)

### Description
This is the pattern used by `cruft` (the most battle-tested template upgrade tool, 1.5k GitHub
stars). At install time, store a manifest (`~/.dld-manifest.json` or `.dld-version`) with SHA256
hash of each installed template file plus the template version/commit. On upgrade: fetch the new
template, compare each file's current hash against the stored hash to classify it as
`unchanged|user-modified|new`. For unchanged files: safe overwrite. For user-modified files:
generate a patch (old template → new template) and try to apply it. For new files: copy directly.
Skill prompt shows the user a report; script does the work.

### Pros
- Lightweight manifest (~1KB JSON) vs full snapshot (~500KB)
- Three-state classification enables precise decisions: overwrite/patch/add
- No git history required — works in non-git directories
- Proven algorithm: cruft uses exactly this pattern for Cookiecutter templates
- Node.js `crypto` module provides SHA256 natively — zero extra dependencies for detection
- Patch generation with `diff` and application with `git apply -3` or `node-diff3` handles merge

### Cons
- Manifest must be created at install time and committed (new install step vs current DLD flow)
- If user loses or corrupts manifest, classification degrades to "all files modified" (safe fallback: show diff, ask user)
- Patch application can fail (same cruft issue #181, #287 — "patch failed, falling back to 3-way merge") — need `.rej` file handling
- More moving parts than pure git approach
- Need to handle the case where DLD did not exist when user installed (no manifest)

### Complexity
**Estimate:** Medium — 8-12 hours
**Why:** Manifest generation at install time is ~20 LOC. Detection is ~30 LOC. The hard part is
patch application + conflict presentation, which cruft has been iterating on since 2019. Using
`node-diff3` (npm, zero native deps) avoids shell diff/patch portability issues. Total: manifest
writer (1 file), upgrade script (1 file), conflict reporter (1 file).

### Example Source
```js
// .dld-manifest.json (generated at install time by bootstrap)
{
  "version": "1.4.2",
  "commit": "769a2ae",
  "installed_at": "2026-02-20",
  "files": {
    ".claude/skills/spark/SKILL.md": "a3f8c1d...",
    ".claude/agents/coder.md": "b29e44f...",
    ".claude/hooks/pre-tool.mjs": "c91d3e2..."
  }
}
```

```js
// upgrade.mjs — classification logic
import { createHash } from 'crypto'
import { readFileSync, existsSync } from 'fs'

const manifest = JSON.parse(readFileSync('.dld-manifest.json'))
const results = { safe: [], modified: [], new: [] }

for (const [file, installedHash] of Object.entries(manifest.files)) {
  if (!existsSync(file)) { results.new.push(file); continue }
  const currentHash = sha256(file)
  if (currentHash === installedHash) {
    results.safe.push(file)      // overwrite freely
  } else {
    results.modified.push(file)  // needs 3-way merge
  }
}
// new files in latest template (not in manifest) -> results.new
```

cruft applies this as a diff between old-template-version and new-template-version, then
applies the diff to user's file. See: [cruft source — _apply_patch](https://github.com/cruft/cruft)

---

## Comparison Matrix

| Criteria | Approach 1: Script-First | Approach 2: Git Upstream | Approach 3: Checksum+Patch |
|----------|--------------------------|--------------------------|---------------------------|
| Determinism | High | High (when it works) | High |
| Merge quality | Low (manual or diff3) | High (git native) | Medium (diff3/node-diff3) |
| Git dependency | None | Hard required | None |
| .gitignore safety | High | Low (breaks silently) | High |
| Manifest overhead | None (or simple) | None | Low (~1KB JSON) |
| UX complexity | Low | Medium-High | Low-Medium |
| Implementation effort | Medium | Low-Medium | Medium-High |
| Failure modes | Needs manual merge UX | Unrelated histories, .gitignore blind spots | Patch rejection, missing manifest |
| Proven at scale | Partial (ad-hoc) | Yes (GitHub forks) | Yes (cruft, 1.5k stars) |
| Works without git repo | Yes | No | Yes |
| New file detection | Medium (need to scan) | High (git diff shows additions) | High (manifest diff) |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 1 (Script-First) with Approach 3's classification logic (Hybrid)

### Rationale

Pure Approach 2 (git upstream) has a structural problem for DLD: `.claude/` is in `.gitignore`
in many user projects. This means `git merge` from the upstream remote silently ignores the exact
files that need upgrading. That is an unacceptable failure mode.

Pure Approach 3 (checksum+patch) is ideal but requires a manifest written at install time —
which DLD's current bootstrap flow does not do. Retrofitting this means every existing user needs
a migration step.

Approach 1 with smart classification is the pragmatic path:

1. **No git dependency** — works in any directory, `.gitignore` irrelevant
2. **Manifest is optional, not required** — if manifest exists, use 3-state classification;
   if absent, fall back to "show diff + ask user" for every file that differs
3. **Node.js already required** — hooks are `.mjs`, DLD already gates on Node 18+
4. **Script is the authoritative actor** — LLM explains, script executes. Non-determinism lives
   only in the human decision layer (which conflicts to accept)

Key factors:
1. **Gitignore safety** — Approach 2 silently fails on the most important files. Approach 1 doesn't care about git at all.
2. **Progressive adoption** — Can ship without manifest support first (always show diff), add manifest detection in v2 for precise classification
3. **Proven classification logic** — Borrow the cruft 3-state model (safe/modified/new) without taking on cruft's patch-application fragility

### Trade-off Accepted

We give up git's native 3-way merge resolution (Approach 2). Instead, for user-modified files,
the script will generate a readable diff and the user resolves manually or uses their editor.
This is slightly worse UX than git conflict markers for power users — but it reaches 100% of users
including those without git history or with `.claude/` gitignored.

We also defer the manifest write to bootstrap (`/spark` or setup script), meaning v1 of upgrade
can only detect "file differs from latest template" without knowing "was it user who changed it or
did it come that way". This means v1 may ask about false positives. Acceptable for MVP.

---

## Research Sources

- [SvelteKit update-template-repo.sh](https://github.com/sveltejs/kit/blob/main/packages/create-svelte/scripts/update-template-repo.sh) — Script-first template maintenance pattern used by major open-source project
- [cruft — template upgrade tool](https://cruft.github.io/cruft/) — Checksum+patch upgrade algorithm for Cookiecutter templates (1.5k stars, production-proven)
- [cruft issue #181 — 3-way merge failure](https://github.com/cruft/cruft/issues/181) — Evidence that patch-based 3-way merge fails in CI/automated contexts ("repository lacks necessary blob")
- [GitHub Docs — Syncing a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork) — Git upstream remote pattern
- [Configuring GitHub Templates to Merge From Upstream](https://sciri.net/blog/configuring-github-templates-to-merge-from-upstream) — Evidence of `--allow-unrelated-histories` complexity and failure modes for template (non-fork) repos
- [Node.js SHA256 directory comparison](https://andidittrich.com/2017/10/node-js-compare-two-directories-with-file-checksums-asynchronously.html) — Implementation reference for checksum-based file comparison in Node.js
- [diff3 algorithm paper — Pierce et al.](https://www.cis.upenn.edu/~bcpierce/papers/diff3-short.pdf) — Theoretical basis for 3-way merge: O←A→B where O=original template, A=user's version, B=new template
