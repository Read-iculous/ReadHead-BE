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
│   ├── logging.py             # Structured JSON logger with sensitive data masking
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
│   ├── auth_session.py        # Login/OAuth sessions, JWT sid & revocation
│   ├── refresh_token.py       # Hash-only session token chains
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
│   ├── reading.py             # History, highlights, stats schemas
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
│   ├── reading_service.py     # History, highlights, stats & privacy enforcement
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
- **Completion metadata**: Request-scoped adapters reset and expose a normalized `finish_reason` from terminal upstream frames. SSE distinguishes a normal stop from token-limit truncation; complete generation rejects non-stop finishes so quiz/proactive callers cannot silently use a partial result. Missing terminal metadata is not assumed to be a normal stop.
- **Complete text validation**: Non-streaming completion requires non-whitespace text even with a normal stop, preserving the same usable-content boundary as SSE.
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
  3. Incremental `pull` uses one opaque position/checkpoint cursor over `(updated_at, entity_type, id)`, combined `limit` up to 100, `next_cursor` and `has_more`. Writers/pull serialize briefly on the user row and advance `users.sync_clock` (ADR-013). Higher-version updates may be re-delivered; client upserts by ID/version. Full resync stages only synced cache and preserves unsent work.
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
- Configures native asynchronous Redis fixed-window limiting with bounded process-local fallback (`app/core/limiter.py`); this avoids blocking the event loop on synchronous rate-limit storage. Key functions:
  1. **Authenticated Endpoints** (`/ai/stream`, `/sync/*`): Keyed by authenticated `user_id` to guarantee user-level rate isolation.
  2. **Public Auth Endpoints** (`/auth/login`, `/auth/register`, `/auth/oauth/google`, `/auth/oauth/github`, `/auth/refresh`): Keyed by `request.client.host` after Uvicorn trusted-proxy processing (never trust arbitrary raw `X-Forwarded-For` headers), regardless of an optional access-token header. Trailing-slash redirects use the same identity. Authenticated logout uses the user identity.
  3. **High-Availability Fallback**: If Redis becomes temporarily unreachable, limiter gracefully falls back to in-memory counters to prevent 500 errors.

### 2.7 Database Session Lifecycle Decoupling for SSE Streaming (`app/services/ai_service.py`)
- Solves database connection pool exhaustion across long-lived streaming requests (`ADR-014`):
  1. **Pre-Stream Read**: Transient DB transaction validates user/auth session, loads the BYOK key, verifies tab ownership/privacy policy, and creates the conversation/user message in standard mode. Commit and release before streaming; skip writes in Privacy Mode.
  2. **Zero-DB Streaming Loop**: Token yielding, prompt fencing, citation analysis, and Redis cancellation checks (`revoked_users:{user_id}`, `revoked_sessions:{sid}`) run without holding any open database connection.
  3. **Post-Stream Write**: A brief scoped DB transaction commits the assistant message/version and allocated sync timestamp before `done`; on failure emit `PERSISTENCE_FAILED` and offer UI copying only. Disconnect saves partial output in standard mode; writes are skipped in Privacy Mode.

### 2.8 Structured JSON Logging & Telemetry Redaction (`app/core/logging.py`)
- Enforces cloud-native observability and strict privacy compliance (`FR-OPS-03`):
  1. Outputs single-line JSON log events containing `timestamp`, `level`, `service`, `request_id`, `user_id` (hashed or masked), and `message`.
  2. **PII & Credential Scrubbing**: Intercepts log records to automatically mask API keys, Authorization headers, passwords, and sensitive text payloads matching credential regexes (`[REDACTED]`).
  3. Correlates logs with `X-Request-ID` middleware for distributed tracing across services.

### Backend implementation status
See `.docs/development/implementation-status.md` for source locations and verification limits. Shared response models live in `app/schemas/responses.py`; provider failures are normalized by `app/core/ai/errors.py`.
