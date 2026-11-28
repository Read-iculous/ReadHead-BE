# ReadHead-BE — Backend Implementation Task Breakdown

Implementation status: see `implementation-status.md`. Backend source for BE-01–BE-16 and BE-18 is implemented; BE-17 automated tests/coverage are explicitly deferred by the user. Acceptance criteria below remain the verification checklist, not a claim that every scenario has been tested.
BE-19 and BE-20 are newly added tasks documented in full but NOT yet implemented (docs complete; code pending).
BE-21, BE-22 and BE-23 are newly added tasks documented in full but NOT yet implemented (docs complete; code pending) — BE-01→BE-20 are unchanged.
BE-24, BE-25 and BE-26 are newly added tasks documented in full but NOT yet implemented (docs complete; code pending) — BE-01→BE-23 are unchanged.

This document defines the complete backend implementation roadmap derived from BRS, SRS, SyRS, OpsCon, and `.docs/`. Every task adheres to a standardized format: **Task Name**, **Description**, **Plan & Codebase**, **Acceptance Criteria**, and **Verification / Screenshot**.

---

## Roadmap Overview

```
Phase 1: Foundation & Database
  ├── [BE-01] Project Scaffolding, Core Config & Health Endpoint (Feature L)
  └── [BE-02] Database Models & Initial Alembic Migration

Phase 2: Authentication & User Lifecycle (Feature A)
  ├── [BE-03] Email/Password Authentication & JWT Token Management
  ├── [BE-04] OAuth2 Integration (Google & GitHub)
  └── [BE-05] User Profile & Account Data Lifecycle Management

Phase 3: User Configuration & Preferences (Features B & G)
  └── [BE-06] User Settings, Accessibility Profile & Proactive Config

Phase 4: BYOK Key Vault (Feature C)
  └── [BE-07] AES-256 Encrypted API Key Vault & Validation Engine

Phase 5: Unified AI Gateway & Streaming (Features E & H)
  ├── [BE-08] Multi-Provider AI Abstraction Layer (OpenAI, Gemini, Claude)
  ├── [BE-09] Real-Time SSE AI Streaming Endpoint
  └── [BE-10] Pre-Flight Sensitive Content Inspection & Privacy Policy Filter

Phase 6: Adaptive Learning & Comprehension (Features F & G)
  ├── [BE-11] Proactive Reading Support Engine
  └── [BE-12] Comprehension Quiz Generation & Grading Subsystem

Phase 7: Reading Data & Community Feedback (Features I & E)
  ├── [BE-13] Tab-Isolated Conversations & Message History
  ├── [BE-14] Reading History & Web Highlights Storage
  └── [BE-15] User Feedback & Accuracy Reporting

Phase 8: Multi-Device Sync & Concurrency (Feature J)
  └── [BE-16] Multi-Device Incremental Synchronization & Conflict Resolver

Phase 9: Quality Assurance & Integration (NFRs)
  └── [BE-17] End-to-End Integration Test Suite & Coverage Baseline

Phase 10: Admin Management, Telemetry & Rate Limiting (Platform Ops)
  └── [BE-18] Admin Portal API, Telemetry Engine & Redis Rate Limiter

Phase 11: Email Trust & Usage Analytics (Feature A extension)
  ├── [BE-19] Email Verification & Password Reset (Resend)
  └── [BE-20] AI Usage Tracking

Phase 12: Language, Quiz History & Personalization Governance (Features B, F, G extension)
  ├── [BE-21] Language Settings & Translate Behavior
  ├── [BE-22] Quiz History API
  └── [BE-23] Proactive Dedup + Personalization Consent

Phase 13: Insights, Export & History Management Hardening (Features I, G extension)
  ├── [BE-24] Reading Stats & Comprehension Insights
  ├── [BE-25] Data Export (GDPR Bundle)
  └── [BE-26] Conversation Bulk Delete, Title Patch, Highlight Patch & Bookmark Cleanup
```

---

## Phase 1: Foundation & Database

