---
paths:
  - ".claude/**"
  - "template/**"
---

# Template Sync Rule

## Two Copies of .claude/

DLD has TWO places with skills/agents/hooks:

```
template/.claude/   ← Universal (for all DLD users)
.claude/            ← DLD-specific (template + customizations)
```

## When Modifying .claude/ Files

**STOP and ask:** Is this universal or DLD-specific?

| Type | Where to edit | Then |
|------|---------------|------|
| **Universal improvement** | `template/.claude/` first | Cherry-pick to `.claude/` |
| **DLD-specific** | `.claude/` only | Document in CUSTOMIZATIONS.md |

## Examples

**"Improve spark prompt"** → Universal
1. Edit `template/.claude/skills/spark/SKILL.md`
2. Then sync to `.claude/skills/spark/SKILL.md`

**"Add Russian triggers"** → DLD-specific
1. Edit only `.claude/rules/localization.md`
2. Don't touch template

## Quick Check

Before editing any file in `.claude/`:

```
Does template/.claude/ have this file?
├─ YES → Edit template first, then sync
└─ NO  → It's a customization, edit .claude/ only
```

## Files Only in Root (Customizations)

- `rules/localization.md` — Russian skill triggers
- `rules/template-sync.md` — This file (DLD dual-repo sync policy)
- `settings.local.json` — Local dev settings
- `skills/scaffold/SKILL.md` — Skill generator
- `hooks/hooks.config.local.mjs` — DLD-specific hook overrides (excludeFromSync)
- `scripts/check-tree-sync.py` — compares the two trees' function bodies and reports what was
  fixed in one only. Root-only by nature: a downstream project has a single `.claude/` and
  nothing to compare it against.
- `scripts/eval-agents.mjs` — feeds root's `/eval` over `test/agents/` golden datasets.
  Not the same tool as template's `scripts/run-eval.mjs`, which runs a *skill* against
  `evals.json`; the similar names have already caused one "isn't this a rename?"

These are NOT in template — edit directly in `.claude/`.

## Files Only in Template (deliberately not ported to root)

Root prompts reference these paths, so their absence is a decision, not a gap. Recorded
2026-07-31 when the other six template-only scripts were ported.

- `scripts/ci-status.sh` — a stub that prints OK and **always exits 0**. Root DLD has four
  real workflows in `.github/workflows/`, so copying the stub would manufacture a green CI
  signal on the one path that exists to catch a broken deploy. `ci-status.sh` and `./test`
  are per-project artifacts by design (TECH-206: "awardybot has them; dld does not").
  Both copies of `skills/autopilot/{autopilot-git,worktree-setup}.md` now define the
  missing-script case: log `CI_STATUS_UNAVAILABLE`, continue, never treat it as exit 2.
- `.claude/scripts/improve-description.mjs` — its accuracy metric counts word overlap
  between query and description rather than testing trigger activation (its own comment
  says so), and it accepts rewrites that raise that proxy while telling the model to add a
  "Triggers on keywords:" line. The loop optimises keyword stuffing. Both copies of
  `skills/skill-creator/SKILL.md` now say so and give the manual procedure instead.
- `.claude/scripts/validate-spec-structure.mjs` — template-only and referenced by nothing
  in root. Not assessed; left alone rather than ported blind.
- `.claude/hooks/__tests__/` — ten node test files covering the hooks, template-only. Root runs
  the same hooks with **no** tests over them. Found 2026-08-28 while closing the debug-layer
  divergence; recorded rather than ported because the suite currently fails one case on
  Windows (`getProjectDir` asserts a `/tmp` path), so porting it blind would hand root a red
  suite. `scripts/check-tree-sync.py` does not catch gaps of this shape — it compares functions
  in files that exist in **both** trees, and a file present in only one is exactly what this
  section is for.

## Files in Both, but Root Has DLD-Specific Extensions

These files exist in template AND root. Template has the baseline, root adds DLD-specific content.
**`/upgrade` will NOT overwrite them** — but only because `/upgrade` is now manual cherry-pick. The auto-apply `upgrade.mjs` was deleted 2026-05-25 after it overwrote these files in awardybot/dowry despite a PROTECTED filter. See `.claude/skills/upgrade/SKILL.md` for the manual flow.

- `rules/architecture.md` — Template carries ADR-001..014. Root adds **ADR-015..030** plus the
  `TECH-*` orchestrator rows, and shell-script safety rules. ADR-014 exists in **both** trees
  and names a **different** decision in each — see the collision section below.
