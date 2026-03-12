# Board Agenda: Autonomous AI Agent Market Entry

**Date:** 2026-02-27
**Type:** Greenfield Evaluation
**Trigger:** Founder researched OpenClaw (175K GitHub stars in 2 weeks, fastest-growing OSS repo)

---

## Context: Market Signal

OpenClaw (ex-Clawdbot → Moltbot → OpenClaw) by Peter Steinberger:
- 175K stars, 20K forks in under 2 weeks
- Creator joining OpenAI (Feb 14, 2026), project → open-source foundation
- MIT license, Node.js, local-first
- 13+ messaging platforms (WhatsApp, Telegram, Discord, Slack, Signal, iMessage, Teams, Matrix...)
- Heartbeat daemon: agent wakes up every 30 min, checks HEARTBEAT.md, acts proactively
- Skills as Markdown (SKILL.md) — self-modification, hot-reload, 100+ community skills
- File-based memory (Markdown + YAML + JSONL + SQLite hybrid search)
- Device nodes (iOS/macOS/Android) — camera, SMS, shell, location
- Security issues: CVE-2026-25253 (RCE), 12-20% malicious skills on ClawHub, plaintext credentials

## Founder Profile

- Small team (2-5 people)
- Has DLD framework (multi-agent AI dev workflow, open-source)
- Strong in: business logic, product sense, systems thinking, multi-agent orchestration
- Weak in: implementation details (prefers combining proven solutions)
- Philosophy: "We don't invent, we combine what already works"
- Goal: Revenue. Clients. Money in the account.

## Founder Assets

- Deep knowledge of multi-agent patterns (DLD: spark, autopilot, council, board, architect)
- ADR-007 through ADR-010: proven patterns for agent orchestration (caller-writes, background fan-out, zero-read)
- Research on persona diversity, agent quality optimization
- Working skill/agent framework with hooks, rules, memory

---

## Questions for Each Director

### CPO (Customer Experience)
- Who is the actual user of autonomous AI agents? Developer? Non-technical power user? Business owner?
- What's the Jobs-to-Be-Done? What does OpenClaw actually solve vs "cool demo"?
- Where does OpenClaw fail UX-wise that a competitor could win?
- Is the 175K stars = real demand or hype cycle?

### CFO (Unit Economics)
- What are the revenue models in this space? (SaaS, marketplace, hosting, enterprise)
- What does it cost to run an autonomous agent 24/7? (LLM API costs, compute)
- OpenClaw is free/OSS — where's the monetization layer?
- TAM for "personal AI agent" market — real numbers, not hype
- CAC for developer tools / AI agents — benchmarks

### CMO (Go-to-Market)
- How did OpenClaw go from 0 to 175K stars? What channel worked?
- Who are the competitors? (Lindy.ai, Dust.tt, AgentGPT, AutoGPT, CrewAI, etc.)
- For a 2-5 person team — what's the realistic GTM?
- Open source as GTM — does it work for monetization?
- Community/marketplace revenue vs direct sales

### COO (Operations)
- What breaks at 10x users? 100x?
- Agent hosting: self-hosted vs managed — what do users actually want?
- Support burden for autonomous agents (things go wrong 24/7)
- What's agent, what's human in this business?
- ClawHub security disaster — how to run a marketplace safely?

### CTO (Technical Strategy)
- Build on OpenClaw fork vs build from scratch vs different approach?
- OpenClaw creator leaving → OSS foundation. Risk or opportunity?
- DLD's existing multi-agent patterns — competitive advantage or irrelevant?
- Local-first vs cloud-first — which wins in 2026-2027?
- Security model for autonomous agents — unsolved problem?

### Devil's Advocate
- Is this a real market or a GitHub star bubble?
- OpenClaw with 175K stars has ZERO revenue model. Is that a warning?
- Peter Steinberger leaving = project dies slowly?
- With 2-5 people, can you compete against well-funded competitors?
- Is the founder chasing shiny objects instead of shipping current products?
- "Autonomous AI agent" = massive liability risk. One agent sends wrong email = lawsuit?

---

## Decision Required

By end of Board:
1. **GO / NO-GO** on entering autonomous AI agent market
2. If GO: what product? what positioning? what's the 90-day plan?
3. If NO-GO: what patterns from OpenClaw to steal for existing work?
