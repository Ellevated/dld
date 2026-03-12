# TECH-129: Multi-Agent ADR Migration — Zero-Read Pattern для всех pipeline-скиллов

**Status:** done | **Priority:** P1 | **Date:** 2026-02-18

## Why

Шесть multi-agent скиллов не следуют ADR-007/008/009/010, доказанным необходимыми через краши Bug Hunt pipeline. Council (9 агентов, ~40K), Board (13 агентов, ~80K) и Architect (17 агентов, ~100K) гарантированно крашнутся на реальных проектах из-за context overflow.

## Context

ADR-цепочка (007→008→009→010) разработана и применена ТОЛЬКО к Bug Hunt (bug-mode.md). Остальные скиллы были созданы ДО появления ADR и никогда не ретрофичены.

**Evidence:**
- Bug Hunt Run 1: Steps 0-5 OK, Step 6 crash (~50-90K accumulated)
- Bug Hunt Run 2: Step 1 crash — 12 TaskOutput calls flooded context
- Bug Hunt Run 3: collector overflow на 22 файлах (~670KB)
- Итог: 3 прогона, 3 разных типа краша — все из-за отсутствия ADR

**ADR Reference:**
- ADR-007: Caller-Writes — субагенты НЕ пишут файлы (0/36 success). Caller пишет.
- ADR-008: Background Fan-Out — `run_in_background: true` предотвращает context flooding.
- ADR-009: Background ALL Steps — ВСЕ шаги в background, не только параллельные.
- ADR-010: Zero-Read — оркестратор НИКОГДА не читает output агентов.

---

## Scope

**In scope:** Миграция 6 скиллов на ADR-compliant паттерн.

**Out of scope:** Autopilot task loop (1 task/time, acceptable scale).

---

## Severity Map

| Скилл | Агентов | Ожидаемый контекст | Risk |
|-------|---------|-------------------|------|
| **Council** | 9 (4+4+1) | ~40K | CRITICAL |
| **Board** | 13 (6+6+1) | ~80K | CRITICAL |
| **Architect** | 17 (8+8+1) | ~100K | CRITICAL |
| **Spark Feature** | 4-5 | ~20K | MEDIUM |
| **Audit Deep** | 7 | ~25K (synth foreground) | MEDIUM |
| **TRIZ** | 4 | ~25K | MEDIUM |

---

## Uniform Fix Pattern

### Anti-pattern (текущее состояние):

```yaml
Task:
  subagent_type: council-architect
  prompt: |
    Analyze: [spec_content]
# Response хранится в переменной оркестратора → context floods
```

### ADR-compliant pattern:

```yaml
Task:
  subagent_type: council-architect
  run_in_background: true
  prompt: |
    Analyze: [spec_content]
    OUTPUT_FILE: {SESSION_DIR}/phase1/analysis-architect.yaml
# Response → temp file → оркестратор получает ~50 токенов
```

### Для synthesis (ADR-010):

**Before:** Synthesizer получает ВСЕ анализы в промпте (40-100K)
**After:** Synthesizer ЧИТАЕТ файлы сам (у него есть Read tool)

```yaml
Task:
  subagent_type: council-synthesizer
  run_in_background: true
  prompt: |
    Read these files from {SESSION_DIR}/:
    - phase1/analysis-architect.yaml
    - phase1/analysis-product.yaml
    ... (synthesizer читает сам)
    OUTPUT_FILE: {SESSION_DIR}/synthesis.yaml
```

### Для cross-critique:

**Before:** Каждый эксперт получает 5-7 полных peer reports В ПРОМПТЕ
**After:** Каждый эксперт ЧИТАЕТ anonymous файлы сам

```yaml
Task:
  subagent_type: board-cpo
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    YOUR_RESEARCH: {SESSION_DIR}/phase1/research-cpo.md
    PEER_DIR: {SESSION_DIR}/phase1/anonymous/
    Read files: peer-A.md through peer-E.md
    OUTPUT_FILE: {SESSION_DIR}/phase2/critique-cpo.md
```

### File Gate Pattern (между фазами):

