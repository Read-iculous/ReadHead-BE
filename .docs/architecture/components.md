# System Components

## 1. Component Map

```
app/
├── core/
│   ├── config.py              # Application settings via Pydantic BaseSettings
│   ├── security.py            # Password hashing (bcrypt) & AES-256 key encryption
│   ├── auth.py                # JWT creation, decode & FastAPI authentication dependencies
│   ├── database.py            # Async engine, sessionmaker & Base declarative class
│   ├── redis.py               # Async Redis connection pool & rate limiter configuration
│   ├── exceptions.py          # Standard domain exceptions and HTTP error handlers
│   ├── privacy/               # Sensitive Data & Privacy Subsystem (Feature H)
│   │   ├── pii_detector.py    # Regex & heuristic detection for credentials, keys, PII
│   │   └── domain_filter.py   # Domain blacklist evaluator
│   └── ai/                    # Unified AI Provider Subsystem (Features C & E)
│       ├── base.py            # BaseAIProvider abstract interface
│       ├── factory.py         # ProviderFactory to instantiate provider adapters
│       ├── openai_adapter.py  # OpenAI integration (Async stream)
│       ├── gemini_adapter.py  # Google Gemini integration (Async stream)
│       ├── claude_adapter.py  # Anthropic Claude integration (Async stream)
│       └── grounding.py       # Grounding attribution & uncertainty evaluator
├── models/                    # SQLAlchemy ORM Models
│   ├── user.py                # Users & OAuth accounts (Feature A)
│   ├── api_key.py             # User-stored encrypted API keys (Feature C)
│   ├── conversation.py        # Chat sessions & individual messages (Feature I)
│   ├── reading_history.py     # Browsed URLs, dwell time, cached summaries (Feature I)
│   ├── highlight.py           # User highlights and notes on web pages (Feature I)
│   ├── quiz.py                # Generated comprehension quizzes & attempts (Feature F)
│   ├── feedback.py            # AI response feedback: thumbs up/down, reports (Feature E)
│   └── user_setting.py        # Accessibility, proactive rules, domain blacklists (Features B & G)
├── schemas/                   # Pydantic V2 Request & Response schemas
│   ├── common.py              # Pagination, generic response envelopes
│   ├── auth.py                # Login, Register, OAuth, Token schemas
│   ├── user.py                # User profile schemas
│   ├── api_key.py             # Key creation (plaintext in) & display (masked out)
│   ├── ai.py                  # Prompt requests, task options, streaming chunks, grounding
│   ├── conversation.py        # Sessions and messages schemas
│   ├── reading.py             # History, highlights, bookmarks schemas
│   ├── quiz.py                # Quiz questions, answer submission, score schemas
│   ├── sync.py                # Multi-device sync push/pull & conflict schemas (Feature J)
│   ├── feedback.py            # Response rating & inaccuracy report schemas
│   └── admin.py               # Telemetry metrics, user status update & admin feedback schemas
├── services/                  # Business Logic Layer
│   ├── auth_service.py        # Registration, login, session token lifecycle
│   ├── user_service.py        # Profile & accessibility settings operations
│   ├── api_key_service.py     # Encrypt, store, decrypt, test user API keys
│   ├── ai_service.py          # Context assembly, prompt engineering, provider delegation
│   ├── privacy_service.py     # Pre-flight sensitive content inspection & policy checks
│   ├── conversation_service.py# Chat session & message persistence
│   ├── reading_service.py     # History, bookmarks, highlights & privacy enforcement
│   ├── quiz_service.py        # Comprehension quiz generation & score evaluation
│   ├── sync_service.py        # Incremental sync & conflict resolution engine
│   ├── feedback_service.py    # User ratings & reporting management
│   └── admin_service.py       # Platform telemetry aggregation & user moderation
└── routers/                   # API Route Handlers
    ├── router.py              # Root router aggregating sub-routers
    ├── health.py              # /api/v1/health (Feature L)
    ├── auth.py                # /api/v1/auth (Feature A)
    ├── users.py               # /api/v1/users (Features A & B)
    ├── api_keys.py            # /api/v1/api-keys (Feature C)
    ├── ai.py                  # /api/v1/ai (Features E, G, H)
    ├── quiz.py                # /api/v1/quiz (Feature F)
    ├── conversations.py       # /api/v1/conversations (Feature I)
    ├── reading.py             # /api/v1/reading (Feature I)
    ├── sync.py                # /api/v1/sync (Feature J)
    └── admin.py               # /api/v1/admin (Web Management Portal Ops)
```

