# Technical Stack

## 1. Core Stack
| Layer | Technology | Version / Specification | Purpose |
|---|---|---|---|
| **Language** | Python | 3.10+ | Primary language, using type hinting & async/await |
| **Framework** | FastAPI | 0.110+ | High-performance async web framework |
| **ASGI Server** | Uvicorn | Standard (uvloop) | Production-ready ASGI server |
| **Database** | PostgreSQL | 15+ / 16+ | Primary ACID-compliant relational data store |
| **In-Memory Cache & Limiter** | Redis | 7.0+ | Fast in-memory cache, rate limiting, and token revocation |
| **ORM** | SQLAlchemy | 2.0+ (asyncio mode) | Object-relational mapping with async query execution |
| **DB Driver** | asyncpg | 0.29+ | High-performance asynchronous PostgreSQL driver |
| **Migrations** | Alembic | 1.13+ | Schema version control & migration management |
| **Validation** | Pydantic | V2 (2.6+) | Data validation and JSON serialization/deserialization |
| **Configuration**| pydantic-settings | 2.2+ | Type-safe environment variable management |

## 2. Authentication & Cryptography
| Component | Library | Purpose |
|---|---|---|
| **JWT Tokens** | `python-jose[cryptography]` / `PyJWT` | Encoding and decoding access/refresh tokens |
| **Password Hashing** | `passlib[bcrypt]` | Secure salted bcrypt hashing for email/pass auth |
| **Key Vault Encryption** | `cryptography` (AES-256-GCM) | Symmetric encryption of user-provided LLM API keys |
| **OAuth2 Clients** | `httpx` + `authlib` | Google & GitHub OAuth2 token exchange and profile fetch |
| **Transactional Email** | `httpx` (direct REST) | Email verification & password-reset delivery via the Resend HTTPS API (`RESEND_API_KEY`); no dedicated SDK (see `.docs/technical/dependencies.md`) |

## 3. External AI Integration
| Provider | Integration Method | Supported Models (Initial) |
|---|---|---|
| **Google Gemini** | Google GenAI SDK / Async HTTP | `gemini-1.5-flash`, `gemini-1.5-pro` |
| **OpenAI** | Official `openai` Python SDK (Async) | `gpt-4o-mini`, `gpt-4o` |
| **Anthropic** | Official `anthropic` Python SDK (Async) | `claude-3-5-sonnet`, `claude-3-haiku` |

## 4. Testing & Code Quality
| Purpose | Tool | Configuration |
|---|---|---|
| **Test Runner** | `pytest`, `pytest-asyncio` | Full async fixture & execution support |
| **HTTP Testing** | `httpx` (AsyncClient) | Testing API endpoints asynchronously |
| **Code Formatter** | `black` | Line length 88 |
| **Import Sorter** | `isort` | Standard multi-line formatting |
| **Linting** | `ruff` | PEP8 & bug detection |
| **Type Checking** | `mypy` | Strict type validation |
