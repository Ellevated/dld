# Architecture Decision: Multi-Project Orchestrator

**Date:** 2026-03-10
**Chosen:** Alternative B — Boring Stack (Pueue + Telegram Bot + SQLite)
**Rejected:** A (too manual), C (over-engineered for 2-3 projects)
**Founder approved:** 2026-03-10

---

## Why B

- Unattended execution needed (founder manages 2-5 projects)
- Mobile control via Telegram topics (founder is mobile-first)
- Multi-LLM ready (Claude Code + ChatGPT Codex GPT-5.4)
- Phase-gated build — can stop at day 3 with working system
- 0.5 innovation tokens (only Telegram bot is custom code)
- Migration path to C (Docker) if production containers appear on same VPS

## Key Architecture Decisions

1. **Pueue** replaces custom bash orchestrator (~300 LOC eliminated)
2. **SQLite WAL** for runtime state (not JSON — GitHub #29158 evidence)
3. **`run-agent.sh`** → provider-specific runners (Claude + Codex abstraction)
4. **`CLAUDE_CODE_CONFIG_DIR`** per project (cross-session contamination fix)
5. **Project-level LLM routing** in v1, task-level deferred
6. **Inbox path:** `{project_path}/ai/inbox/` (standard DLD convention)
7. **Spark summary in Telegram** before autopilot — founder validates understanding
8. **`auto_approve_timeout`** per project (0 = always wait, 60 = auto after 1 min)

## VPS

- 32GB minimum for Claude + Codex ($35/mo Hetzner)
- Same VPS as project repos (no Docker containers for now)
- systemd for process management, `MemoryMax=27G`, `KillMode=control-group`

## Build Phases

| Phase | Days | What | Gate |
|-------|------|------|------|
| 1 | 1-3 | Pueue + systemd + Telegram bot + SQLite | Bot responds to /status |
| 2 | 4-5 | RAM floor gate + heartbeat + run-agent.sh | Heartbeat 24h clean |
| 3 | 6-7 | P0 security + Codex runner + voice inbox | /addproject creates full project |

## Additions from founder review

- Spark summary displayed in Telegram topic before autopilot starts
- Founder can approve, reject, or let timeout auto-approve
- `auto_approve_timeout` configurable per project in projects.json

## Source

- Full architectures: `ai/architect/orchestrator/architectures.md`
- Research: `ai/architect/orchestrator/research-*.md` (8 files)
- Critiques: `ai/architect/orchestrator/critique-*.md` (8 files)
