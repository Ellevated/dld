# Audit — Deep Mode (6-Persona Protocol with Phase 0)

Self-contained protocol for Deep Audit Mode. Triggered from `/retrofit` or explicit "deep audit".

---

## Purpose

Full forensic analysis of codebase by 6 specialized personas. Produces consolidated `deep-audit-report.md` for Architect recovery.

**Input:** Codebase (read-only)
**Output:** `ai/audit/deep-audit-report.md` (consolidated from 6 persona reports)

**When to use:** From `/retrofit`, "deep audit", or when comprehensive analysis is needed.

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store agent responses in orchestrator variables
⛔ NEVER pass full agent output in another agent's prompt
⛔ NEVER use TaskOutput to read agent results

✅ ALL Task calls use run_in_background: true
✅ Agents WRITE their output to ai/audit/ files
✅ File gates (Glob) verify completion between phases
✅ Orchestrator reads ONLY deep-audit-report.md at the end
```

---

## Phase 0: Codebase Inventory (Deterministic)

**Before ANY persona runs, generate deterministic inventory.**

```bash
node .claude/scripts/codebase-inventory.mjs src/ > ai/audit/codebase-inventory.json
```

This produces:
- 100% file coverage (every file listed with path, LOC, language)
- Symbol extraction (functions, classes, imports — tree-sitter or regex)
- Dependency graph (from imports)
- Stats (by_directory, largest_files, no_tests)

**Phase 0 is NON-NEGOTIABLE.** Personas receive inventory as a checklist. They do NOT search for files themselves — they work from the inventory.

**If codebase-inventory.mjs fails:** Check that target directory exists and Node.js 18+ is available. Fix and re-run. Do NOT proceed without inventory.

---

## Phase 1: Dispatch 6 Personas (Parallel, Isolated)

Each persona reads the codebase through their own lens. All run in parallel, isolated from each other.

| # | Persona | Agent | Focus | Output |
|---|---------|-------|-------|--------|
| 1 | Cartographer | `audit-cartographer` | File structure, modules, dependencies, import graph | `report-cartographer.md` |
| 2 | Archaeologist | `audit-archaeologist` | Patterns, conventions, conflicts between them | `report-archaeologist.md` |
| 3 | Accountant | `audit-accountant` | Tests, coverage, what's covered vs what's not | `report-accountant.md` |
| 4 | Geologist | `audit-geologist` | Data model, schema, migrations, types | `report-geologist.md` |
| 5 | Scout | `audit-scout` | External integrations, APIs, SDKs, configs | `report-scout.md` |
| 6 | Coroner | `audit-coroner` | Tech debt, dead code, TODO/FIXME, red flags | `report-coroner.md` |

### Dispatch Pattern

```yaml
# Read inventory first
inventory = Read ai/audit/codebase-inventory.json

# All 6 in parallel — each receives inventory as context
Task tool:
  description: "Audit: Cartographer scan"
  subagent_type: audit-cartographer
  run_in_background: true
  prompt: |
    INVENTORY: [contents of ai/audit/codebase-inventory.json]
    TARGET: [project source directory]
    Write your report to: ai/audit/report-cartographer.md

Task tool:
  description: "Audit: Archaeologist scan"
  subagent_type: audit-archaeologist
  run_in_background: true
  prompt: |
    INVENTORY: [contents of ai/audit/codebase-inventory.json]
    TARGET: [project source directory]
    Write your report to: ai/audit/report-archaeologist.md

Task tool:
  description: "Audit: Accountant scan"
  subagent_type: audit-accountant
  run_in_background: true
  prompt: |
    INVENTORY: [contents of ai/audit/codebase-inventory.json]
    TARGET: [project source directory]
    Write your report to: ai/audit/report-accountant.md

Task tool:
  description: "Audit: Geologist scan"
  subagent_type: audit-geologist
  run_in_background: true
  prompt: |
    INVENTORY: [contents of ai/audit/codebase-inventory.json]
    TARGET: [project source directory]
    Write your report to: ai/audit/report-geologist.md

Task tool:
  description: "Audit: Scout scan"
  subagent_type: audit-scout
  run_in_background: true
  prompt: |
    INVENTORY: [contents of ai/audit/codebase-inventory.json]
    TARGET: [project source directory]
    Write your report to: ai/audit/report-scout.md

