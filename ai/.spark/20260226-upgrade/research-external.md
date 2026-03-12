# External Research — /upgrade skill: deterministic DLD template update

## Best Practices

### 1. Use a manifest file (not just a version number) as the source of truth

**Source:** [cruft documentation](https://cruft.github.io/cruft/) and [`.cruft.json` format](https://howto.neuroinformatics.dev/programming/Cookiecutter-cruft.html)

**Summary:** The gold standard for template-based upgrade tracking is a single JSON manifest file committed to the project root. cruft (the Python template upgrade tool, 2K+ GitHub stars) uses `.cruft.json`:

```json
{
  "template": "https://github.com/example/template",
  "commit": "8a65a360d51250221193ed0ec5ed292e72b32b0b",
  "skip": ["tests", "CLAUDE.md"],
  "context": { "project_name": "my-project" }
}
```

The `commit` field is the git SHA of the **template repo** at the time of the last successful upgrade. This is what makes 3-way merge possible: you have `base` (template at install), `current` (user's files), `new` (template HEAD).

**Why relevant:** DLD should use `.dld-version` containing `{ "template_commit": "...", "installed_at": "...", "version": "x.y.z", "skip": [] }`. The `template_commit` SHA is the anchor for computing the diff to apply.

---

### 2. Compute template diff, apply as patch — do NOT copy files blindly

**Source:** [rn-diff-purge USAGE.md](https://github.com/react-native-community/rn-diff-purge/blob/master/USAGE.md) — React Native's canonical upgrade approach (1.3K stars)

**Summary:** The React Native community solved the same problem in 2019. Their approach:

```bash
# Download the diff between old template version and new
curl https://github.com/.../compare/release/0.29.0...release/0.30.0.diff > upgrade.patch

# Apply with git apply (3-way when possible)
git apply --3way upgrade.patch
```

Key insight: you generate a diff **between two clean template states** (old → new), then apply that diff to the user's repo. This means:
- Lines the user did not touch apply cleanly
- Lines both template and user changed → conflict markers
- Lines only user changed → untouched (user wins)

**Why relevant:** This is exactly the mechanism for DLD. The script: (1) generates `template@base_commit → template@HEAD` diff, (2) applies with `git apply --3way` to the project, (3) presents conflicts to the Skill for human resolution.

---

### 3. `git merge-file` for per-file 3-way merge (fallback strategy)

**Source:** [git-merge-file documentation](https://git-scm.com/docs/git-merge-file.html) — official Git docs

**Summary:** `git merge-file` is the standard Unix tool for 3-way merge of individual files:

```bash
git merge-file \
  -L "your version" \
  -L "base (v1.0)" \
  -L "new template" \
  current.md base.md new.md
# Returns 0 = clean merge, N = N conflicts
# Leaves conflict markers <<<<<< ======= >>>>>>> in current.md on conflict
```

Signature: `git merge-file <current> <base> <other>`
- `current` = user's file (modified in-place)
- `base` = template at install time (from `.dld-version` commit reference)
- `other` = latest template version

Exit code: 0 = clean, >0 = number of conflicts. Used by cruft, Helm (3-way strategic merge patches in Helm 3), and git itself internally.

**Why relevant:** DLD's upgrade script should use `git merge-file` per file as the fallback when `git apply --3way` fails. It produces human-readable conflict markers that the Skill can show to the user.

---

### 4. File categorization before any action — classify first, act second

**Source:** [Yeoman generator update workflow discussion (GitHub)](https://github.com/yeoman/yo/issues/474) + [cruft skip list](https://cruft.github.io/cruft/)

**Summary:** Every mature template upgrade system pre-classifies files into categories before applying changes:

| Category | Detection | Action |
|----------|-----------|--------|
| NEW in template | file exists in new, not in base or user | auto-add |
| DELETED in template | file in base, not in new | prompt user |
| Template-only changed | base != new, base == user (sha match) | auto-update |
| Both changed (conflict) | base != new, base != user | 3-way merge, show diff |
| User-only changed | base == new, base != user | leave untouched |
| Skip list | in `.dld-version.skip[]` | always leave alone |

cruft's skip list allows permanent opt-out: `"skip": ["CLAUDE.md", "ai/"]`. Yeoman's issue #474 confirmed that without categorization, generators break user code silently.

**Why relevant:** DLD upgrade script must classify all files FIRST, output a summary, then ask for confirmation before touching anything. This is what prevents "silent skips."

---

### 5. Verification gate: `files_processed == total_files`

**Source:** [How to write idempotent Bash scripts (HN discussion, 655 upvotes)](https://news.ycombinator.com/item?id=20375197) + cruft CI integration pattern

**Summary:** Production upgrade scripts always verify completeness. cruft adds `cruft check` as a CI gate — it exits with code 1 if the project is out of date. The pattern:

```bash
TOTAL=$(find_all_template_files | wc -l)
PROCESSED=0

for file in $template_files; do
  process_file "$file" && PROCESSED=$((PROCESSED + 1))
done

if [ "$PROCESSED" -ne "$TOTAL" ]; then
  echo "ERROR: Only $PROCESSED/$TOTAL files processed. Aborting."
  exit 1
fi
```

Idempotency rule: running upgrade twice should produce the same result. Track state in the manifest file, not in memory.

**Why relevant:** DLD's upgrade script must count and verify. "files_processed == total_files" is the non-negotiable gate before updating `.dld-version`.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| `git merge-file` | built-in | Zero deps, standard 3-way merge, exit code = conflict count, modifies file in-place | Line-based only (no semantic awareness) | Per-file 3-way merge in bash script | [git-scm docs](https://git-scm.com/docs/git-merge-file.html) |
| `git apply --3way` | built-in | Applies patch to whole repo at once, falls back to 3-way on conflict | Requires patch file preparation step | Bulk template diff application | [rn-diff-purge](https://github.com/react-native-community/rn-diff-purge/blob/master/USAGE.md) |
| `cruft` (Python) | 1.5.0 | Full template lifecycle management, .cruft.json tracking, CI integration, skip lists, GitHub Actions workflow | Python dependency, complex setup for simple use case, known 3-way merge failures in cloned repos (issue #181) | Python/Cookiecutter projects | [cruft.github.io](https://cruft.github.io/cruft/) |
| `update-yeoman-generator` | 3.0.0 | Handles .yo-rc.json version tracking, EJS template support | Only for Yeoman generators, npm ecosystem only | Yeoman-based scaffolders | [npmjs.com](https://www.npmjs.com/package/update-yeoman-generator) |
| `chezmoi update` | 2.x | git pull + apply in one command, auto-commit/push support, handles dotfiles across machines | Requires full chezmoi setup, not designed for framework distribution | Dotfiles management | [chezmoi.io](https://chezmoi.io/user-guide/daily-operations) |
| `shasum` / `sha256sum` | built-in | Detects if user modified a file (compare current hash vs stored hash-at-install) | Hash stored separately from file | User-modification detection | [Stack Overflow](https://stackoverflow.com/questions/51546097/verify-sha-256-sum-of-a-file) |

**Recommendation:** No external library needed. Use `git merge-file` (built-in) + `git apply --3way` (built-in) + `shasum` (built-in) — pure bash with zero dependencies. This is the same stack cruft uses under the hood (it shells out to git). The `.dld-version` manifest file tracks the template git commit SHA as the base for diffs.

---

## Production Patterns

### Pattern 1: Commit-anchored diff (rn-diff-purge / React Native Upgrade Helper)

**Source:** [react-native-community/rn-diff-purge](https://github.com/react-native-community/rn-diff-purge) — 1.3K stars, used by React Native's official upgrade tooling

**Description:**
1. Maintain a separate "clean template" repo with one commit per version
2. To upgrade from v1.0 to v1.2: `git diff v1.0...v1.2 > upgrade.patch`
3. Apply the patch to user's project: `git apply --3way -p2 upgrade.patch`
4. The `-p2` strips leading path prefix (e.g., `RnDiffApp/`) so paths match user's project
5. Conflicts go to `.rej` files or inline markers — user resolves manually

**Real-world use:** React Native official upgrade path. [upgrade-helper.reactnative.dev](https://react-native-community.github.io/upgrade-helper/) is a web UI built on top of this. Millions of RN apps upgraded via this pattern.

**Fits DLD:** Yes — DLD template is on GitHub. We can `git clone` the template, `git diff $BASE_COMMIT..HEAD -- template/`, then apply. The template lives at `template/` in the DLD repo, so `-p2` strips both leading directories.

---

### Pattern 2: Manifest + skip list + 3-way merge (cruft pattern)

**Source:** [cruft](https://cruft.github.io/cruft/) — 2K stars, used by Astronomer, ASTRON, many Python organizations

**Description:**
1. On first install: write `.cruft.json` with `{ "commit": "<git SHA>", "skip": [] }`
2. On upgrade: `git diff $old_commit..$new_commit` on clean template clone
3. Per file: check if user modified it (diff user vs original template at `$old_commit`)
4. If user did NOT modify: auto-apply template change
5. If user DID modify AND template also changed: run `git merge-file` → show conflict
6. If template file is NEW: always copy
7. Update `.cruft.json` commit to HEAD after success

**Real-world use:** Astronomer uses cruft to keep 50+ Airflow project repos in sync with their standard template. GitHub Actions workflow auto-creates PRs weekly when template drifts.

```yaml
# cruft GitHub Actions pattern (production)
- name: Check if update is available
  run: |
    if ! cruft check; then
      cruft update --skip-apply-ask
    fi
- uses: peter-evans/create-pull-request@v4
  with:
    branch: cruft/update
    title: "New updates from DLD template"
```

**Fits DLD:** Yes — `.dld-version` plays the role of `.cruft.json`. The GitHub Actions pattern (auto-PR weekly) is directly applicable for DLD's CI story.

---

### Pattern 3: Schematic migrations (Angular `ng update`)

**Source:** [Angular migration schematics](https://medium.com/ngconf/modernize-your-angular-app-with-migration-schematics-afe9ed9fa69b) — Angular CLI (millions of users)

**Description:**
1. Each major version ships a "migration schematic" (a TypeScript script)
2. `ng update @angular/core` runs the schematic: modifies specific AST nodes, config files
3. Schematics are version-gated: only the delta from v18→v19 runs
4. Code-aware: can rename APIs, move imports, change config structures

**Real-world use:** Angular 19 ships standalone migration, inject() migration, etc. Run automatically on `ng update`. Google-scale (millions of projects).

**Fits DLD:** Partially — Angular schematics require TypeScript runtime and AST parsing. Overkill for DLD's text files (.md, .mjs). However, the **version-gating pattern** is directly applicable: each DLD release could ship a small migration script that handles that version's specific breaking changes.

---

### Pattern 4: Helm 3-way strategic merge patches

**Source:** [3-way Strategic Merge Patches in Helm](https://www.elpa.dev/2025/11/02/helm-3-ways-strategic-merge-patches.html)

**Description:** Helm 3 compares: (previous release manifest) vs (new chart version) vs (live state). If a field was NOT changed between previous and new chart, it is not touched — even if user manually changed it. Only fields changed by the chart upgrade are updated.

**Real-world use:** Helm (CNCF graduated project, used by virtually all Kubernetes deployments). Production systems with millions of upgrades.

**Fits DLD:** The insight is: "if template didn't change a section, user's change wins silently." This is the correct default for DLD — user edits to sections the template didn't touch should be preserved without any prompt.

---

## Key Decisions Supported by Research

### 1. Decision: `.dld-version` stores template git commit SHA (not semver string)

**Evidence:** cruft (2K stars) stores `"commit": "8a65a360..."` — the git SHA of the template at install time. rn-diff-purge uses `release/0.29.0` git tags. Both use git's object model as the source of truth.

**Rationale:** A semver string requires a lookup table. A git SHA lets you run `git diff $sha..HEAD -- template/` directly — no lookup needed, always precise.

**Confidence:** High

---

### 2. Decision: `git apply --3way` as primary merge, `git merge-file` as per-file fallback

**Evidence:** rn-diff-purge recommends `git apply` for bulk application. cruft uses `git apply` with 3-way fallback (issue #181 shows the edge case). `git merge-file` is git's own tool for single-file 3-way merge — used internally by git merge.

**Rationale:** `git apply --3way` handles the common case (no conflicts) in one shot. For files with conflicts, `git merge-file` gives fine-grained control and conflict markers that the Skill can present to the user.

**Confidence:** High

---

### 3. Decision: File classification BEFORE any writes — never modify without categorizing first

**Evidence:** Yeoman's issue #474 (2016, Yeoman core team) documents that naive "re-run generator" breaks user code. cruft's skip list and file categorization emerged from the same lesson. Angular schematics are also categorization-first.

**Rationale:** Users need to see "here's what will change, here's what has conflicts, here's what will be left alone" BEFORE any file is written. This is the trust contract.

**Confidence:** High

---

### 4. Decision: SHA-based user-modification detection (not git status)

**Evidence:** chezmoi uses content hash comparison to detect local modifications. cruft computes `git diff` against the stored template commit. `shasum` is universally available on macOS/Linux.

**Rationale:** Users may not use git in their DLD project (or may have uncommitted changes for unrelated reasons). Checking `sha256sum(current_file) != sha256sum(template@base_commit)` is git-independent and reliable.

**Implementation:**
```bash
# At install time: store hash of each template file
sha256sum .claude/skills/spark/SKILL.md >> .dld-version.checksums

# At upgrade time: detect user modification
STORED=$(grep "SKILL.md" .dld-version.checksums | awk '{print $1}')
CURRENT=$(sha256sum .claude/skills/spark/SKILL.md | awk '{print $1}')
if [ "$STORED" = "$CURRENT" ]; then
  echo "user did NOT modify — safe to auto-update"
else
  echo "user modified — needs 3-way merge"
fi
```

**Confidence:** High

---

### 5. Decision: Skip CLAUDE.md from auto-update by default (opt-in to update)

**Evidence:** cruft documentation explicitly: "Sometimes certain files just aren't good fits for updating. Such as test cases or `__init__` files." The ASTRON guide shows skip lists for project-specific files.

**Rationale:** `CLAUDE.md` is the user's primary customization surface. Auto-updating it would destroy their project description, stack, commands. Default skip list: `["CLAUDE.md", "ai/", ".env*"]`. Users can remove from skip list in `.dld-version` to receive updates.

**Confidence:** High

---

## Research Sources

- [cruft documentation](https://cruft.github.io/cruft/) — canonical pattern for template lifecycle management; `.cruft.json` manifest, `cruft update`, skip lists, GitHub Actions integration
- [react-native-community/rn-diff-purge](https://github.com/react-native-community/rn-diff-purge) — commit-anchored diff pattern; `git apply --3way` for bulk template upgrade
- [git-merge-file documentation](https://git-scm.com/docs/git-merge-file.html) — 3-way per-file merge tool built into git; exit code = conflict count; `--diff3` flag for ancestor context
- [update-yeoman-generator](https://www.npmjs.com/package/update-yeoman-generator) — `.yo-rc.json` version tracking pattern for scaffolders
- [Yeoman issue #474: Better generator update workflow](https://github.com/yeoman/yo/issues/474) — documents why naive generator re-runs break user code; origin of the "diff-and-apply" approach
- [Helm 3-way Strategic Merge Patches](https://www.elpa.dev/2025/11/02/helm-3-ways-strategic-merge-patches.html) — production pattern: user changes win for fields template didn't touch
- [cruft 3-way merge issue #181](https://github.com/cruft/cruft/issues/181) — documents known failure mode: 3-way merge fails in shallow clones; mitigation: ensure full git history
- [cruft GitHub Actions automation pattern](https://cruft.github.io/cruft/) — weekly auto-PR workflow; "accept" and "reject" PR strategy
- [Angular migration schematics](https://medium.com/ngconf/modernize-your-angular-app-with-migration-schematics-afe9ed9fa69b) — version-gated migration scripts; runs only the delta between installed and target version
- [How to write idempotent Bash scripts (HN)](https://news.ycombinator.com/item?id=20375197) — verification gate pattern; count-processed == count-total; state in files not memory
- [chezmoi daily operations](https://chezmoi.io/user-guide/daily-operations) — `chezmoi update` = git pull + apply; auto-commit/push; content-hash-based change detection

---

## Implementation Sketch (from research synthesis)

This is the architecture research supports — not a final design, but what production patterns converge on:

```
.dld-version (JSON manifest)
{
  "version": "1.3.0",
  "template_repo": "https://github.com/Ellevated/dld",
  "template_commit": "abc123...",    ← git SHA of template at install
  "installed_at": "2026-02-26",
  "skip": ["CLAUDE.md"]             ← user's opt-out list
}

upgrade script flow:
1. Read .dld-version → get BASE_COMMIT
2. git clone DLD template → get HEAD_COMMIT
3. git diff BASE_COMMIT..HEAD_COMMIT -- template/ > upgrade.patch
4. For each file in patch:
   a. Does user's file match sha256 at BASE_COMMIT? → auto-apply
   b. File is NEW in template? → auto-add
   c. File in user's skip list? → skip entirely
   d. Both changed? → git merge-file → produce conflict markers
5. Print classified summary (counts per category)
6. Confirm with user before writing anything
7. Apply changes, update .dld-version.template_commit = HEAD_COMMIT
8. Verify files_processed == total_files (gate)
```

Key open question (not research question — design question): does DLD keep a branch-per-version in the template repo (like rn-diff-purge does), or does it rely on semver git tags? Research supports either; tags are simpler for a smaller project.