---

## 2. Core Subsystems Detail

### 2.1 Unified AI Gateway (`app/core/ai/`)
- **Abstract Interface (`BaseAIProvider`)**: Defines `generate_stream(...)`, `generate_complete(...)`, and `validate_key(...)`.
- **Adapters**: Concrete implementations for OpenAI, Gemini, and Claude translate standardized prompt messages into provider-specific payloads.
- **Factory**: Dynamically instantiates the appropriate adapter using the active user's decrypted API key retrieved from the database.
- **Grounding Attributor (`grounding.py`)**: Analyzes LLM output against the provided page context to calculate an initial grounding flag (`is_grounded: true/false`), identify citations, and detect uncertainty cues (e.g., "The provided text does not mention...").

### 2.2 Sensitive Data & Privacy Engine (`app/core/privacy/`)
- Enforces **Feature H** (`FR-SEC-01~12`):
  1. Inspects outbound text (selected text, page context, user prompts) against patterns for:
     - Credentials (passwords, auth tokens, private keys).
     - Financial data (credit card numbers, bank account numbers).
     - Personally Identifiable Information (national ID numbers, SSNs).
  2. If detected and `data_protection_mode` is enabled: Blocks transmission, generates a redacted preview, and returns error code `SENSITIVE_DATA_DETECTED`.
  3. Provides an explicit bypass mechanism (`bypass_protection: true`) only after the user actively confirms override.
  4. Enforces the user's domain blacklist (e.g. `*.bank.com`, `intranet.*`) to prevent data leakage.

### 2.3 Synchronization & Conflict Resolution Engine (`app/services/sync_service.py`)
- Enforces **Feature J** (`FR-SYN-01~08`):
  1. Uses **Optimistic Concurrency Control** via `version` numbers and `updated_at` timestamps on synchronized mutable entities (`conversations`, `settings`, `highlights`).
  2. Individual `messages` are **append-only and immutable**; they are excluded from sync pull and fetched on-demand via `GET /api/v1/conversations/{id}/messages`.
  3. Incremental `pull` uses a **Composite Cursor** `(updated_at, id)` with pagination (`limit: 100`, `next_cursor`, `has_more`) ensuring zero skipped or duplicated records even when items share identical timestamps.
  4. Batch `push` applies changes atomically. If a client submits an update with a stale base version, the server detects a collision and returns `409 SYNC_CONFLICT` with both versions, allowing deterministic resolution without silent data loss.

### 2.4 Accessibility Profile Manager (`app/services/user_service.py`)
- Enforces **BG-06** and **BR-11**:
  - Manages preferences in `user_settings.accessibility_profile`:
    - `dyslexia_font`: Boolean (enables OpenDyslexic typography).
    - `line_spacing`: Float (e.g. 1.5, 1.8).
    - `font_size_delta`: Integer.
    - `bionic_reading`: Boolean (bolds initial letters of words).
    - `high_contrast`: Boolean.
  - Couples with AI Text Simplification (`task: "simplify"`) to rephrase dense passages for cognitive ease.

### 2.5 Health & Diagnostics Subsystem (`app/routers/health.py`)
- Enforces **Feature L** (`FR-OPS-01~05`):
  - Returns database connection latency, system uptime, and environment status.
  - Strictly strips all user credentials, decrypted API keys, and sensitive page context from application logs (`FR-OPS-03`).

### 2.6 Rate Limiting & Reverse Proxy Shield (`app/core/limiter.py`)
- Configures Redis-backed `slowapi.Limiter` with proxy-aware key functions:
  1. **Authenticated Endpoints** (`/ai/stream`, `/sync/*`): Keyed by authenticated `user_id` to guarantee user-level rate isolation.
  2. **Public Auth Endpoints** (`/auth/login`, `/auth/register`): Keyed by client IP extracted from `X-Forwarded-For` via trusted proxy middleware (`uvicorn --proxy-headers`), preventing Reverse Proxy IP collations that could cause system-wide lockouts.
  3. **High-Availability Fallback**: If Redis becomes temporarily unreachable, limiter gracefully falls back to in-memory counters to prevent 500 errors.
