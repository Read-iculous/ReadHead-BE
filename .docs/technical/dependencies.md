# Project Dependencies

## 1. Production Dependencies (`requirements.txt`)
```txt
# Core Framework
fastapi>=0.110.0,<1.0.0
uvicorn[standard]>=0.28.0,<1.0.0
pydantic>=2.6.0,<3.0.0
pydantic-settings>=2.2.0,<3.0.0

# Database & ORM
sqlalchemy>=2.0.28,<3.0.0
asyncpg>=0.29.0,<1.0.0
alembic>=1.13.1,<2.0.0

# Security, Cryptography & Auth
passlib[bcrypt]>=1.7.4
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