- `rules/dependencies.md` — Root has full DLD dependency map (scripts/vps/*, orchestrator, callback)
- `rules/model-capabilities.md` — **the two bodies deliberately differ since 2026-07-31.**
  The byte-identical invariant was dropped: root's copy documents DLD's own runner
  (`claude-runner.py` refusal handling, exit codes, telemetry tables, the Fable-5 routing
  decision and its ADR trail), none of which a downstream project has. Template carries
  16.6 KB against root's 21.6 KB.

  **What to sync:** facts about the models — prices and the Sonnet intro-price expiry,
  context/output windows, effort levels, knowledge cutoffs, the "what to remove from
  prompts" table, both Breaking Changes tables, refusal semantics as an API behaviour.
  A model fact that is true for us is true for everyone.

  **What not to sync:** anything naming our runner, orchestrator, env vars, spec ids or
  internal documents. If a lesson behind one of those is worth carrying, port the lesson
  in words — the same rule as the id-stripping entry below.

  Root's `paths:` header also covers `template/**` and `scripts/vps/*`, because DLD edits
  both trees; template's covers only its own `.claude/agents/**` and `.claude/skills/**`.
- **LLM-Native economics wording**, in `agents/board/{cmo,coo}.md`,
  `agents/architect/{dx,evolutionary,synthesizer}.md` — root states it as a fact about this
  repo ("this codebase is maintained by AI agents … MUST reflect this reality"); template
  hedges for downstream users ("For human teams, include both"). Deliberate: DLD has no human
  implementers, a template user might.
- `agents/architect/synthesizer.md` — template carries an extra "Effort Estimate" section.
- `agents/tester.md` — root's "Mock Fidelity Audit" heading cites `(ADR-030)`, template's
  cites `(ADR-014)`. Same rule, different id per tree — see the ADR-014 collision below.
  Bodies are otherwise identical.
- `skills/council/SKILL.md`, `skills/architect/SKILL.md` — both trees now write
  `**Status:** draft` and agree on the contract; the **wording** differs on purpose, because
  the two trees can resolve different references:
  - root cites ADR-022 by number and links `ai/inbox/README.md`. Template does neither —
    its ADR table stops at ADR-014, and it ships no `ai/inbox/README.md`, so both would
    dangle. Template states the rule in its own terms instead.
  - template adds "create `ai/inbox/` if it does not exist" and an opening line marking the
    section optional. A template-derived project has no `ai/inbox/` in its scaffold and may
    never be scanned by an orchestrator; root always is.

  Keep the *contract* identical when either side changes — `draft`, never `queued`; the
  intake supervisor is the only promoter. Let the *citations* stay different.
- **Template prompts carry no DLD spec ids.** Root cites `ADR-`/`TECH-`/`ARCH-` numbers
  freely; template states the same rules in words. 43 citations were stripped from 13 files
  on 2026-07-31 — a downstream project has neither DLD's ADR table nor its backlog, and its
  own `TECH-NNN` numbering will collide. When porting root→template, drop the id and keep
  the rule. The one remaining exception is illustrative placeholders — example commit
  subjects, example invocations, sample finding ids — where the number is the point of the
  example. `rules/model-capabilities.md` was the second exception until 2026-07-31, when the
  byte-identical invariant was dropped and its four citations went with the DLD-specific
  sections; see its entry above.

Found by audit 2026-07-27, not by anyone noticing. Undocumented divergence is
indistinguishable from an interrupted sync — record it here when you create it.

- `.claude/scripts/validate-allowlist.mjs`, `check-prompt-integrity.mjs` — **logic
  identical, header comments differ.** Root's cite `callback.py` / `gate_logic.py` line
  numbers and the parity test that binds them; template's state the same rule without
  naming files a downstream project does not have (it ships no `scripts/vps/`). Keep the
  regexes and the checks byte-identical; only the prose that names our parser diverges.
  `prompt-integrity-baseline.json` differs on purpose — root baselines DLD's own
  decisions, template ships only the one that is universal.

## Known dangling reference in template

`template/.claude/skills/spark/feature-mode.md` Phase 5 tells the agent to run
`from scripts.vps.lifecycle import create_initial` — and `scripts/vps/` does not exist in
the template tree. Same class as the six scripts ported on 2026-07-31, found 2026-08-01
while replacing the Phase 5.5 linter. Not fixed: porting the lifecycle module downstream
is a real design decision (a template project may have no orchestrator at all), and the
alternative is rewriting Phase 5's ID-claim protocol in tree-agnostic terms. Recorded
here so the next reader does not rediscover it.

`check-prompt-integrity.mjs` does not currently catch it — the reference is a Python
import, not a shell invocation, and the check is deliberately anchored on interpreters to
keep its false-positive rate near zero. An import-shaped check is a reasonable extension.

## ADR-014 means two different things in the two trees

Not a divergence to preserve — a collision to be aware of before citing the number.

| Tree | ADR-014 |
|---|---|
| `template/.claude/rules/architecture.md:76` | Mock boundary rule for unit tests |
| `.claude/rules/architecture.md:95` | Data Architect gets agenda priority in `/architect` |

Template's ADR table ends at 014. Root continued its own numbering from 014 onward, so the
number was reused and the mock-boundary decision was never carried into root's table at all.

**Resolved 2026-07-30 — the mock rule now has its own root id, ADR-030.** Nothing was
renumbered: root's existing 014 keeps its meaning, and the rule template numbered 014 was
added to root's table at the next free id. `agents/coder.md` and `agents/tester.md` cite
`ADR-030` and resolve correctly. The two trees still disagree on what "ADR-014" names, so
**cite by meaning when crossing trees, never by number alone** — that is what the table
above is for.

The `rules/architecture.md` line above used to read "Root adds ADR-015..018" — stale on the
range, and silent on the fact that 014 exists in both trees under different meanings. That
silence is how the collision stayed invisible; the line now states both.

When template updates these files, manually merge changes into root.

## Deleted Files (History)

- `rules/git-local-folders.md` — Removed in TECH-144. Was redundant with root `.gitignore`.
