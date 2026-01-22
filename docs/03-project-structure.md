# Структура проекта

```
{project}/
│
├── CLAUDE.md                 # 50 lines: ASCII + links (entry point for LLM)
│
├── .claude/
│   ├── contexts/             # Domain contexts (100-200 lines each)
│   │   ├── shared.md         # Infrastructure: DB, LLM, utils
│   │   ├── {domain1}.md      # Business domain 1
│   │   ├── {domain2}.md      # Business domain 2
│   │   └── web.md            # Frontend context
│   │
│   ├── skills/               # LLM workflows
│   │   ├── spark/SKILL.md    # Ideation → Spec
│   │   ├── plan/SKILL.md     # Spec → Tasks (UltraThink)
│   │   ├── autopilot/SKILL.md # Tasks → Code (subagents)
│   │   ├── council/SKILL.md  # Complex decisions (5 experts)
│   │   ├── review/SKILL.md   # Architecture watchdog
│   │   └── debug/SKILL.md    # Root cause analysis
│   │
│   └── agents/               # Subagent prompts
│       ├── autopilot/
│       │   ├── coder.md
│       │   ├── tester.md
│       │   ├── documenter.md
│       │   └── reviewer.md
│       └── council/
│           ├── architect.md
│           ├── product.md
│           ├── developer.md
│           ├── ux.md
│           └── business.md
│
├── backend/                  # Python backend (FastAPI)
│   ├── src/
│   │   ├── shared/           # Base types, Result pattern
│   │   ├── infra/            # Infrastructure layer
│   │   │   ├── db/           # Supabase client
│   │   │   ├── llm/          # OpenAI wrapper
│   │   │   └── external/     # Third-party APIs
│   │   ├── domains/          # Business logic
│   │   │   ├── auth/
│   │   │   ├── workflows/
│   │   │   ├── tasks/
│   │   │   ├── notifications/
│   │   │   └── bot/
│   │   ├── api/              # Entry points
│   │   │   ├── http/         # REST API (FastAPI)
│   │   │   └── telegram/     # Bot entry point
│   │   └── config/           # Configuration
│   │
│   ├── tests/                # Test structure
│   │   ├── contracts/        # API contracts — NEVER modify
│   │   ├── regression/       # Bug prevention — NEVER modify
│   │   ├── integration/      # Integration tests
│   │   ├── e2e/              # End-to-end tests
│   │   └── conftest.py       # Fixtures + auto-markers
│   │
│   ├── scripts/              # Utility scripts
│   │   ├── check_domain_imports.py  # Import linter
│   │   └── check_file_sizes.py      # LOC gate
│   │
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                 # Next.js frontend
│   ├── src/
│   │   ├── app/              # App router
│   │   ├── components/       # UI components
│   │   ├── lib/              # Utilities
│   │   └── types/            # TypeScript types
│   ├── package.json
│   └── Dockerfile
│
├── supabase/                 # Database
│   ├── migrations/           # SQL migrations
│   └── functions/            # Edge functions
│
├── ai/                       # AI workflow tracking
│   ├── backlog.md            # Task tracking (single table!)
│   ├── features/             # Feature specs
│   ├── principles/           # This folder!
│   └── ideas.md              # Future ideas
│
├── docker-compose.yml        # Local development
├── docker-compose.prod.yml   # Production
├── .env.example
├── .gitignore
└── README.md
```