Task tool:
  description: "Audit: Coroner scan"
  subagent_type: audit-coroner
  run_in_background: true
  prompt: |
    INVENTORY: [contents of ai/audit/codebase-inventory.json]
    TARGET: [project source directory]
    Write your report to: ai/audit/report-coroner.md
```

### MANDATORY WAIT

```
!!! MANDATORY: Wait for ALL 6 agents to complete before proceeding.
DO NOT start synthesis while agents are still running.
DO NOT start synthesis after first 2-3 agents — wait for ALL.
Violation of this rule invalidates the entire audit output.
```

**⏳ FILE GATE:** Wait for ALL 6 completion notifications, then verify:
```
Glob("ai/audit/report-*.md") → must find 6 files
If < 6: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

---

## Phase 2: Coverage Verification (Gate)

After ALL 6 reports exist, run coverage check:

```bash
node .claude/scripts/validate-audit-coverage.mjs ai/audit/codebase-inventory.json ai/audit/
```

**PASS (>= 80% files covered):** Proceed to Phase 3.

**FAIL (< 80% files covered):** The script reports which files were missed and which directories are under-covered. Re-dispatch ONLY the personas responsible for those areas with explicit instructions to cover missed files.

---

## Phase 3: Synthesis

Dispatch synthesizer to read all 6 reports + inventory and produce consolidated report.

```yaml
Task tool:
  description: "Audit: Synthesizer"
  subagent_type: audit-synthesizer
  run_in_background: true
  prompt: |
    Read ALL of these files:
    - ai/audit/codebase-inventory.json
    - ai/audit/report-cartographer.md
    - ai/audit/report-archaeologist.md
    - ai/audit/report-accountant.md
    - ai/audit/report-geologist.md
    - ai/audit/report-scout.md
    - ai/audit/report-coroner.md

    Synthesize into: ai/audit/deep-audit-report.md
    Follow the template in your agent prompt EXACTLY.
```

**⏳ FILE GATE:** Verify `ai/audit/deep-audit-report.md` exists.
**Orchestrator reads ONLY `deep-audit-report.md`** for the final result.

---

## Phase 4: Structural Validation (Gate)

```bash
node .claude/scripts/validate-audit-report.mjs ai/audit/deep-audit-report.md
```

**PASS:** Deep audit complete. Report is ready for Architect.

**FAIL:** Script reports missing sections or empty content. Re-run synthesizer with specific instructions to fill gaps.

---

## Output

```
ai/audit/
  codebase-inventory.json   (Phase 0 — deterministic)
  report-cartographer.md    (persona 1)
  report-archaeologist.md   (persona 2)
  report-accountant.md      (persona 3)
  report-geologist.md       (persona 4)
  report-scout.md           (persona 5)
  report-coroner.md         (persona 6)
  deep-audit-report.md      (synthesizer — consolidated)
```

---

## Coverage Requirements (Anti-Corner-Cutting)

**Per persona — minimum operations (for ~10K LOC project):**

| Persona | Min Reads | Min Greps | Min Findings | Evidence Rule |
|---------|-----------|-----------|-------------|---------------|
| Cartographer | 20 files | 5 | 15 | file:line for each |
| Archaeologist | 25 files | 10 | 12 | file:line + quote |
| Accountant | 15 files | 5 | 10 | file:line + quote |
| Geologist | 15 files | 8 | 10 | file:line + quote |
| Scout | 10 files | 5 | 8 | file:line + quote |
| Coroner | 20 files | 10 | 15 | file:line + quote |

**Scaling:** For 30K+ LOC, multiply minimums by 2-2.5x.

**Quote-before-claim (mandatory in all persona prompts):**
```
Before making ANY claim about the code:
1. Quote the relevant lines (exact text from Read)
2. State file:line reference
3. THEN make your claim
4. Explain how the quote supports your claim
```

---

## After Deep Audit

```
ai/audit/deep-audit-report.md  ✓

From /retrofit → Next: /architect (retrofit mode — uses audit report as primary input)
Standalone    → Next: Create TECH/BUG specs for critical findings
```
