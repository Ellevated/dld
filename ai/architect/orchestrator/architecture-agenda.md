# Architecture Agenda: Multi-Project Orchestrator

**Date:** 2026-03-10
**Scope:** VPS-based orchestrator managing N projects via single Telegram supergroup + optional GitHub Issues integration
**Input:** `ai/architect/multi-project-orchestrator.md` (existing spec), Сережа Рис articles (GitHub Issues as agent interface), existing System Blueprint (Morning Briefing product)

---

## Problem Statement

Solo founder manages 2-5 projects in parallel from a single VPS. Each project has its own DLD lifecycle (inbox → spark → autopilot → QA). Need a unified orchestrator that:
1. Routes messages (text/voice/screenshots) to correct project
2. Manages Claude CLI concurrency (limited by VPS RAM)
3. Provides status/control per project
4. Stores and retrieves project context for agents

**Key tension:** Existing spec uses Telegram topics for routing. Сережа Рис advocates GitHub Issues as the canonical interface for AI agents (structured, version-controlled, API-native). Which is the right primary interface? Hybrid?

---

## Persona Focus Areas

### 1. Domain Architect (Eric)
- What are the bounded contexts? Is "orchestrator" a domain or infrastructure?
- Relationship between orchestrator and individual project DLD instances
- Domain events: what crosses project boundaries?
- Is there a "portfolio" domain (cross-project prioritization, dependencies)?
- Ubiquitous language: project, workspace, topic, inbox, pipeline

### 2. Data Architect (Martin)
- `projects.json` schema design — is JSON file sufficient or need SQLite?
- State management: `.orchestrator-state.json` vs DB
- Inbox storage: per-project `ai/inbox/` vs centralized
- How does project context flow between orchestrator and DLD instance?
- Voice transcription storage, screenshot storage
- GitHub Issues as data layer (pinned issue = project context, comments = history)

### 3. Ops / Observability (Charity)
- VPS resource management: RAM per Claude process, semaphore implementation
- Monitoring: how do you know the orchestrator itself is healthy?
- Dead man's switch for the orchestrator (not just individual briefings)
- Log aggregation across N projects
- Restart recovery: what happens when VPS reboots mid-autopilot?
- Backup strategy for project state

### 4. Security Architect (Bruce)
- Telegram bot security: who can send commands? Admin validation
- Project isolation: can a bug in project A affect project B?
- Secret management: per-project `.env` vs shared secrets
- Claude CLI sandboxing across projects
- GitHub token scope management
- Voice/screenshot data handling (PII in transcriptions?)

### 5. Evolutionary Architect (Neal)
- Fitness functions for the orchestrator (max latency, resource utilization)
- Migration path from current single-project VPS to orchestrated multi-project
- What changes when going from 2 to 10 projects? Scaling inflection points
- Config hot-reload: inotifywait vs polling vs file watch
- Versioning the orchestrator itself (upgrading without downtime)

### 6. DX / Pragmatist (Dan)
- Shell script orchestrator vs Node.js vs Python — what's the boring choice?
- Developer experience of adding a new project (steps, time, friction)
- How does the founder debug a stuck project?
- CLI ergonomics: is Telegram the right control plane or is SSH + tmux simpler?
- Pueue / Task Spooler / systemd — existing tools vs custom orchestrator

### 7. LLM Architect (Erik)
- Claude CLI concurrency model: how many simultaneous sessions?
- Context isolation between projects: does Claude Code handle this natively?
- Agent Teams (Opus 4.6) — can teammates span projects?
- How does the orchestrator pass project context to Claude?
- `--max-turns` and `timeout` tuning per project priority
- Inbox processing: Claude for triage/routing or rule-based?

### 8. Devil's Advocate (Fred)
- Is this over-engineered for 2-3 projects? Would tmux + cron suffice?
- Telegram dependency: what if Telegram API changes/blocks bots?
- Does Сережа Рис's GitHub Issues approach make the Telegram layer unnecessary?
- Concurrency problem: is flock the right primitive or will it deadlock?
- What fails first at 3am with no one watching?
- Single VPS = single point of failure. Is that acceptable?

---

## Key Questions for ALL Personas

1. **Telegram topics vs GitHub Issues vs hybrid** — which is the primary interface for the founder? For the agents?
2. **Shell vs application** — bash orchestrator.sh or a proper application (Node.js/Python)?
3. **State storage** — JSON files vs SQLite vs GitHub Issues (as state store)?
4. **Concurrency** — flock semaphore vs proper job queue (BullMQ/Pueue)?
5. **Scope** — orchestrator manages DLD projects only, or any project with Claude Code?
6. **Multi-LLM orchestration** — not just Claude Code, also ChatGPT Codex (GPT-5.4). How to manage heterogeneous agents?
7. **Infrastructure topology** — same VPS running Docker containers for projects + orchestrator, or dedicated orchestrator VPS?
8. **Practical setup** — what to install, configure, how to bootstrap from zero?

---

## Founder Addendum (Phase 1 update)

**Added after initial research launch. ALL personas MUST address in Phase 3 cross-critique.**

### Multi-LLM: Claude Code + ChatGPT Codex (GPT-5.4)
- Founder wants to run BOTH Claude Code and Codex on the same orchestrator
- GPT-5.4 "очень хорошо кодит" — different strengths per task type
- Questions: same project can use both? Task routing by model? Separate queues?
- Codex CLI vs Claude CLI — different invocation patterns, different auth, different resource profiles
- How does concurrency work with two different LLM CLI tools?

### Infrastructure Topology
- Founder already runs Docker containers for projects on VPS
- Can orchestrator run on the SAME VPS as project containers?
- Resource contention: Docker containers + Claude CLI + Codex = how much RAM?
- Or: dedicated lightweight VPS for orchestrator only, separate from project hosting?
- Cost implications: 1 beefy VPS ($40-80/mo) vs 2 smaller VPS ($20-40/mo each)

### Practical Bootstrap
- What does "day 1 setup" look like?
- Install script, systemd services, config generation
- How to add a new project in under 5 minutes

---

## External Research Required

- GitHub Copilot Coding Agent architecture (how does it use Issues?)
- Spec Kit (open-source, 20+ agent support)
- Pueue vs Task Spooler vs custom queue
- Telegram Bot API Forum mode edge cases
- VPS resource profiling for Claude CLI processes
- ChatGPT Codex CLI resource usage and invocation patterns
- tmux/screen scripting as alternative
- GitHub Actions for self-hosted runners (agent execution)
- Multi-LLM orchestration patterns (running Claude + Codex side by side)

---

## Constraints from Business Blueprint

- Solo founder, 2-5 projects in parallel
- Revenue focus — orchestrator is tooling, not product
- Phase 1 (now): consulting IP. Phase 2: morning briefing product
- Max budget for VPS: $50-100/month (Hetzner/DigitalOcean class)
- Must work with existing DLD framework (spark, autopilot, etc.)
