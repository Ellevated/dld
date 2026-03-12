# TOC Experiment #3: v3 Corrected Multi-Agent Analysis

**Date:** 2026-02-13
**Bug:** BUG-477 (buyer flow breaks)
**Round:** 3 (corrected v3 run)

## Setup

v3 corrected = v3 with three fixes applied:
1. `Task` added to spark.md tools
2. Custom agents `toc-analyst` and `code-auditor` in `.claude/agents/`
3. Methodology as system prompt in agent files

## Critical Finding: Subagents Launched in Degraded Mode

From conversation log analysis:

```
1. Spark reads toc-layer.md                              ✅
2. Spark attempts Task(subagent_type="toc-analyst")      ❌ "Not found"
3. Spark reads agent prompts manually                    ✅ smart fallback
4. Spark launches 2x Task(general-purpose, prompt=...)   ✅ workaround
5. Both agents work (11 + 12 tool uses, 53K + 67K tok)   ✅ actually ran
6. Merge → spec without CRT structure                    ⚠️ degradation
```

### Root Cause of "Not Found"

Custom agents in `.claude/agents/` are loaded at SESSION START.
The agent files were written to Awardybot filesystem but the session
may have started before or simultaneously with the file writes.

Documentation says: "Subagents are loaded at session start. Use /agents to reload."

### Evidence from Log

- Error message lists available agents — toc-analyst NOT in list
- Spark CAN read the files (Read 2 files) — files exist on disk
- But they're NOT registered as subagent_type
- Spark falls back to general-purpose with methodology in prompt

### Impact on Results

v3 corrected found 6 issues (vs 3-5 vanilla, 10 multi-pass, 4 CRT v1).
Better than vanilla but without CRT structure:
- No UDEs, no causal chains, no convergence
- No adversarial challenges from Code Auditor
- No evidence typing (CODE/HYPOTHESIS)
- Spec looks like "good vanilla", not like TOC analysis

## v4 Plan

Fix: Commit agent files BEFORE starting session → agents load at startup.
Improvements:
- effort: high for toc-analyst (deeper causal reasoning)
- toc-layer.md: explicit "preserve CRT structure" instruction
- toc-layer.md: troubleshooting section (don't fall back to general-purpose)

## Mega-Table: 3 Rounds, 10 Runs, 22 Unique Issues

### Methodology Overview

| Code | Round | Method | Issues Found |
|------|-------|--------|:------------:|
| R1:O | 1 | Original spark | 5 |
| R1:V | 1 | Vanilla (5 Whys) | 4 |
| R1:T | 1 | Multi-pass (original TOC) | 10 |
| R2:V | 2 | Vanilla (5 Whys) | 3 |
| R2:C | 2 | CRT single-agent (TOC v1) | 4 |
| R2:M | 2 | Multi-pass (FAKE) | 10 |
| R3:V | 3 | Vanilla (5 Whys) | 4 |
| R3:C | 3 | CRT single-agent (TOC v1) | 4 |
| R3:b | 3 | v3 broken | 5 |
| R3:c | 3 | v3 corrected (degraded) | 6 |

### Key Statistics

- 22 unique issues found total across all runs
- Multi-pass finds 10 (45%), CRT finds 4 (18%), Vanilla finds 3-5 (14-23%)
- CRT ∩ Multi-pass = 0 (ZERO overlap between methodologies!)
- Within-methodology reproducibility = ~100%
- To cover >80% need ALL THREE approaches

### Reproducibility

- Multi-pass: identical 10/10 issues in R1 and R2
- CRT v1: identical 4/4 issues in R2 and R3
- Each methodology stably "sees" its own cluster

### Unique Findings by Methodology

- ONLY CRT finds: Reply KB interrupts flow (#1 system constraint), nav:back gaps, error:retry wrong target
- ONLY Multi-pass finds: pending_review/rejection no KB, flickering, DB queries, keyboard inconsistency, progress bar, search migration
- ONLY Vanilla finds: missing send_proof button, CTA hint

## Conclusions

1. CRT and Multi-pass find COMPLETELY DIFFERENT bug clusters (zero overlap)
2. CRT finds fewer bugs but at SYSTEM level (the constraint)
3. Multi-pass finds more bugs but at UI/code level
4. v3 corrected was degraded (general-purpose fallback) — needs v4 with proper registration
5. The real test (v4) will show if proper subagent dispatch + CRT preservation works