```
1. Launch N background agents
2. Wait for completion notifications (automatic)
3. Glob("{SESSION_DIR}/phase1/*.yaml") → count >= N?
4. If missing files → launch extractor subagent (caller-writes fallback)
5. Proceed to next phase
```

---

## Changes Per Skill

### 1. Council (CRITICAL) — `council/SKILL.md`

**SESSION_DIR:** `ai/.council/{YYYYMMDD}-{spec_id}/`

| Phase | Current | Fix |
|-------|---------|-----|
| Phase 1 (4 experts) | Foreground, vars | `run_in_background: true`, write to phase1/ |
| Phase 2 (4 critics) | Foreground, full content in prompt | `run_in_background: true`, READ anonymous files |
| Phase 3 (synthesizer) | Foreground, ALL 8 in prompt | `run_in_background: true`, READ files self |
| Storage | "Store in variables" | File IPC + file gates |

**Key changes:**
- Add session dir computation block
- Remove lines 190, 248 ("Store results in variables")
- Phase 1: add `run_in_background: true` × 4, add `OUTPUT_FILE:` to each prompt
- Phase 2: add `run_in_background: true` × 4, replace inline content with READ instructions
- Add anonymous label shuffling step between Phase 1 and Phase 2
- Phase 3: add `run_in_background: true`, replace inline content with READ instructions
- Add file gate after each phase
- Add FORBIDDEN ACTIONS block (copy from bug-mode.md)

### 2. Board Greenfield (CRITICAL) — `board/greenfield-mode.md`

**SESSION_DIR:** `ai/board/` (existing paths, add subfolder for anonymous)

| Phase | Current | Fix |
|-------|---------|-----|
| Phase 2 (6 directors) | Foreground | `run_in_background: true`, file gates |
| Phase 3 (6 critics) | Foreground, content in prompt | `run_in_background: true`, READ files |
| Phase 4 (synthesizer) | Foreground | `run_in_background: true`, READ files |
| Phase 6 (iterate) | Same problems | Same fixes per round |

**Key changes:**
- Phase 2: add `run_in_background: true` × 6
- Add file gate: 6 research-*.md files exist
- Add caller-writes fallback
- Phase 3: add `run_in_background: true` × 6, directors READ anonymous files
- Phase 4: add `run_in_background: true`, synthesizer reads files self
- Add FORBIDDEN ACTIONS block

### 3. Architect Greenfield (CRITICAL) — `architect/greenfield-mode.md`

**SESSION_DIR:** `ai/architect/` (existing paths)

Same as Board but 8 personas:
- Phase 2: `run_in_background: true` × 8 + file gates
- Phase 3: `run_in_background: true` × 8 + anonymous file reads
- Phase 4: `run_in_background: true` + synthesizer self-reads
- Phase 6: iterate with same pattern
- Add FORBIDDEN ACTIONS block

### 4. Spark Feature (MEDIUM) — `spark/feature-mode.md`

| Phase | Current | Fix |
|-------|---------|-----|
| Phase 2 (4 scouts) | No background flag | `run_in_background: true`, file gates |
| Phase 3 (synthesis) | Orchestrator reads 4 responses | Acceptable (~20K), or background synth |

**Key changes:**
- Phase 2: add `run_in_background: true` × 4
- Add file gate: 4 research-*.md files exist
- Add caller-writes fallback
- Phase 3: orchestrator reads 4 files (~5K each = ~20K) — acceptable for now

### 5. Audit Deep (MEDIUM) — `audit/deep-mode.md`

Already partially correct. Fix:
- Line 122: replace "poll output files" with file gate (Glob for 6 files)
- Phase 3: add `run_in_background: true` to synthesizer Task
- Add caller-writes fallback for all personas + synthesizer
- Orchestrator reads ONLY final report (deep-audit-report.md)

### 6. TRIZ (MEDIUM) — `triz/SKILL.md`

| Phase | Current | Fix |
|-------|---------|-----|
| All 4 phases | No background | `run_in_background: true`, file gates |

**Key changes:**
- Add `run_in_background: true` to all 4 Task calls
- Add file gate between each phase (Glob for output file)
- Add caller-writes fallback
- Phase 4 synthesizer already reads files via paths (good)

---

## Allowed Files

**Template first (template-sync rule), then sync to root:**