### [BE-01] Project Scaffolding, Core Config & Health Endpoint
- **Feature Reference**: Feature L (`FR-OPS-01~05`), `NFR-MNT-01`
- **Description**: Initialize the project directory layout, dependencies, environment settings via Pydantic Settings, database session lifecycle, error handlers, and a public `/api/v1/health` endpoint.
- **Plan & Codebase**:
  - `requirements.txt` & `requirements-dev.txt`: Pin FastAPI, Uvicorn, SQLAlchemy, asyncpg, redis, Pydantic, etc.
  - `app/core/config.py`: Implement `Settings` class loading `.env` parameters (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEY`, `CORS_ORIGINS`). Enforce Pydantic key separation validator (JWT signing secret must differ from every effective keyring key) failing fast on startup if identical.
  - `app/core/database.py`: Configure asynchronous engine `create_async_engine`, sessionmaker `AsyncSessionLocal`, and `get_db` dependency.
  - `app/core/redis.py`: Configure asynchronous Redis connection pool and ping utility.
  - `app/core/exceptions.py`: Define base `AppException` and exception handlers for standard JSON envelopes.
  - `app/core/logging.py`: Implement structured JSON logger emitting single-line JSON with automatic secret and PII masking (`[REDACTED]`) and request correlation ID.
  - `app/routers/health.py`: Create `GET /api/v1/health` returning system status, latency checks for database and redis.
  - `app/main.py`: Assemble FastAPI instance, CORS middleware with `allow_origin_regex=r"^chrome-extension://[a-p]{32}$"` to support credentials without wildcard failures, router mounting, and lifespan management.
- **Acceptance Criteria**:
  - Server starts cleanly via `uvicorn app.main:app --port 8000`.
  - Application logs emit single-line JSON format with sensitive credentials/tokens masked as `[REDACTED]` (`FR-OPS-03`).
  - `GET /api/v1/health` returns `200 OK` with JSON checks (`checks.database` and `checks.redis` reporting healthy status and latency).
  - Returns `503 Service Unavailable` if PostgreSQL fails; Redis-only failure returns `200 OK` with `status: "degraded"` and declared feature fallbacks (ADR-010).
  - CORS middleware accepts origins configured in `CORS_ORIGINS` and regex-matches Chrome Extension origins.
  - Unhandled exceptions return structured JSON (`code: "INTERNAL_SERVER_ERROR"`), never raw HTML traces.
- **Verification / Screenshot**:
  - Command: `curl -i http://localhost:8000/api/v1/health`
  - Screenshot: Swagger UI at `http://localhost:8000/docs` displaying the `/api/v1/health` endpoint execution with `200 OK`.

---

### [BE-02] Database Models & Initial Alembic Migration
- **Feature Reference**: SRS §3.1.3, Database Schema Specification
- **Description**: Implement all core SQLAlchemy 2.0 async ORM declarative models and initialize Alembic migrations to construct the PostgreSQL database schema.
- **Plan & Codebase**:
  - `app/models/base.py`: Shared declarative base class with timestamp mixins (`created_at`, `updated_at`).
  - `app/models/user.py`: `User` (including server-only `sync_clock`) and `OAuthAccount` models.
  - `app/models/auth_session.py` and `app/models/refresh_token.py`: Session and hash-only token chain schema, constraints and indexes.
  - `app/models/api_key.py`: `UserApiKey` model with unique constraint on `(user_id, provider)`.
  - `app/models/user_setting.py`: `UserSetting` model with JSONB accessibility profile and privacy settings.
  - `app/models/conversation.py`: `Conversation` and `Message` models (with grounding fields).
  - `app/models/reading_history.py` & `app/models/highlight.py`: Models for history and saved highlights.
  - `app/models/quiz.py` & `app/models/feedback.py`: Comprehension quiz records and AI feedback models.
  - `alembic/`: Configure `env.py` to import all models and generate the initial migration `0001_initial_schema.py`.
- **Acceptance Criteria**:
  - `alembic upgrade head` runs without errors against a clean PostgreSQL database.
  - `alembic downgrade -1` cleanly drops created tables and constraints.
  - All foreign keys, cascade delete policies, and indexes match `.docs/database/relationships.md`.
- **Verification / Screenshot**:
  - Command: `alembic current` shows head revision.
  - Screenshot: PostgreSQL GUI (pgAdmin / DBeaver / terminal `\dt`) showing all 12 tables created with correct foreign key constraints.

---

## Phase 2: Authentication & User Lifecycle (Feature A)

### [BE-03] Email/Password Authentication & JWT Token Management
- **Feature Reference**: Feature A (`FR-ACC-01~06`, `FR-SEC-01~03`)
- **Description**: Provide user registration with salted bcrypt password hashing, login verification, and token lifecycle management (short-lived Access Tokens + database-backed Refresh Tokens).
- **Plan & Codebase**:
  - `app/core/security.py`: Implement password hashing/verification using `passlib[bcrypt]`.
  - `app/core/auth.py`: Token generation (`create_access_token`, `create_refresh_token`), verification, and `get_current_user` dependency.
  - `app/models/auth_session.py`: `AuthSession` with user/device ownership, expiry, revocation time and reason; JWT `sid` identifies this row across rotations.
  - `app/models/refresh_token.py`: Hash-only token chain, session FK, unique token hash, revocation reason/time and successor linkage.
  - `app/schemas/auth.py`: Pydantic schemas for `UserRegisterRequest`, `UserLoginRequest`, `TokenResponse`, and `TokenRefreshRequest`.
  - `app/services/auth_service.py`: Business logic for credential checking, duplicate email validation and session-scoped rotation; implement auth-flow §2.3–2.5 (cache recheck, owner-safe Redis lock, DB session-row lock/conditional update, temporary-failure isolation).
  - `app/routers/auth.py`: Endpoints `POST /register`, `POST /login`, `POST /refresh`, `POST /logout`.
- **Acceptance Criteria**:
  - `POST /register` with valid data returns `201 Created` with User profile object (`id`, `email`, `full_name`, `role`, `status`).
  - Duplicate registration returns `409 EMAIL_ALREADY_EXISTS`.
  - Invalid login returns `401 INVALID_CREDENTIALS`.
  - Inactive/suspended user login returns `401 USER_SUSPENDED`.
  - Token hash comparisons use constant-time `secrets.compare_digest` to prevent timing attacks.
  - Auth dependency `get_current_user` catches `RedisError` gracefully and falls back to checking user and auth-session validity directly in PostgreSQL if Redis is offline; session validation remains authoritative in normal operation too.
  - `POST /refresh` with valid refresh token rotates and issues a new access + refresh token pair.
  - Concurrent multi-tab refresh requests presenting the same old token within 30 seconds are safely served the new token pair without revocation errors.
  - Rotated tokens outside grace return `401 REFRESH_TOKEN_REVOKED`; missing grace results within 30s/lock timeout return `503 REFRESH_TEMPORARILY_UNAVAILABLE` without revoking other sessions. Revocation reasons distinguish rotation, logout and explicit security events.
  - Cover post-lock cache hits, lease expiry, DB-success/Redis-failure, logout of a successor while predecessor mappings remain, and Redis-unavailable DB rotation.
  - `POST /logout` revokes the whole authenticated session chain and all indexed grace mappings, including earlier tokens; stale caches cannot bypass DB session checks. Other device sessions remain active.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_ai_quiz_oauth_admin.py tests/integration/test_account_cache_url_refresh_errors.py tests/integration/test_concurrency_privacy_review.py tests/integration/test_send_disconnect_domain_password.py -v` (auth coverage is spread across these files; no `test_auth_api.py` exists)
  - Screenshot: Postman or Swagger UI showing `POST /api/v1/auth/login` returning tokens and subsequent authenticated call to `/api/v1/users/me` with Bearer header.

---

### [BE-04] OAuth2 Integration (Google & GitHub)
- **Feature Reference**: Feature A (`FR-ACC-01`), `.docs/technical/auth-flow.md`
- **Description**: Implement third-party OAuth2 authentication endpoints for Google (via Google ID Token) and GitHub (via Auth Code), enforcing email verification and auto-linking external identities to ReadHead user accounts.
- **Plan & Codebase**:
  - `app/schemas/auth.py`: `GoogleAuthRequest` (`id_token`), `GitHubAuthRequest` (`code`).
  - `app/services/auth_service.py`: Add `authenticate_google()` verifying ID Token with Google and `authenticate_github()` fetching profile and verified primary email via GitHub API.
  - Enforce `email_verified == true` before account creation or auto-linking (`403 EMAIL_NOT_VERIFIED` or `400 OAUTH_EMAIL_MISSING`).
  - Link or create user in `oauth_accounts` table; generate standard ReadHead JWT pair.
  - `app/routers/auth.py`: Mount `POST /api/v1/auth/oauth/google` and `POST /api/v1/auth/oauth/github`.
- **Acceptance Criteria**:
  - Valid OAuth payload authenticates existing user or creates a new user profile with `is_verified: true`.
  - Auto-links to existing account if email matches and provider confirms email verification.
  - Returns `200 OK` with standard `TokenResponse`.
  - Handled network errors or rejected provider tokens return `401 TOKEN_INVALID`.
- **Verification / Screenshot**:
  - Test: Mocked unit tests verifying token exchange logic.
  - Screenshot: Swagger UI response for `/api/v1/auth/oauth/google` returning access and refresh tokens.

---

### [BE-05] User Profile & Account Data Lifecycle Management
- **Feature Reference**: Feature A (`FR-ACC-04`), Feature I (`FR-HIS-07`)
- **Description**: Provide user profile retrieval and account deletion, enforcing strict multi-account isolation and distinguishing between deleting reading history vs deleting an entire account.
- **Plan & Codebase**:
  - `app/schemas/user.py`: `UserResponse` and `AccountDeleteRequest`.
  - `app/services/user_service.py`: Implement `get_profile()` and `delete_account()`.
  - `app/routers/users.py`: Implement `GET /api/v1/users/me` and `DELETE /api/v1/users/me`.
- **Acceptance Criteria**:
  - `GET /api/v1/users/me` returns current user profile without password or secret data.
  - `DELETE /api/v1/users/me` requires explicit confirmation string (`DELETE_ACCOUNT`) and valid password (for non-OAuth accounts).
  - Deletion cascades and completely removes all associated API keys, conversations, history, highlights, and settings.
  - Writes `revoked_users:{user_id}` to Redis with TTL=3600s, instantly rejecting any in-flight active access tokens across all devices.
- **Verification / Screenshot**:
  - Test: auth-focused integration files cover deletion (`tests/integration/test_send_disconnect_domain_password.py`, `tests/integration/test_account_cache_url_refresh_errors.py`); no dedicated `test_user_lifecycle.py` exists.
  - Screenshot: Response from `DELETE /api/v1/users/me` returning `204 No Content` and verifying database record removal.

---

## Phase 3: User Configuration & Preferences (Features B & G)

### [BE-06] User Settings, Accessibility Profile & Proactive Config
- **Feature Reference**: Feature B (`FR-CFG-01~07`), Feature G (`FR-PRV-01~04`), `BG-06`, `BR-11`
- **Description**: Implement user settings CRUD, persisting AI defaults, accessibility typography profiles (OpenDyslexic, bionic reading, line spacing), proactive assistance sensitivity, and domain privacy rules.
- **Plan & Codebase**:
  - `app/schemas/user.py`: `UserSettingResponse`, `UserSettingUpdateRequest`, and `AccessibilityProfileSchema`.
  - `app/services/user_service.py`: Retrieve and update settings with automatic initialization upon user creation.
  - `app/routers/users.py`: Mount `GET /api/v1/users/me/settings` and `PATCH /api/v1/users/me/settings`.
- **Acceptance Criteria**:
  - Newly created users automatically receive default settings (`default_provider: "gemini"`, `proactive_assistance_enabled: true`, `data_protection_mode: true`).
  - `PATCH /api/v1/users/me/settings` updates specified fields and increments the `version` integer for sync.
  - Invalid settings (e.g. unsupported provider, invalid language code) return `422 VALIDATION_ERROR`.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_concurrency_privacy_review.py -k "settings or provider or privacy" -v` (no dedicated `test_settings_api.py` exists).
  - Note: unsupported `default_provider` returns `400 UNSUPPORTED_PROVIDER` per `.docs/api/endpoints.md`, not the generic `422 VALIDATION_ERROR`.
  - Screenshot: Postman/Swagger UI showing `PATCH /api/v1/users/me/settings` updating `accessibility_profile` with `200 OK`.

---

## Phase 4: BYOK Key Vault (Feature C)

### [BE-07] AES-256 Encrypted API Key Vault & Validation Engine
- **Feature Reference**: Feature C (`FR-KEY-01~07`), `ADR-003`
- **Description**: Provide secure storage for user-provided LLM API keys (OpenAI, Gemini, Claude). Keys are encrypted at rest with AES-256-GCM, masked in responses, validated via upstream ping check before storage, and isolated per provider. Employs a dual-key Keyring for 100% zero-downtime key rotation.
- **Plan & Codebase**:
  - `app/core/security.py`: Add `encrypt_secret()` (enforcing CSPRNG `secrets.token_bytes(12)` nonce for every encryption to eliminate GCM nonce reuse) and `decrypt_secret()` supporting `ENCRYPTION_MASTER_KEYS` dictionary keyring and `CURRENT_KEY_VERSION`.
  - `app/schemas/api_key.py`: `ApiKeyCreateRequest`, `ApiKeyResponse` (with masked `key_hint`), `KeyValidationResponse`.
  - `app/services/api_key_service.py`: Add methods to store, retrieve, delete, and test keys. Enforce UPSERT behavior (atomic replace upon successful ping test; preserves old key if validation fails).
  - `app/cli/rotate_keys.py`: CLI maintenance utility (`python -m app.cli.rotate_keys --old-version v1 --new-version v2`) to re-encrypt stored keys when rotating master secrets without downtime.
  - `app/routers/api_keys.py`: Endpoints `GET /api/v1/api-keys`, `POST /api/v1/api-keys`, `DELETE /api/v1/api-keys/{provider}`, `POST /api/v1/api-keys/{provider}/validate`.
- **Acceptance Criteria**:
  - Plaintext key is encrypted before writing to PostgreSQL (format: `<version>:<nonce>:<ciphertext>:<tag>`); database inspect shows ciphertext.
  - `GET /api-keys` returns only masked previews (`sk-...4aF9`), never the decrypted key.
  - `POST /api-keys/{provider}/validate` performs a lightweight ping to the external provider:
    - If valid: returns `200 OK` with `valid: true`.
    - If invalid: returns `400 KEY_VALIDATION_FAILED` and rejects activation.
  - Load both keys in every process, switch all writers to `v2`, migrate in bounded ciphertext compare-and-swap batches, then verify zero `v1` writers/records before removing the old live key. Cover concurrent user key replacement and interrupted/resumed migration; follow the commands runbook.
  - Logs never contain plaintext keys (`FR-KEY-07`, `FR-OPS-03`).
- **Verification / Screenshot**:
  - Test: `pytest tests/unit/test_security_vault.py -v` plus vault assertions inside the integration suite (`store_key` in `tests/integration/test_ai_quiz_oauth_admin.py` checks ciphertext format, absence of plaintext in DB and responses, and decrypt roundtrip); no dedicated `test_api_keys_api.py` exists.
  - Screenshot: Database query output showing encrypted string in `encrypted_key` column alongside Swagger UI response showing masked `key_hint`.

---

## Phase 5: Unified AI Gateway & Streaming (Features E & H)

### [BE-08] Multi-Provider AI Abstraction Layer (OpenAI, Gemini, Claude)
- **Feature Reference**: Feature E (`FR-AI-01~08`), `ADR-001`, `ADR-008`
- **Description**: Build a unified AI provider subsystem using the Factory and Strategy patterns, allowing the backend to call OpenAI, Google Gemini, and Anthropic Claude through a single interface.
- **Plan & Codebase**:
  - `app/core/ai/base.py`: Abstract class `BaseAIProvider` defining `generate_stream(...)` and `validate_key(...)`.
  - `app/core/ai/openai_adapter.py`: Async streaming implementation using `openai.AsyncOpenAI`.
  - `app/core/ai/gemini_adapter.py`: Async streaming implementation using `google-generativeai`.
  - `app/core/ai/claude_adapter.py`: Async streaming implementation using `anthropic.AsyncAnthropic`.
  - `app/core/ai/factory.py`: `ProviderFactory` to instantiate adapters based on provider name and decrypted user key.
  - `app/core/ai/formatter.py`: `HistoryFormatter` normalizing multi-turn history across providers (maps `assistant` -> `model` for Gemini; merges consecutive same-role turns to satisfy Anthropic Claude turn alternating requirements).
  - `app/core/ai/grounding.py`: Prompt engineering templates enforcing source-grounding priority, uncertainty declarations, and citation markers (`BR-12~14`).
- **Acceptance Criteria**:
  - All three adapters implement the exact same interface and yield standardized chunk strings.
  - HistoryFormatter cleanly transforms conversation threads across Gemini, OpenAI, and Claude without provider-specific syntax errors.
  - Adapters wrap upstream calls in `try...finally` executing `await upstream_stream.aclose()` upon `asyncio.CancelledError`, preventing credit drain and socket leaks.
  - Unit tests with mock responses verify that each adapter properly handles rate limits, token timeouts, and authentication errors.
  - Grounding prompts instruct models to explicitly declare when answers rely on external training data vs current page text.
- **Verification / Screenshot**:
  - Test: `pytest tests/unit/test_sse_cleanup.py tests/unit/test_ai_edge_paths.py -v`
  - Output: Test log showing mocked streaming chunks successfully yielded from all three adapters.

---

### [BE-09] Real-Time SSE AI Streaming Endpoint
- **Feature Reference**: Feature E (`FR-AI-01~12`), `ADR-002`, `ADR-009`, `ADR-011`, `ADR-014`
- **Description**: Implement the central `/api/v1/ai/stream` Server-Sent Events endpoint handling Explain, Summarize, Translate, Simplify (Accessibility), and Multi-turn Chat. Enforce prompt injection fencing, max 2 concurrent SSE streams per user, zero-binary PDF text ingestion, and database session lifecycle decoupling (`ADR-014`).
- **Plan & Codebase**:
  - `app/schemas/ai.py`: `AiStreamRequest` (with task enum: `explain`, `summarize`, `translate`, `simplify`, `chat`; optional `target_language: str`; payload accepts `selected_text`, `page_content`, `content_type`, `user_prompt`, `bypass_protection`).
  - `app/services/ai_service.py`: Orchestrate user key decryption, conversation history injection, prompt construction with XML fencing (`<untrusted_web_context>`, `<user_selected_text>`), and async chunk generation. Decouple DB session into 3 phases: (1) Pre-stream authentication/key load and standard-mode user-message commit, (2) Streaming loop with zero DB connections held, and (3) Assistant-message commit before emitting `done` (ADR-014).
  - `app/routers/ai.py`: Mount `POST /api/v1/ai/stream` using FastAPI's `StreamingResponse(media_type="text/event-stream")`. Check and enforce max 2 concurrent active SSE streams via Redis `active_streams:{user_id}` (`429 STREAM_CONCURRENCY_EXCEEDED`).
  - Implement client disconnect detection (`asyncio.CancelledError`) to abort upstream streams gracefully (`ISSUE-001`).
  - Enforce rule against silent automated AI retries (`ADR-009`).
- **Acceptance Criteria**:
  - Returns `text/event-stream` with standard events `start`, `token`, `citation`, `done`, and `error`.
  - Database connection is freed before entering the token generator loop, preventing connection pool starvation across long-lived SSE streams (`ADR-014`).
  - If user has no active key for the provider, returns `400 NO_ACTIVE_API_KEY` before starting stream.
  - If user already has 2 active streams, rejects 3rd request with `429 STREAM_CONCURRENCY_EXCEEDED`.
  - If upstream provider fails or runs out of quota, streams `event: error` and aborts stream without `event: done`.
  - On `PERSISTENCE_FAILED`, retain text in current UI memory as "Not saved" and allow copying. MVP provides no retry-save operation or automatic LLM replay.
  - Supports `content_type: "pdf_text"` with client-extracted plain text (max 100KB); rejects raw binary files.
- **Verification / Screenshot**:
  - Command: `curl -N -X POST http://localhost:8000/api/v1/ai/stream -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"task": "explain", "page_url": "https://example.com/a", "selected_text": "Photosynthesis converts light into chemical energy."}'`
  - Test: `pytest tests/integration/test_stream_review.py tests/integration/test_send_disconnect_domain_password.py tests/integration/test_admin_marker_empty_completion.py tests/unit/test_ai_edge_paths.py tests/unit/test_sse_cleanup.py -v`
  - Screenshot: Terminal or Postman showing continuous event stream output chunk by chunk.

---

### [BE-10] Pre-Flight Sensitive Content Inspection & Privacy Policy Filter
- **Feature Reference**: Feature H (`FR-SEC-01~12`), `ADR-006`
- **Description**: Implement the privacy filter that inspects outbound text for sensitive data (PII, credentials, financial numbers) and checks target domains against the user's blacklist before any content is sent to an external AI provider.
- **Plan & Codebase**:
  - `app/core/privacy/pii_detector.py`: Heuristics and regex detectors for API keys, passwords, credit cards, SSNs, and private tokens.
  - `app/core/privacy/domain_filter.py`: Evaluator matching current URL against `user_settings.blacklisted_domains`.
  - `app/services/privacy_service.py`: Evaluator invoked in `ai_service` before LLM dispatch.
  - `app/routers/ai.py`: Mount `POST /api/v1/ai/check-sensitive`.
- **Acceptance Criteria**:
  - If text contains detected secrets and `data_protection_mode: true`:
    - Blocks AI call and returns `400 SENSITIVE_DATA_DETECTED` with redacted preview and detected secret types (`FR-SEC-04`).
  - If user sets `bypass_protection: true`: allows transmission with logged user consent (`FR-SEC-07`).
  - If page URL matches a blacklisted domain: rejects call with `400 DOMAIN_BLOCKED_BY_PRIVACY`.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_privacy_engine.py -v`
  - Screenshot: Swagger UI response showing `POST /api/v1/ai/check-sensitive` detecting a test API key pattern with `blocked_by_policy: true`.

---

## Phase 6: Adaptive Learning & Comprehension (Features F & G)

### [BE-11] Proactive Reading Support Engine
- **Feature Reference**: Feature G (`FR-PRV-01~06`), `BR-10`
- **Description**: Provide the backend service to evaluate complex paragraphs where a user paused or slowed down, generating concise, unobtrusive hints or key concept definitions.
- **Plan & Codebase**:
  - `app/schemas/ai.py`: `ProactiveSuggestRequest` (`page_url`, `paragraph_text`, `dwell_time_seconds`) and `ProactiveSuggestResponse`.
  - `app/services/ai_service.py`: Implement `evaluate_proactive_suggestion()` with lightweight model prompts.
  - `app/routers/ai.py`: Mount `POST /api/v1/ai/proactive-suggest`.
- **Acceptance Criteria**:
  - If user has `proactive_assistance_enabled: false` in settings, endpoint returns `has_suggestion: false` immediately.
  - On complex technical or academic text with high dwell time, returns `has_suggestion: true` with a short plain-text hint and suggested action.
  - Does not execute actions autonomously without user confirmation (`FR-PRV-03`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_ai_quiz_oauth_admin.py tests/integration/test_stream_review.py tests/integration/test_concurrency_privacy_review.py -v` (proactive-suggest coverage)
  - Screenshot: Postman response for `/api/v1/ai/proactive-suggest` returning a suggestion payload.

---

### [BE-12] Comprehension Quiz Generation & Grading Subsystem
- **Feature Reference**: Feature F (`FR-CMP-01~05`), `BG-03`, `BR-06~07`
- **Description**: Generate 3-5 multiple-choice questions based on extracted article text, evaluate submitted answers, provide explanations, and maintain quiz performance history.
- **Plan & Codebase**:
  - `app/schemas/quiz.py`: `QuizGenerateRequest`, `QuizResponse` (without revealing correct answers), `QuizSubmitRequest`, and `QuizGradeResponse`.
  - `app/services/quiz_service.py`: Orchestrate LLM JSON generation for questions, record quiz in `quiz_records` table, and compute score on submission.
  - `app/routers/quiz.py`: Mount `POST /api/v1/quiz/generate` and `POST /api/v1/quiz/{quiz_id}/submit`.
- **Acceptance Criteria**:
  - `POST /quiz/generate` returns structured questions with 4 options each, storing the correct answer on the server.
  - Insufficient source text returns `422 UNREPRESENTATIVE_SOURCE` instead of hallucinating questions (`FR-CMP-04`).
  - `POST /quiz/{id}/submit` compares submitted answers against stored keys, returns score (e.g. 4/5) and explanations.
  - Re-submitting an already graded quiz returns `400 QUIZ_ALREADY_SUBMITTED` (`BR-07`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_ai_quiz_oauth_admin.py -v` (quiz generate/submit/privacy coverage; `tests/integration/test_quiz_api.py` does not exist)
  - Screenshot: Swagger UI execution of `/api/v1/quiz/generate` showing generated quiz questions.

---

## Phase 7: Reading Data & Community Feedback (Features I & E)

### [BE-13] Tab-Isolated Conversations & Message History
- **Feature Reference**: Feature D (`FR-CNT-05~07`), Feature I (`FR-HIS-01~10`), `ADR-012`
- **Description**: Manage reading conversation threads, guaranteeing strict tab isolation via `reading_session_id`, chronological message retrieval, source grounding flags, and soft deletion with tombstone persistence.
- **Plan & Codebase**:
  - `app/schemas/conversation.py`: `ConversationResponse`, `MessageResponse` (with `is_grounded`, `uncertainty_flag`).
  - `app/services/conversation_service.py`: Create sessions, bind `reading_session_id`, append messages (in an atomic transaction that bumps `conversations.updated_at = :sync_timestamp` and `conversations.version = version + 1`), list conversations with search, and soft delete conversations (`is_deleted = TRUE`).
  - `app/routers/conversations.py`: `GET /conversations`, `GET /conversations/{id}/messages` (returns 404 if conversation is soft-deleted), `DELETE /conversations/{id}`.
- **Acceptance Criteria**:
  - Conversations from different browser tabs remain isolated using client-provided `reading_session_id`; mismatched un-bound requests reject with `400 TAB_CONTEXT_MISMATCH` (`FR-CNT-05`).
  - Appending a message atomically increments conversation `version` and updates `updated_at`, ensuring sync detection and proper sorting.
  - Historical messages include `is_grounded` and `uncertainty_flag` metadata.
  - `DELETE /conversations/{id}` performs soft delete (`is_deleted = TRUE`), generating a sync tombstone retained for 30 days. Child messages are hidden from GET queries.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_stream_review.py tests/integration/test_concurrency_privacy_review.py tests/integration/test_review_regressions.py -v` (no dedicated `test_conversations_api.py`; tab binding, soft delete and tombstone coverage live there)
  - Screenshot: Swagger UI response for `/api/v1/conversations/{id}/messages` showing message history with grounding metadata.

---

### [BE-14] Reading History & Web Highlights Storage
- **Feature Reference**: Feature I (`FR-HIS-01~06`, `BR-18~21`)
- **Description**: Store visited reading pages, dwell time, and user-saved text highlights with color tags and notes. Support bulk history clearance without deleting account credentials.
- **Plan & Codebase**:
  - `app/schemas/reading.py`: `ReadingHistoryCreate`, `ReadingHistoryResponse`, `HighlightCreate`, `HighlightResponse`, `HighlightListResponse`.
  - `app/services/reading_service.py`: Record history (bypassed if privacy mode or blacklisted domain), save highlights, clear history.
  - `app/routers/reading.py`: `POST /api/v1/reading/history`, `GET /api/v1/reading/history`, `DELETE /api/v1/reading/history`, `POST /api/v1/reading/highlights`, `GET /api/v1/reading/highlights`, `DELETE /api/v1/reading/highlights/{id}`.
- **Acceptance Criteria**:
  - If `privacy_mode_enabled: true` or URL is blacklisted, `POST /api/v1/reading/history` returns `200 OK` with `data: null` and message `"History logging skipped by privacy policy"` without writing to DB.
  - `GET /api/v1/reading/history` returns paginated reading logs with dwell time and cached summaries using query params `page` and `page_size`.
  - Dedicated endpoint `GET /api/v1/reading/highlights` lists highlights with pagination and `page_url` filter.
  - `DELETE /api/v1/reading/highlights/{id}` soft-deletes a highlight (`is_deleted = TRUE`, `version = version + 1`, `updated_at = :sync_timestamp`), returns `204 No Content`, and preserves a sync tombstone for cross-device synchronization (`FR-HIS-06`).
  - `DELETE /api/v1/reading/history` clears browsing logs and atomically sets `conversations.page_url = NULL, conversations.page_title = NULL` to eliminate past browsing ghost footprints under GDPR (`FR-HIS-05`, `FR-HIS-07`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_concurrency_privacy_review.py tests/integration/test_text_email_domain_errors.py tests/integration/test_send_disconnect_domain_password.py -v` (no dedicated `test_reading_history_api.py`)
  - Screenshot: Response of `DELETE /api/v1/reading/history` returning `204 No Content` and verifying database rows wiped.

---

### [BE-15] User Feedback & Accuracy Reporting
- **Feature Reference**: Feature E (`BR-15`, `BG-08`)
- **Description**: Allow users to rate AI responses (helpful / unhelpful) and report inaccuracies or hallucinations to track AI answer quality. Enforce message ownership and duplicate UPSERT.
- **Plan & Codebase**:
  - `app/schemas/feedback.py`: `AiFeedbackCreateRequest` (`message_id`, `rating`, `report_reason`, `comment`).
  - `app/services/feedback_service.py`: Record or atomically update feedback linked to user and message. Verify message belongs to user's conversation (`403 FORBIDDEN_RESOURCE` if not).
  - `app/routers/ai.py`: Mount `POST /api/v1/ai/feedback`.
- **Acceptance Criteria**:
  - Authenticated user can submit feedback for an existing message.
  - Duplicate feedback updates the existing rating.
  - Submitting feedback on a non-existent message returns `404 MESSAGE_NOT_FOUND`.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_ai_quiz_oauth_admin.py tests/integration/test_text_email_domain_errors.py -v` (no dedicated `test_feedback_api.py`)
  - Screenshot: Swagger UI response for `POST /api/v1/ai/feedback` returning `201 Created`.

---

## Phase 8: Multi-Device Sync & Concurrency (Feature J)

### [BE-16] Multi-Device Incremental Synchronization & Conflict Resolver
- **Feature Reference**: Feature J (`FR-SYN-01~08`), `ADR-007`, `ADR-013`
- **Description**: Implement incremental pull and push endpoints using optimistic locking and one unified position/checkpoint cursor over `(updated_at, entity_type, id)`. Use ADR-013's user-row lock and monotonic sync clock to order concurrent commits.
- **Plan & Codebase**:
  - `app/schemas/sync.py`: `SyncPullRequest` (with one opaque Base64url position/checkpoint cursor (ADR-013)), `SyncPullResponse`, `SyncPushRequest`, `SyncConflictResponse`.
  - `app/services/sync_service.py`: Query mutable entities (`conversations`, `highlights`, `user_settings`) using one merged `(updated_at, entity_type, id)` cursor, the user-row sync clock and completed checkpoints (ADR-013). Excludes `messages` (loaded on-demand). Compare entity `version` and `updated_at`.
  - `app/cli/purge_tombstones.py`: CLI maintenance utility (`python -m app.cli.purge_tombstones --days 30`) to permanently delete tombstones older than 30 days (PostgreSQL `ON DELETE CASCADE` purges child messages and feedback).
  - `app/routers/sync.py`: Mount `POST /api/v1/sync/pull` and `POST /api/v1/sync/push`.
- **Acceptance Criteria**:
  - `POST /sync/pull` merges entity types before applying `limit` (max 100); returns only one `next_cursor` and `has_more`, including an advanced checkpoint for empty/final pages. Cover same timestamps, concurrent/late commits and repeated higher-version rows.
  - `410 CURSOR_EXPIRED` rebuilds only the synced cache through staging storage; preserve credentials, drafts, ephemeral state and pending mutations. Failed rebuilds preserve the old checkpoint/cache. Conflicting pending mutations require resolution before submission; no silent overwrite/resurrection.
  - `POST /sync/push` applies mutations atomically via conditional SQL update (`WHERE id = :id AND version = :base_version RETURNING id`), strictly preventing multi-threaded race condition silent overwrites (`FR-SYN-05`).
  - In a conflict situation (stale version submitted), server returns `409 SYNC_CONFLICT` with both versions, strictly preventing silent data loss (`FR-SYN-05`).
  - In-flight unsent drafts are excluded from synchronization (`FR-SYN-07`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_concurrency_privacy_review.py tests/integration/test_text_email_domain_errors.py tests/unit/test_review_regressions.py -v` (no dedicated `test_sync_engine.py`; pull cursor + push conflict coverage live there)
  - Screenshot: Postman response showing `409 Conflict` payload containing conflicting server and client entities.

---

## Phase 9: Quality Assurance & Integration (NFRs)

### [BE-17] End-to-End Integration Test Suite & Coverage Baseline
- **Feature Reference**: SRS §4.2, `NFR-REL-01~05`, `NFR-SEC-01~08`
- **Description**: Implement a full end-to-end test suite simulating realistic client user journeys from registration through AI streaming, quiz generation, and data synchronization.
- **Plan & Codebase**:
  - `tests/conftest.py`: Async SQLite/PostgreSQL test fixtures, mocked AI provider clients, authenticated client sessions.
  - `tests/integration/test_user_journey.py`: Complete user journey test.
  - `tests/integration/test_security_rules.py`: Verify AES-256 vault security, no plaintext keys in logs, and CORS isolation.
- **Acceptance Criteria**:
  - Total test coverage across service and router layers reaches **≥ 80%**.
  - All tests pass via `pytest --cov=app`.
  - Linter (`black --check app/`, `ruff check app/`, `mypy app/`) passes with zero errors.
- **Verification / Screenshot**:
  - Command: `pytest -v --cov=app --cov-report=term-missing` with full-integration env (`READHEAD_FULL_INTEGRATION=1` + PostgreSQL/Redis URLs)
  - Note: named files `tests/integration/test_user_journey.py` and `tests/integration/test_security_rules.py` do not exist; journey coverage is distributed across the integration suite and vault security lives in `tests/unit/test_security_vault.py`
  - Screenshot: Terminal output showing 100% passed test suite and code coverage summary table.

---

## Phase 10: Admin Management, Telemetry & Rate Limiting (Platform Ops)

### [BE-18] Admin Portal API, Telemetry Engine & Redis Rate Limiter
- **Feature Reference**: Web Management Portal, Feature L (`FR-OPS-01~05`)
- **Description**: Implement platform telemetry aggregation, user management (suspend/ban accounts), feedback browsing, and Redis-backed asynchronous IP/User rate limiting.
- **Plan & Codebase**:
  - `app/core/limiter.py`: Configure the native async Redis limiter to protect AI endpoints from burst abuse (keys by `user_id` for authenticated routes; uses `X-Forwarded-For` with proxy headers for public routes; falls back to in-memory if Redis down).
  - `app/cli/create_admin.py`: CLI command (`python -m app.cli.create_admin --email ... --password ...`) to bootstrap the initial superuser account.
  - `app/schemas/admin.py`: `TelemetryResponse`, `AdminUserListResponse`, `UserStatusUpdateRequest`, `AdminFeedbackResponse`.
  - `app/services/admin_service.py`: Aggregate request volume, upstream model breakdown (without reading user prompt text), update account statuses, list feedback logs.
  - `app/routers/admin.py`: Mount `GET /api/v1/admin/telemetry`, `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{id}/status`, `GET /api/v1/admin/feedback` protected by `require_admin` dependency.
- **Acceptance Criteria**:
  - All `/api/v1/admin/*` endpoints strictly reject non-admin users with `403 FORBIDDEN_RESOURCE`.
  - Telemetry numbers are aggregated purely from counters and logs with **zero plaintext user reading materials exposed** (strict privacy isolation guarantee).
  - Admin feedback table applies heuristic PII redaction to the `comment` field before presentation.
  - Rejects attempts by an administrator to suspend, ban, or modify their own status (`400 CANNOT_MODIFY_SELF_STATUS`).
  - Banning/suspending a user updates PostgreSQL `users.status`, revokes all auth sessions and active refresh tokens with reason `security`, cleans session-indexed grace caches, and immediately sets `revoked_users:{user_id}` in Redis (TTL=3600s). Re-activating deletes the Redis key but never reopens revoked sessions.
  - Excessive requests hit rate limits with standard `429 Too Many Requests` headers; SSE endpoint limits active concurrency to max 2 streams.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_admin_portal.py -v`
  - Screenshot: Swagger/Postman output showing `GET /api/v1/admin/telemetry` returning telemetry JSON and `PATCH /api/v1/admin/users/{id}/status` successfully banning an account.

---

## Phase 11: Email Trust & Usage Analytics (Feature A extension)

### [BE-19] Email Verification & Password Reset (Resend)
- **Feature Reference**: Feature A (`FR-ACC-01~06`), `FR-OPS-03`, `.docs/api/endpoints.md` §2.7, §3.5, §9.5; `.docs/technical/auth-flow.md` §2.5, §2.7–2.9
- **Description**: Make email verification mandatory for password accounts. Registration dispatches a Resend verification email fire-and-forget; unverified login is blocked (`403 EMAIL_NOT_VERIFIED`); a full forgot/reset flow revokes all sessions on success; email changes re-verify ownership; admins can trigger reset links. Full attack-scenario hardening (anti-enumeration, email-bombing and token-abuse controls) per `.docs/api/endpoints.md` §10.
- **Plan & Codebase**:
  - `app/models/token.py` (or `app/models/email_token.py`): `EmailVerificationToken` and `PasswordResetToken` models — `user_id` FK cascade, unique `token_hash` (SHA-256 hex of a 256-bit URL-safe token), `expires_at`, nullable `used_at`, `created_at`; indexes on `(user_id)` and `(token_hash)`.
  - `alembic/versions/`: new revision `0004_add_email_verification_and_password_reset_tokens` (see `.docs/database/migrations.md`); ORM models updated before autogenerate.
  - `app/services/email_service.py`: Resend delivery via direct `httpx` `POST https://api.resend.com/emails` (no SDK; see `.docs/technical/dependencies.md`), 3 retries with exponential backoff on 429/5xx/timeout, no retry on other 4xx, sanitized logging (`FR-OPS-03`: never log tokens/links/mail payloads), `verification_email_sent` outcome.
  - `app/services/auth_service.py`: registration hook (create token row + dispatch after user commit), login `is_verified` gate returning `403 EMAIL_NOT_VERIFIED` with `can_resend: true`, token consumption with `secrets.compare_digest` and atomic `used_at` write, reset flow revoking all `auth_sessions` with reason `security` (mechanism of auth-flow §2.5), change-email password re-check/uniqueness/re-verification.
  - `app/routers/auth.py`: `POST /auth/verify-email/resend` (auth optional, per-email 3/hour cap + shared auth bucket, uniform neutral 200), `POST /auth/verify-email` (`400 VERIFICATION_TOKEN_EXPIRED` / `400 VERIFICATION_TOKEN_INVALID`, idempotent already-verified 200), `POST /auth/forgot-password` (always neutral 200, stable timing), `POST /auth/reset-password` (`400 RESET_TOKEN_EXPIRED` / `400 RESET_TOKEN_INVALID`, success revokes all sessions).
  - `app/routers/users.py`: `PATCH /users/me` (`full_name`; email change requires `current_password`, unique new email, `is_verified = FALSE`, verification mail to the new address, old email effective until verified).
  - `app/routers/admin.py`: `POST /admin/users/{id}/send-reset-link` (admin-only, same per-email cap, audit-logged).
  - `app/core/config.py`: `RESEND_API_KEY`, `MAIL_FROM_ADDRESS`, `APP_BASE_URL`, `VERIFICATION_TOKEN_TTL_HOURS`, `PASSWORD_RESET_TOKEN_TTL_MINUTES`, `VERIFICATION_RESEND_LIMIT_PER_HOUR`.
- **Acceptance Criteria**:
  - Register returns `201` immediately with `verification_email_sent` reflecting dispatch outcome; mail failure (including total Resend outage after 3 retries) NEVER fails registration; token row stores only the SHA-256 hash (database inspection confirms no plaintext).
  - Login with `is_verified = FALSE` returns `403 EMAIL_NOT_VERIFIED` (`can_resend: true`) and creates no `auth_sessions` row; after consuming a valid token, login succeeds; OAuth flows are unchanged.
  - `verify-email`: expired token → `400 VERIFICATION_TOKEN_EXPIRED`; unknown or reused token → `400 VERIFICATION_TOKEN_INVALID`; replayed link on a verified account → neutral 200 (idempotent).
  - `forgot-password` returns the identical neutral 200 for registered and unregistered addresses with stable response timing (measured in tests); `reset-password` applies the 8–72 byte password rule and, on success, marks the token used and revokes every user session with reason `security` — old access/refresh tokens fail authoritative checks on all devices and in-flight streams terminate.
  - Resend limits: the 4th verification email within one hour for the same address returns `429 RATE_LIMIT_EXCEEDED` with `Retry-After`; unknown addresses consume the same per-email budget.
  - Anti-enumeration tests: register/forgot/resend responses for existing vs non-existing emails are byte-identical; timing difference for `forgot-password` stays below the test threshold; no endpoint echoes token or verification state for foreign addresses.
  - `PATCH /users/me` email change requires the correct `current_password` (`401 INVALID_CREDENTIALS` otherwise), rejects duplicates (`409 EMAIL_ALREADY_EXISTS`), sets `is_verified = FALSE`, mails the NEW address, and the old email remains the login identity until verification completes.
  - Admin send-reset-link rejects non-admins with `403 FORBIDDEN_RESOURCE` and is rate-limited per target email.
  - Migration `0004` passes `alembic upgrade head` / `downgrade -1` / `upgrade head`; token tests cover expiry, single-use reuse, brute-forced resend and enumeration-timing scenarios.
- **Verification / Screenshot**:
  - Test: new `tests/integration/test_email_verification_reset.py` (token expiry, reuse, resend brute force, enumeration timing) plus existing auth regression files.
  - Screenshot: Resend dashboard/test inbox showing the verification email; Swagger UI showing `403 EMAIL_NOT_VERIFIED` before and `200 OK` token pair after verification.

---

### [BE-20] AI Usage Tracking
- **Feature Reference**: Feature E (`FR-AI-01~12`), BG-08, ADR-016; `.docs/api/endpoints.md` §3.6, §5.2, §8
- **Description**: Record per-user daily AI usage aggregates from provider terminal frames into `usage_daily` (upsert-increment), expose them via `GET /users/me/usage`, and add `input_tokens`/`output_tokens` to the SSE done event. Privacy Mode keeps recording aggregate usage with zero content linkage; admin per-user usage is out of scope (privacy guard).
- **Plan & Codebase**:
  - `app/models/usage.py`: `UsageDaily` model — `user_id` FK cascade, `date` (DATE, UTC), `provider`, `model`, `request_count`, `input_tokens`/`output_tokens` (BIGINT), unique constraint `[user_id, date, provider, model]`.
  - `alembic/versions/`: new revision `0005_add_usage_daily` (see `.docs/database/migrations.md`).
  - `app/core/ai/openai_adapter.py`: request `stream_options: {"include_usage": true}` and parse the final usage chunk. `app/core/ai/claude_adapter.py`: read usage from the `message_delta` terminal frame. `app/core/ai/gemini_adapter.py`: read `usageMetadata` (`promptTokenCount`/`candidatesTokenCount`/`totalTokenCount`) from the final chunk. All three: missing metadata → `None`, never fabricated.
  - `app/services/ai_service.py`: after the upstream ends (and after the final revocation check, before/with persistence), perform the upsert-increment (`INSERT ... ON CONFLICT [user_id, date, provider, model] DO UPDATE SET request_count = usage_daily.request_count + 1, input_tokens = usage_daily.input_tokens + COALESCE(EXCLUDED.input_tokens, 0), ...`); counts stay aggregate-only — no message IDs, prompts or response text. Privacy Mode: the usage write STILL happens (no content linkage), unlike conversation/message writes.
  - `app/routers/ai.py`: extend the `event: done` payload with `input_tokens` and `output_tokens` (null when metadata is missing; existing nullable `total_tokens` behavior unchanged).
  - `app/routers/users.py` + `app/schemas/user.py`: `GET /users/me/usage?period=day|month&from=&to=` returning `{period, items: [{date, provider, model, request_count, input_tokens, output_tokens}]}` with bounded range validation.
- **Acceptance Criteria**:
  - Each completed standard-mode generation increments exactly one `usage_daily` row per `(user_id, date, provider, model)`; concurrent completions aggregate atomically (no lost increments; unique constraint holds).
  - Usage metadata parsing: OpenAI (with `stream_options.include_usage`), Anthropic (`message_delta`) and Gemini (`usageMetadata`) populate `input_tokens`/`output_tokens` in the done event and the aggregate; absent metadata leaves the done-event fields `null` (preserving the current null `total_tokens` contract) and stores zeros without error.
  - `usage_daily` is never written for content it cannot attribute to a completed generation: streams cancelled mid-flight before the terminal frame add no row (under-counting is accepted and documented).
  - Privacy Mode: generating a private request still increments usage while writing zero conversation/message rows; the aggregate contains no message IDs, URLs, prompts or response content (schema review + test asserts column set).
  - `GET /users/me/usage` returns only the authenticated user's aggregates grouped per day/provider/model for `day` and `month` periods; out-of-range `from`/`to` return `422 VALIDATION_ERROR`; other users' rows are never reachable (owner isolation test).
  - No `/sync` change: `usage_daily` and `user_api_keys` remain outside pull/push (§8 contract unchanged).
  - No admin endpoint exposes per-user usage (privacy guard); admin telemetry remains aggregate and content-free.
  - Migration `0005` passes `alembic upgrade head` / `downgrade -1` / `upgrade head`.
- **Verification / Screenshot**:
  - Test: new `tests/unit/test_usage_parsing.py` (three providers' terminal frames, missing metadata) and `tests/integration/test_usage_tracking.py` (upsert increments, privacy mode, owner isolation, cancelled streams); SSE done-event assertion added to the streaming regression files.
  - Screenshot: `usage_daily` rows after a mixed multi-provider session alongside `GET /users/me/usage` JSON; SSE `event: done` showing `input_tokens`/`output_tokens`.

---

## Phase 12: Language, Quiz History & Personalization Governance (Feature B/F/G extension)

### [BE-21] Language Settings & Translate Behavior
- **Feature Reference**: Feature B (`FR-CFG-01~07`), Feature E (BR-05), BG-02; `.docs/api/endpoints.md` §3.3–3.4, §5.2, §8; `.docs/api/error-codes.md` (`400 UNSUPPORTED_LANGUAGE`)
- **Description**: Introduce `ui_language` (extension UI language, `vi`/`en` only, separate from translation) alongside `target_language`, enforce the supported-translation-language enum (`vi`, `en`, `ja`, `zh`, `ko`, `fr`, `de`, `es`) on both settings and per-request overrides with `400 UNSUPPORTED_LANGUAGE`, document the settings-omission fallback, and pin the translate-task prompt behavior to "translate AND explain terminology in context" (BR-05).
- **Plan & Codebase**:
  - `app/models/user_setting.py` + migration `0006_language_consent_and_quiz_history` (shared with BE-22/BE-23): add `ui_language VARCHAR(10) NOT NULL DEFAULT 'vi'`.
  - `app/schemas/user.py`: add `ui_language` to `UserSettingResponse`/`UserSettingUpdateRequest`; `target_language` restricted to the 8-language set.
  - `app/services/user_service.py`: PATCH/sync normalization rejects `ui_language ∉ {vi, en}` and `target_language` outside the supported set with `400 UNSUPPORTED_LANGUAGE` (`field`-attributed), reusing the enum-validation mapping pattern of `UNSUPPORTED_PROVIDER` (ISSUE-032); sync push validates mutable settings fields with the same rule (`INVALID_SYNC_MUTATION` for invalid sync payload values remains per §8.2).
  - `app/schemas/ai.py` + `app/services/ai_service.py`: optional per-request `target_language` validated against the same set (`400 UNSUPPORTED_LANGUAGE` before any LLM dispatch); omitted value falls back to the stored settings value; settings value is never mutated by an override; no `source_language` parameter exists — source language is auto-detected.
  - `app/core/ai/grounding.py` / prompt templates: translate-task system prompt instructs the model to translate AND explain the meaning of domain/technical terms in context (BR-05); response stays a plain text stream (no schema/endpoint change).
- **Acceptance Criteria**:
  - `PATCH /users/me/settings` with `ui_language: "fr"` returns `400 UNSUPPORTED_LANGUAGE` with `field="ui_language"`; `ui_language: "en"` persists and the settings GET/sync entities carry both `ui_language` and `target_language`.
  - `target_language: "xx"` in settings PATCH and in `/ai/stream` both return `400 UNSUPPORTED_LANGUAGE`; the 8 supported codes are accepted in both places.
  - `/ai/stream` `task: "translate"` without `target_language` uses the settings value; with an explicit value it overrides for that request only and a subsequent settings GET shows the original value (override does not persist).
  - Translate responses explain in-context terminology per the prompt behavior; the response remains an ordinary SSE text stream (`start`/`token`/`done` events unchanged).
  - Invalid language values never reach a provider call (no quota spent on rejected requests).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_concurrency_privacy_review.py tests/integration/test_text_email_domain_errors.py -v` plus new settings/stream language-validation cases; settings sync assertions confirm both fields travel through `/sync/pull` and `/sync/push`.
  - Screenshot: Swagger UI showing `PATCH /users/me/settings` accepting `ui_language` and returning `400 UNSUPPORTED_LANGUAGE` for an unsupported code, plus a translate stream done event.

---

### [BE-22] Quiz History API
- **Feature Reference**: Feature F (`FR-CMP-01~05`), BG-03; `.docs/api/endpoints.md` §6.2–6.5, §8; `.docs/database/schema.md` §2.10
- **Description**: Expose persistent quiz history via `GET /quiz` (paginated list with date/domain/status filters), `GET /quiz/stats` (daily aggregates for the dashboard chart) and `GET /quiz/{quiz_id}` (detail with review answers); extend `quiz_records` with `submitted_at`/`page_title`, add history indexes and migration `0006`; keep Privacy-Mode quizzes excluded, tombstoned/expired quizzes at `404 QUIZ_NOT_FOUND`, and submitted quizzes non-retryable.
- **Plan & Codebase**:
  - `app/models/quiz.py` + migration `0006_language_consent_and_quiz_history`: add `submitted_at TIMESTAMPTZ NULL`, `page_title VARCHAR(500) NULL`; indexes `idx_quiz_records_user_created (user_id, created_at DESC)` and `idx_quiz_records_user_score (user_id, score)`. `total_questions` stays derived from `questions_payload` JSONB — no new column.
  - `app/services/quiz_service.py`: stamp `submitted_at` on successful grading; stamp `page_title` at generation; derive `total_questions` from the payload; history/stats queries filter by `created_at` UTC date range (max 366 days → `422 VALIDATION_ERROR`), optional normalized `domain`, and `status=submitted|unsubmitted|all` (default `all`).
  - `app/routers/quiz.py`: mount `GET /quiz`, `GET /quiz/stats`, `GET /quiz/{quiz_id}` under the general rate bucket (`API_REQUESTS_PER_MINUTE`, 120/min) — NOT `AI_REQUESTS_PER_MINUTE`.
  - Privacy-Mode ephemeral quizzes (Redis-only, 30-minute TTL) never appear in lists/stats; expired/tombstoned/foreign IDs return `404 QUIZ_NOT_FOUND` on detail lookup; unsubmitted quizzes return `is_submitted: false` with answers/explanations still hidden; submitted quizzes keep the `400 QUIZ_ALREADY_SUBMITTED` guard with no retry path.
- **Acceptance Criteria**:
  - `GET /quiz` returns the documented pagination envelope with items `{id, page_url, page_title, total_questions, score, is_submitted, created_at, submitted_at}`; a user with no history gets `200` with empty `items`/`total: 0`, never an error.
  - Date filtering honors UTC day boundaries (inclusive `from`, inclusive `to`); a range over 366 days returns `422 VALIDATION_ERROR`; `status=unsubmitted` returns only `is_submitted: false` rows with `score: null`/`submitted_at: null`.
  - `GET /quiz/stats` returns `{days: [{date, attempts, avg_score}], overall: {total_submitted, avg_score}}` counting only submitted quizzes; `GET /quiz/{quiz_id}` returns full questions with `selected_option`/`correct_option`/`explanation` only when submitted, and hides them while unsubmitted.
  - Privacy-Mode generated quizzes never appear in list/stats/detail; after Redis expiry the detail lookup returns `404 QUIZ_NOT_FOUND`.
  - Submitting an already-submitted quiz still returns `400 QUIZ_ALREADY_SUBMITTED`; there is no retry/reset.
  - Quiz endpoints are throttled by the general bucket, not the AI/quiz generation bucket.
  - Migration `0006` passes `alembic upgrade head` / `downgrade -1` / `upgrade head`.
- **Verification / Screenshot**:
  - Test: new `tests/integration/test_quiz_history.py` (empty history, unsubmitted flag, UTC date boundary, 366-day limit, Redis expiry → 404, privacy exclusion, owner isolation, general-bucket limit) plus existing quiz regressions.
  - Screenshot: Swagger UI showing `GET /quiz` paginated history and `GET /quiz/stats` aggregate JSON; database view of `quiz_records` showing `submitted_at`/`page_title` columns.

---

### [BE-23] Proactive Dedup + Personalization Consent
- **Feature Reference**: Feature G (`FR-PRV-01~06`), BG-05, ADR-017; ISSUE-015/ISSUE-043; `.docs/api/endpoints.md` §3.4, §5.3
- **Description**: Close ISSUE-043 with a Redis TTL dedup cache in front of the proactive LLM call (keyed `(user_id, paragraph_hash)`, TTL 300s; hit → `{has_suggestion: false}` without calling the LLM), and implement `personalization_consent` (ADR-017) as an independent opt-in column in `user_settings` enforced under the user row lock before any personalization use.
- **Plan & Codebase**:
  - `app/services/ai_service.py` (`evaluate_proactive_suggestion` path): before any provider dispatch, compute a SHA-256 hash of the normalized paragraph text and check Redis key `proactive_dedup:{user_id}:{paragraph_hash}`. On hit, return `{"has_suggestion": false}` immediately. On a completed suggestion, `SET` the key with TTL 300 seconds (5 minutes); upstream errors write nothing. Cache is Redis-only — no DB persistence, no schema change for the cache itself, skipped silently in Redis degraded mode.
  - `app/models/user_setting.py` + migration `0006_language_consent_and_quiz_history` (shared with BE-21/BE-22): add `personalization_consent BOOLEAN NOT NULL DEFAULT FALSE`.
  - `app/schemas/user.py` + `app/services/user_service.py`: expose `personalization_consent` in settings GET/PATCH and the sync entity; boolean validation; revocation sets the flag to FALSE without deleting any stored data; update paths go through the ADR-013 user-row lock so the new value is immediately effective for concurrent content writes (ISSUE-015 re-read pattern).
  - Personalization enforcement rule (ADR-017): any current or future code path that reads `reading_history` or AI interactions to personalize behavior (adapt explanation level/detail, improve proactive suggestions) MUST re-read `personalization_consent` under the user row lock and skip personalization when FALSE; admins see no personalization data.
- **Acceptance Criteria**:
  - Calling `/ai/proactive-suggest` twice with the same paragraph within 300 seconds results in exactly one LLM dispatch; the second call returns `{has_suggestion: false}` (asserted via provider call-counting with synthetic HTTP).
  - After the 300-second TTL expires, the same paragraph triggers a fresh LLM call; different paragraphs never share a cache entry; failed upstream calls do not populate the cache.
  - The dedup cache never touches PostgreSQL and `/sync` behavior is unchanged.
  - New users default to `personalization_consent: false`; PATCH to `true`/`false` persists and increments `version`; the field travels through `/sync/pull` and `/sync/push` settings payloads.
  - Revoking consent does NOT delete `reading_history`/conversation/AI-interaction rows (data remains intact after revoke) and does not toggle `privacy_mode_enabled`; the two flags are independently mutable.
  - A consent flip concurrent with a content write is observed under the user lock: personalization behavior re-reads consent after acquiring the lock (no stale snapshot).
- **Verification / Screenshot**:
  - Test: new `tests/integration/test_proactive_dedup_consent.py` (cache hit without provider call, TTL expiry re-dispatch, per-user/per-paragraph isolation, consent default/revoke/sync, independence from privacy mode, lock-ordered re-read) plus `tests/integration/test_ai_quiz_oauth_admin.py` regressions.
  - Screenshot: Redis CLI showing `proactive_dedup:*` keys with TTL 300 alongside a `user_settings` row with `personalization_consent`; provider-call-count assertion output proving one dispatch per dedup window.

---

## Phase 13: Insights, Export & History Management Hardening (Feature I/G extension)

### [BE-24] Reading Stats & Comprehension Insights
- **Feature Reference**: Feature I (`FR-HIS-01~06`), Feature G (`FR-PRV-01~06`), BG-03/BG-08, ADR-018; `.docs/api/endpoints.md` §3.8, §5.3, §7.10
- **Description**: Expose `GET /reading/history/stats?from&to` (on-the-fly reading statistics) and `GET /users/me/reading-insights?from&to` (rule-based per-domain comprehension insight aggregates computed from `quiz_records` + `messages`⋈`conversations` — no new table, no ML), and add the optional consent-gated `insight` enrichment with a 2/day/domain anti-spam cap to `POST /ai/proactive-suggest` (ADR-018).
- **Plan & Codebase**:
  - `app/services/reading_service.py` + `app/routers/reading.py`: `GET /reading/history/stats` — bounded UTC date-range aggregate of `reading_history` (`articles_count`, `total_reading_time_seconds`, host-normalized `top_domains` capped at 5, bounded `recent` list). No dedicated stats table; general API bucket.
  - `app/services/insight_service.py` (new) + `app/routers/users.py`: `GET /users/me/reading-insights` — per-`(user, domain)` aggregates: quiz decay (avg of latest 5 quizzes vs previous 5; avg < 0.6 AND declining → `difficulty_signal` medium/high), `assist_request_rate` (user-turns per domain normalized by visits; `messages` has no `task` column, so user-turns are the proxy per ADR-018), `has_sufficient_data` (false when < 2 submitted quizzes AND < 3 user turns). Dwell alone never raises the signal.
  - `app/core/config.py`: all thresholds as configurable constants/env (`INSIGHT_QUIZ_WINDOW`, `INSIGHT_DECAY_FLOOR`, `INSIGHT_MIN_QUIZZES`, `INSIGHT_MIN_TURNS`, `INSIGHT_DAILY_CAP_PER_DOMAIN`, …) — no hard-coded rule values.
  - `app/services/ai_service.py` (proactive path): after the plain hint, aggregate the current domain on-the-fly; attach `insight: {domain_difficulty, suggested_action}` ONLY when `personalization_consent == true` re-read under the user row lock (ADR-017), the daily cap (Redis counter `insight_cap:{user_id}:{domain}`, TTL 24h) is not exhausted, and no 24h dismissal cache (`insight_dismissed:{user_id}:{domain}`) exists. Cap reached or dismissed → omit `insight`; the ordinary hint still functions under the existing 5-minute dedup cache. Redis degraded mode skips cap/dismissal checks.
  - No migration: no new table is introduced (insights are on-the-fly; ADR-018).
- **Acceptance Criteria**:
  - `GET /reading/history/stats` returns the documented shape; UTC date boundaries are inclusive; a range over 366 days returns `422 VALIDATION_ERROR`; after `DELETE /reading/history` the aggregate resets to zero on the next call.
  - `GET /users/me/reading-insights` with **insufficient data** (e.g. 1 submitted quiz, 1 user turn) returns the domain with `has_sufficient_data: false` and its `sample_size` — never an error and never a fabricated difficulty signal.
  - **Consent gate**: with `personalization_consent = false` the insights endpoint still returns data (viewing needs no consent), while `POST /ai/proactive-suggest` never includes the `insight` field; with consent `true` (re-read under the user lock, verified against a concurrent consent flip) the field may appear.
  - **False-positive guard**: a domain with high dwell time but no low/declining quiz scores and no elevated assist rate yields `difficulty_signal: "none"`/`"low"` — dwell alone never triggers `medium`/`high`.
  - **Daily cap**: the 3rd insight-enriched proactive response for the same domain within 24h omits `insight` while the plain hint still returns; the cap counter is keyed per `(user, domain)` with TTL 24h.
  - **Dismissal**: after a dismissal of an insight-type suggestion, subsequent proactive responses for that domain omit `insight` for 24h; the 5-minute paragraph dedup behavior for plain hints is unchanged.
  - **Privacy Mode**: with Privacy Mode enabled no new signals are written; aggregates read only previously stored rows (test: generate pre-toggle data, toggle privacy, verify insights still computed from old rows and no new rows appear).
  - **Reset**: bulk-deleting conversations and deleting history immediately changes the next insights response (on-the-fly, no stale cache).
  - Both endpoints are throttled by the general bucket, not the AI bucket.
- **Verification / Screenshot**:
  - Test: new `tests/integration/test_reading_insights.py` (empty/insufficient data, decay rule windows, consent gating under lock, cap + dismissal TTLs, privacy mode, reset-after-delete, rate bucket) plus `tests/integration/test_ai_quiz_oauth_admin.py` proactive regressions.
  - Screenshot: Swagger UI showing `GET /users/me/reading-insights` JSON and a proactive response with the optional `insight` object; Redis CLI showing `insight_cap:*`/`insight_dismissed:*` keys with TTL 24h.

---

### [BE-25] Data Export (GDPR Bundle)
- **Feature Reference**: Feature I (`FR-HIS-05~07`), BG-07; `.docs/api/endpoints.md` §3.7
- **Description**: Implement `GET /users/me/export` — a synchronous JSON bundle of every persisted entity owned by the user (profile, settings, reading history, highlights, conversations each with messages, quiz records, AI feedback), delivered as a `Content-Disposition: attachment` download with a dedicated 5/min rate limit. MD/PDF rendering stays client-side; the backend produces JSON only.
- **Plan & Codebase**:
  - `app/services/export_service.py` (new) + `app/routers/users.py`: `GET /users/me/export` — assemble the bundle in one bounded read pass (per-entity queries filtered by `user_id`); conversations embed their messages via a single joined fetch (no N+1).
  - Response headers: `Content-Type: application/json`, `Content-Disposition: attachment; filename="readhead-export-<timestamp>.json"`.
  - `app/core/config.py`: `EXPORT_SIZE_WARNING_BYTES` (default 50 MB). When the serialized bundle exceeds it, include `"size_warning"` in the bundle header advising client-side download prompts. Synchronous implementation — no job queue in the MVP.
  - Rate limit: general API bucket **plus** a dedicated 5/min per-user counter (same limiter infrastructure; exceeded → `429 RATE_LIMIT_EXCEEDED` with `Retry-After`).
  - Privacy Mode: private-mode data has no rows and is naturally absent; no special-casing needed beyond asserting the bundle only contains persisted rows.
- **Acceptance Criteria**:
  - The bundle contains all nine sections (`exported_at`, `profile`, `settings`, `reading_history`, `highlights`, `conversations` (each with embedded `messages`), `quiz_records`, `ai_feedback`, optional `size_warning`) and only the authenticated user's rows (owner-isolation test with a second seeded account).
  - **Privacy-mode data excluded**: generate a private-mode stream and ephemeral quiz, then export — no private conversation/message/quiz content appears (only persisted entities).
  - `Content-Disposition: attachment` header is present with the timestamped filename; the body parses as JSON under the standard `data` envelope.
  - The 6th export request within one minute returns `429 RATE_LIMIT_EXCEEDED` with `Retry-After`; the general bucket still applies independently.
  - A bundle over `EXPORT_SIZE_WARNING_BYTES` includes the `size_warning` note (covered with a lowered test threshold).
  - The endpoint performs no writes (no version bumps, no sync events; `/sync` behavior unchanged).
- **Verification / Screenshot**:
  - Test: new `tests/integration/test_data_export.py` (bundle completeness, owner isolation, privacy-mode exclusion, attachment header, 5/min limit, size-warning threshold) plus existing user regressions.
  - Screenshot: Swagger UI download of `GET /users/me/export` with response headers visible; database view showing the exported conversation/message counts match.

---

### [BE-26] Conversation Bulk Delete, Title Patch, Highlight Patch & Bookmark Cleanup
- **Feature Reference**: Feature I (`FR-HIS-04~06`), Feature J (`FR-SYN-01~08`); `.docs/api/endpoints.md` §7.1, §7.3, §7.3a, §7.3b, §7.7, §7.9a, §8.2; migration `0007`
- **Description**: Add bulk conversation delete (`DELETE /conversations`, tombstone all with streaming-skip semantics), conversation rename (`PATCH /conversations/{id}`), highlight editing (`PATCH /reading/highlights/{id}`), the 200-highlights-per-page limit, delete-while-streaming `409 CONVERSATION_BUSY`, and migration `0007_drop_reading_history_bookmark`.
- **Plan & Codebase**:
  - `app/services/conversation_service.py` + `app/routers/conversations.py`:
    - `DELETE /api/v1/conversations` — under the ADR-013 user lock, tombstone all non-deleted conversations (`is_deleted = TRUE`, `version + 1`, ADR-013 `updated_at`); conversations holding an active stream lease are **skipped**; response `{deleted_count, skipped_streaming}`; tombstones flow through `sync/pull` as per-item deletes. Does NOT touch `reading_history` or `DELETE /reading/history` semantics (anonymization contract unchanged).
    - `PATCH /api/v1/conversations/{id}` — update `title`, bump `version`, ADR-013 `updated_at`, sync `update` event; `404 CONVERSATION_NOT_FOUND` for tombstoned rows.
    - `DELETE /api/v1/conversations/{id}` — reject with `409 CONVERSATION_BUSY` when the conversation holds an active stream lease (client must stop the stream first).
  - `app/services/reading_service.py` + `app/routers/reading.py`:
    - `PATCH /api/v1/reading/highlights/{id}` — update `user_note`/`color` only, `version + 1`, ADR-013 `updated_at`, sync `update` event; `404 HIGHLIGHT_NOT_FOUND` (unknown/unowned/tombstoned); `422 VALIDATION_ERROR` for invalid color/oversized note/empty payload.
    - `POST /reading/highlights` — enforce max **200 non-deleted highlights per `page_url`**; exceeding returns `422 VALIDATION_ERROR` with `field="page_url"` and the current count in the detail. Duplicate highlight text is allowed (no dedup).
  - `app/models/reading_history.py` + `alembic/versions/`: revision `0007_drop_reading_history_bookmark` dropping the unused `is_bookmarked` column (downgrade re-adds it); remove the attribute from schemas/responses.
  - `app/services/sync_service.py`: document/verify push edge cases — stale `update` against a tombstoned row → `409 SYNC_CONFLICT` with `server_record.is_deleted = true`; duplicate `create` for an existing `entity_id` → `409 SYNC_CONFLICT` (no upsert); any 409 rolls back the entire batch (all-or-nothing, ISSUE-036).
- **Acceptance Criteria**:
  - Bulk delete tombstones every non-streaming conversation and returns `{deleted_count, skipped_streaming}`; a subsequent `sync/pull` delivers one delete tombstone per deleted conversation; re-running bulk delete is idempotent (`deleted_count: 0`).
  - A conversation streaming during bulk delete is skipped (`skipped_streaming: 1`) and its data remains intact; single `DELETE /conversations/{id}` against a streaming conversation returns `409 CONVERSATION_BUSY` with no tombstone written.
  - `PATCH /conversations/{id}` persists the title, bumps `version`, and other devices receive the `update` event via pull; renaming a tombstoned conversation returns `404 CONVERSATION_NOT_FOUND`.
  - `GET /conversations` excludes tombstones and matches the documented `ConversationSummary` shape (`version`/`is_deleted` absent from the list item).
  - `PATCH /reading/highlights/{id}` edits only `user_note`/`color`, bumps version, emits a sync `update`; invalid color/empty payload returns `422 VALIDATION_ERROR`; foreign/tombstoned IDs return `404 HIGHLIGHT_NOT_FOUND`.
  - The 201st highlight on one page returns `422 VALIDATION_ERROR` (`field="page_url"`); duplicates on the same page remain allowed.
  - Migration `0007` passes `alembic upgrade head` / `downgrade -1` / `upgrade head`; `reading_history.is_bookmarked` is absent after upgrade and restored after downgrade.
  - Sync push: stale update vs tombstone → `409 SYNC_CONFLICT` including `server_record.is_deleted = true`; duplicate create → `409 SYNC_CONFLICT`; a batch containing one 409 applies zero mutations (all-or-nothing).
  - `DELETE /reading/history` behavior is byte-identical to the existing contract (anonymization + conversation URL clearing unchanged by bulk delete work).
- **Verification / Screenshot**:
  - Test: new `tests/integration/test_conversation_bulk_delete.py` (bulk + streaming skip + tombstone pull, rename tombstone 404, delete-while-stream 409) and `tests/integration/test_highlight_edit_limits.py` (patch sync event, 200/page limit, duplicate allowance, migration roundtrip); push edge cases added to existing sync regression files.
  - Screenshot: Swagger UI showing bulk delete response `{deleted_count, skipped_streaming}` and the `422 VALIDATION_ERROR` for the 201st highlight; `\d reading_history` before/after migration `0007`.
