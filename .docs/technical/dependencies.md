# Project Dependencies

## 1. Production Dependencies (`requirements.txt`)
```txt
# Core Framework
fastapi>=0.110.0,<1.0.0
anyio>=4.0.0,<5.0.0  # cancellation-safe bounded upstream cleanup
uvicorn[standard]>=0.28.0,<1.0.0
pydantic>=2.6.0,<3.0.0
pydantic-settings>=2.2.0,<3.0.0

# Database & ORM
sqlalchemy>=2.0.28,<3.0.0
asyncpg>=0.29.0,<1.0.0
alembic>=1.13.1,<2.0.0

# In-Memory Cache & Rate Limiting
redis>=5.0.3,<6.0.0
slowapi>=0.1.9,<1.0.0

# Security, Cryptography & Auth
passlib[bcrypt]>=1.7.4
bcrypt>=4.0.1,<4.1  # compatible with passlib 1.7.x
python-jose[cryptography]>=3.3.0
cryptography>=42.0.5
authlib>=1.3.0

# HTTP & Async Client
httpx>=0.27.0,<1.0.0

# AI Provider SDKs
openai>=1.14.0
google-generativeai>=0.4.1
anthropic>=0.20.0
```

## 2. Development & Testing Dependencies (`requirements-dev.txt`)
```txt
pytest>=8.1.0
pytest-asyncio>=0.23.5
pytest-cov>=4.1.0
black>=24.2.0
isort>=5.13.2
ruff>=0.3.2
mypy>=1.9.0
```

## 3. Dependency Pinning & Upgrades
- Use semantic versioning ranges in specifications, but lock exact versions using `pip-tools` (`requirements.txt` compiled from `requirements.in`) or Poetry/Pipenv when locked down.
- Always review major version bumps of `openai`, `google-generativeai`, and `anthropic` to catch any breaking changes in streaming interfaces.

The initial declared provider/OAuth packages remain available, but Gemini and OAuth use `httpx` directly. Native async Redis limiting is implemented instead of invoking synchronous SlowAPI storage. `pyproject.toml` enables the Pydantic Mypy plugin; the passlib-compatible bcrypt bound is explicit in `requirements.txt`.

AnyIO is an explicit runtime dependency for bounded shielded stream/client cleanup. Focused offline regressions coexist with opt-in PostgreSQL/Redis integration tests. `python tests/run_integration.py` provisions disposable storage and runs installed provider SDKs with synthetic upstream HTTP responses. The wire fixture uses each SDK's native HTTP transport (`httpx` or `httpx2`) to avoid mistaking transport-fixture incompatibilities for application defects. The full BE-17 plan and coverage target remain incomplete; real external AI/OAuth success requires live credentials.
