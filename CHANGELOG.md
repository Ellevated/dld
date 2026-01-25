# Changelog

All notable changes to DLD (Double-Loop Development) methodology.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [3.4] - 2026-01-26

### Added
- **Bootstrap skill** — Day 0 discovery, unpack idea from founder's head
- **Claude-md-writer skill** — CLAUDE.md optimization with 3-tier modular system
- **Council decomposition** — 5 separate expert agents in `agents/council/`
- **Spark agent** — dedicated agent file for idea generation
- **Diary recorder** — auto-captures problems for future reflection
- **Wrapper skills** — tester/coder/planner as standalone invocable skills
- **Research tools** — Exa + Context7 MCP integration in agents
- **Scout skill** — isolated research agent for external sources
- **Reflect skill** — synthesize diary entries into CLAUDE.md rules

### Changed
- README rewritten as hero landing page with Mermaid diagrams
- All documentation translated to English
- Skills and agents fully translated to English

### Documentation
- Added FAQ.md with 20+ questions
- Added COMPARISON.md with fair alternatives analysis
- Added 3 example projects (marketplace, content factory, AI company)
- Added MCP setup guide for Context7 and Exa

---

## [3.2] - 2026-01-24

### Added
- GitHub community files (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY)
- Issue and PR templates
- Hooks system with README documentation

### Changed
- Template CLAUDE.md translated to English

---

## [3.1] - 2026-01-23

### Added
- Autopilot skill split into 7 modular files
- Template sync from production project (awardybot)

### Changed
- Removed hardcoded project-specific references from template

---

## [3.0] - 2026-01-23

Initial public release of DLD methodology.

### Added
- **Core methodology** — Double-Loop Development concept
- **Project structure** — shared/infra/domains/api layers
- **Skills system** — spark, autopilot, council, audit
- **Agent prompts** — planner, coder, tester, reviewer, debugger
- **Documentation** — 19 methodology docs + 3 foundation docs
- **Template** — ready-to-use project template with CLAUDE.md

### Architecture
- Result pattern for explicit error handling
- Async everywhere for IO operations
- Money in cents (no floats)
- Max 400 LOC per file (LLM-friendly)
- Max 5 exports per `__init__.py`

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 3.3 | 2026-01-26 | Bootstrap, Claude-md-writer, Council decomposition, English translation |
| 3.2 | 2026-01-24 | GitHub community files, Hooks system |
| 3.1 | 2026-01-23 | Autopilot modularization, Template sync |
| 3.0 | 2026-01-23 | Initial release |
