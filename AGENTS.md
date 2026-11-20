# ReadHead-BE — Agent Context

## What This Project Is
**ReadHead-BE** is the backend API server for the **Intelligent Reading Assistant**, an AI-powered Chrome Browser Extension. It enables real-time reading assistance (explain, summarize, translate, accessibility re-rendering & text simplification for dyslexia, comprehension quizzes, and adaptive proactive assistance) using a Bring Your Own Key (BYOK) model across OpenAI, Google Gemini, and Anthropic Claude.

## Tech Stack
| Layer | Technology |
|---|---|
| Runtime | Python 3.10+ |
| Framework | FastAPI (Async) |
| Database | PostgreSQL |
| Driver & ORM | asyncpg + SQLAlchemy 2.0 (asyncio) |
| Migrations | Alembic |
| Auth | JWT (Access + Refresh tokens) & OAuth2 (Google, GitHub) |
| Cryptography | AES-256-GCM symmetric encryption for User API Keys |
| AI Protocol | Server-Sent Events (SSE) streaming with multi-provider abstraction |
| Testing | Pytest + pytest-asyncio |

## Mandatory Rules — Read First
1. **Always read `.docs/` before writing any code** — no guessing allowed.
2. **Never guess database schema** — check `.docs/database/schema.md` and `.docs/database/relationships.md`.
3. **Never guess API contracts** — check `.docs/api/endpoints.md` and `.docs/api/error-codes.md`.
4. **Never store API keys in plaintext** — use AES-256 encryption via `app/core/security.py`.
5. **Every DB change requires an Alembic migration** — see `.agents/skills/database-migration/SKILL.md`.
6. **Ask before guessing** — if requirements or business logic are missing, stop and ask.

## Codebase Map
```
app/
├── core/         ← Config, auth, AES-256 security, database session, AI provider gateway
│   └── ai/       ← Unified AI adapter subsystem (OpenAI, Gemini, Claude)
├── models/       ← SQLAlchemy async ORM models (User, ApiKey, Conversation, History...)
├── schemas/      ← Pydantic V2 request & response schemas
├── services/     ← Business logic layer (auth, AI orchestration, key vault, history)
├── routers/      ← FastAPI route handlers (REST & SSE streaming endpoints)
└── main.py       ← App entrypoint, CORS middleware, router registration
tests/
├── unit/         ← Isolated service & schema unit tests
└── integration/  ← Full HTTP & database API integration tests
```

## Quick Reference
| Topic | File |
|---|---|
| Project overview & scope | `.docs/project-overview.md` |
| System context diagram | `.docs/system-context.md` |
| Architecture overview | `.docs/architecture/overview.md` |
| Architecture decisions (ADR) | `.docs/architecture/decisions.md` |
| Tech stack & dependencies | `.docs/technical/tech-stack.md` & `.docs/technical/dependencies.md` |
| Database schema & ERD | `.docs/database/schema.md` & `.docs/database/relationships.md` |
| API endpoints & SSE specs | `.docs/api/endpoints.md` |
| Error codes registry | `.docs/api/error-codes.md` |
| Auth & OAuth flows | `.docs/technical/auth-flow.md` |
| Environment variables | `.docs/technical/environment-variables.md` |
| Coding standards & conventions | `.agents/rules/04-coding-standards.md` & `.docs/technical/coding-conventions.md` |
| FastAPI & async conventions | `.agents/rules/07-python-fastapi-conventions.md` |
| Setup & development commands | `.docs/development/setup.md` & `.docs/development/commands.md` |

## Available Skills
Activate when relevant:
- `project-exploration` — Explore project structure and build mental models
- `codebase-research` — Locate existing code and patterns before implementing
- `api-endpoint-implementation` — Create new endpoints (schema → model → service → router → test)
- `database-migration` — Generate, apply, and verify Alembic migrations
- `feature-implementation` — End-to-end feature development
- `bug-investigation` — Trace errors and fix bugs safely
- `code-review` — Review code for architecture, security, and quality compliance
- `documentation-sync` — Keep `.docs/` in sync after code changes
- `docx-to-docs-sync` — Extract additional specs from `.docx` files