1. `template/.claude/skills/council/SKILL.md` — full ADR migration
2. `template/.claude/skills/board/greenfield-mode.md` — full ADR migration
3. `template/.claude/skills/architect/greenfield-mode.md` — full ADR migration
4. `template/.claude/skills/spark/feature-mode.md` — add background to scouts
5. `template/.claude/skills/audit/deep-mode.md` — fix synthesizer + polling
6. `template/.claude/skills/triz/SKILL.md` — add background to all phases

**Sync copies:**
7. `.claude/skills/council/SKILL.md`
8. `.claude/skills/board/greenfield-mode.md`
9. `.claude/skills/architect/greenfield-mode.md`
10. `.claude/skills/spark/feature-mode.md`
11. `.claude/skills/audit/deep-mode.md`
12. `.claude/skills/triz/SKILL.md`

---

## Implementation Plan

### Task 1: Council SKILL.md — full ADR migration
**Files:** modify `template/.claude/skills/council/SKILL.md`
- Add FORBIDDEN ACTIONS block
- Add session dir computation
- Phase 1: 4 background experts + OUTPUT_FILE + file gates
- Phase 2: 4 background critics + anonymous file reads + file gates
- Phase 3: background synthesizer + self-reads files
- Remove variable storage pattern

### Task 2: Board greenfield-mode.md — full ADR migration
**Files:** modify `template/.claude/skills/board/greenfield-mode.md`
- Add FORBIDDEN ACTIONS block
- Phase 2: 6 background directors + file gates + caller-writes
- Phase 3: 6 background critics + anonymous file reads + file gates
- Phase 4: background synthesizer + self-reads

### Task 3: Architect greenfield-mode.md — full ADR migration
**Files:** modify `template/.claude/skills/architect/greenfield-mode.md`
- Add FORBIDDEN ACTIONS block
- Phase 2: 8 background personas + file gates + caller-writes
- Phase 3: 8 background critics + anonymous file reads + file gates
- Phase 4: background synthesizer + self-reads

### Task 4: Spark feature-mode.md — add background to scouts
**Files:** modify `template/.claude/skills/spark/feature-mode.md`
- Phase 2: 4 background scouts + file gates
- Add caller-writes fallback

### Task 5: Audit deep-mode.md — fix synthesizer + polling
**Files:** modify `template/.claude/skills/audit/deep-mode.md`
- Remove "poll output files" language
- Phase 3: background synthesizer
- Add caller-writes fallback

### Task 6: TRIZ SKILL.md — add background to all phases
**Files:** modify `template/.claude/skills/triz/SKILL.md`
- All 4 phases: background + file gates
- Add caller-writes fallback

### Task 7: Sync template to root
**Files:** copy 6 files from template/ to root .claude/

### Execution Order
1 → 2 → 3 → 4 → 5 → 6 → 7

---

## Tests

### Structural Validation
- [ ] All 6 template skills have FORBIDDEN ACTIONS block
- [ ] All Task examples contain `run_in_background: true`
- [ ] No skill contains "Store results in variables" pattern
- [ ] All skills have file gate instructions between phases
- [ ] No synthesis step receives full peer content in prompt
- [ ] Cross-critique uses anonymous labels (A/B/C, not role names)
- [ ] Caller-writes fallback documented

### Grep Verification
- [ ] `grep -r "run_in_background" template/.claude/skills/` → all 6 skills
- [ ] `grep -r "Store results in variables" template/.claude/skills/` → 0 results
- [ ] `grep -r "FORBIDDEN ACTIONS" template/.claude/skills/` → all 6 skills
- [ ] `grep -r "file gate" template/.claude/skills/` → all 6 skills

---

## Definition of Done

- [ ] All 6 skills have FORBIDDEN ACTIONS block (ADR-010)
- [ ] All Task calls have `run_in_background: true`
- [ ] No skill stores agent responses in orchestrator variables
- [ ] All skills use file gates between phases
- [ ] All synthesis steps tell synthesizer to READ files (not receive in prompt)
- [ ] Cross-critique phases use anonymous file labels
- [ ] Caller-writes fallback documented in each skill
- [ ] Template → root sync complete (6 files)
- [ ] Grep verification passes (4 checks)
