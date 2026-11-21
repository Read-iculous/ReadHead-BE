# ReadHead-BE — Backend Implementation Task Breakdown

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
```

---

## Phase 1: Foundation & Database

### [BE-01] Project Scaffolding, Core Config & Health Endpoint
- **Feature Reference**: Feature L (`FR-OPS-01~05`), `NFR-MNT-01`
- **Description**: Initialize the project directory layout, dependencies, environment settings via Pydantic Settings, database session lifecycle, error handlers, and a public `/api/v1/health` endpoint.
- **Plan & Codebase**:
  - `requirements.txt` & `requirements-dev.txt`: Pin FastAPI, Uvicorn, SQLAlchemy, asyncpg, redis, Pydantic, etc.
  - `app/core/config.py`: Implement `Settings` class loading `.env` parameters (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEY`, `CORS_ORIGINS`). Enforce Pydantic key separation validator (`JWT_SECRET_KEY != ENCRYPTION_MASTER_KEY`) failing fast on startup if identical.
  - `app/core/database.py`: Configure asynchronous engine `create_async_engine`, sessionmaker `AsyncSessionLocal`, and `get_db` dependency.
  - `app/core/redis.py`: Configure asynchronous Redis connection pool and ping utility.
  - `app/core/exceptions.py`: Define base `AppException` and exception handlers for standard JSON envelopes.
  - `app/core/logging.py`: Implement structured JSON logger emitting single-line JSON with automatic secret and PII masking (`[REDACTED]`) and request correlation ID.
  - `app/routers/health.py`: Create `GET /api/v1/health` returning system status, latency checks for database and redis.
  - `app/main.py`: Assemble FastAPI instance, CORS middleware with `allow_origin_regex=r"^chrome-extension://[a-z0-9]+$"` to support credentials without wildcard failures, router mounting, and lifespan management.
- **Acceptance Criteria**:
  - Server starts cleanly via `uvicorn app.main:app --port 8000`.
  - Application logs emit single-line JSON format with sensitive credentials/tokens masked as `[REDACTED]` (`FR-OPS-03`).
  - `GET /api/v1/health` returns `200 OK` with JSON checks (`checks.database` and `checks.redis` reporting healthy status and latency).
  - Returns `503 Service Unavailable` if PostgreSQL or Redis connection fails.
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
  - `app/models/user.py`: `User` and `OAuthAccount` models.
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
  - Screenshot: PostgreSQL GUI (pgAdmin / DBeaver / terminal `\dt`) showing all 11 tables created with correct foreign key constraints.

---

## Phase 2: Authentication & User Lifecycle (Feature A)

### [BE-03] Email/Password Authentication & JWT Token Management
- **Feature Reference**: Feature A (`FR-ACC-01~06`, `FR-SEC-01~03`)
- **Description**: Provide user registration with salted bcrypt password hashing, login verification, and token lifecycle management (short-lived Access Tokens + database-backed Refresh Tokens).
- **Plan & Codebase**:
  - `app/core/security.py`: Implement password hashing/verification using `passlib[bcrypt]`.
  - `app/core/auth.py`: Token generation (`create_access_token`, `create_refresh_token`), verification, and `get_current_user` dependency.
  - `app/models/refresh_token.py`: Store active refresh tokens with revocation flags and expiration.
  - `app/schemas/auth.py`: Pydantic schemas for `UserRegisterRequest`, `UserLoginRequest`, `TokenResponse`, and `TokenRefreshRequest`.
  - `app/services/auth_service.py`: Business logic for credential checking, duplicate email validation, token rotation, and 30-second Redis concurrency grace period.
  - `app/routers/auth.py`: Endpoints `POST /register`, `POST /login`, `POST /refresh`, `POST /logout`.
- **Acceptance Criteria**:
  - `POST /register` with valid data returns `201 Created` with User profile object (`id`, `email`, `full_name`, `role`, `status`).
  - Duplicate registration returns `409 EMAIL_ALREADY_EXISTS`.
  - Invalid login returns `401 INVALID_CREDENTIALS`.
  - Inactive/suspended user login returns `401 USER_SUSPENDED`.
  - Token hash comparisons use constant-time `secrets.compare_digest` to prevent timing attacks.
  - Auth dependency `get_current_user` catches `RedisError` gracefully and falls back to checking `users.status` directly in PostgreSQL if Redis is offline.
  - `POST /refresh` with valid refresh token rotates and issues a new access + refresh token pair.
  - Concurrent multi-tab refresh requests presenting the same old token within 30 seconds are safely served the new token pair without revocation errors.
  - Revoked or reused tokens outside the grace period return `401 REFRESH_TOKEN_REVOKED` and trigger immediate session invalidation.
  - `POST /logout` marks the refresh token as revoked in DB and purges Redis grace period cache.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_auth_api.py -v`
  - Screenshot: Postman or Swagger UI showing `POST /api/v1/auth/login` returning tokens and subsequent authenticated call to `/api/v1/users/me` with Bearer header.

---

### [BE-04] OAuth2 Integration (Google & GitHub)
- **Feature Reference**: Feature A (`FR-ACC-01`), `.docs/technical/auth-flow.md`
- **Description**: Implement third-party OAuth2 authentication endpoints for Google (via Google ID Token) and GitHub (via Auth Code), enforcing email verification and auto-linking external identities to ReadHead user accounts.
- **Plan & Codebase**:
  - `app/schemas/auth.py`: `GoogleAuthRequest` (`id_token`), `GitHubAuthRequest` (`code`).
  - `app/services/auth_service.py`: Add `authenticate_google()` verifying ID Token with Google and `authenticate_github()` fetching profile and verified primary email via GitHub API.
  - Enforce `email_verified == true` before account creation or auto-linking (`400 EMAIL_NOT_VERIFIED` or `400 OAUTH_EMAIL_MISSING`).
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
  - Test: `pytest tests/integration/test_user_lifecycle.py -v`
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
  - Test: `pytest tests/integration/test_settings_api.py -v`
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
  - Key rotation CLI successfully migrates existing `v1` ciphers to `v2` without interrupting running workers or causing downtime.
  - Logs never contain plaintext keys (`FR-KEY-07`, `FR-OPS-03`).
- **Verification / Screenshot**:
  - Test: `pytest tests/unit/test_security_vault.py tests/integration/test_api_keys_api.py -v`
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
  - Test: `pytest tests/unit/test_ai_adapters.py -v`
  - Output: Test log showing mocked streaming chunks successfully yielded from all three adapters.

---

### [BE-09] Real-Time SSE AI Streaming Endpoint
- **Feature Reference**: Feature E (`FR-AI-01~12`), `ADR-002`, `ADR-009`, `ADR-011`, `ADR-014`
- **Description**: Implement the central `/api/v1/ai/stream` Server-Sent Events endpoint handling Explain, Summarize, Translate, Simplify (Accessibility), and Multi-turn Chat. Enforce prompt injection fencing, max 2 concurrent SSE streams per user, zero-binary PDF text ingestion, and database session lifecycle decoupling (`ADR-014`).
- **Plan & Codebase**:
  - `app/schemas/ai.py`: `AiStreamRequest` (with task enum: `explain`, `summarize`, `translate`, `simplify`, `chat`; optional `target_language: str`; payload accepts `selected_text`, `page_content`, `content_type`, `user_prompt`, `bypass_protection`).
  - `app/services/ai_service.py`: Orchestrate user key decryption, conversation history injection, prompt construction with XML fencing (`<untrusted_web_context>`, `<user_selected_text>`), and async chunk generation. Decouple DB session into 3 phases: (1) Pre-stream read & key load, (2) Streaming loop with zero DB connections held, and (3) Post-stream brief atomic write.
  - `app/routers/ai.py`: Mount `POST /api/v1/ai/stream` using FastAPI's `StreamingResponse(media_type="text/event-stream")`. Check and enforce max 2 concurrent active SSE streams via Redis `active_streams:{user_id}` (`429 STREAM_CONCURRENCY_EXCEEDED`).
  - Implement client disconnect detection (`asyncio.CancelledError`) to abort upstream streams gracefully (`ISSUE-001`).
  - Enforce rule against silent automated AI retries (`ADR-009`).
- **Acceptance Criteria**:
  - Returns `text/event-stream` with standard events `start`, `token`, `citation`, `done`, and `error`.
  - Database connection is freed before entering the token generator loop, preventing connection pool starvation across long-lived SSE streams (`ADR-014`).
  - If user has no active key for the provider, returns `400 NO_ACTIVE_API_KEY` before starting stream.
  - If user already has 2 active streams, rejects 3rd request with `429 STREAM_CONCURRENCY_EXCEEDED`.
  - If upstream provider fails or runs out of quota, streams `event: error` and aborts stream without `event: done`.
  - Supports `content_type: "pdf_text"` with client-extracted plain text (max 100KB); rejects raw binary files.
- **Verification / Screenshot**:
  - Command: `curl -N -X POST http://localhost:8000/api/v1/ai/stream -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"task": "explain", "selected_text": "Photosynthesis"}'`
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
  - Test: `pytest tests/integration/test_proactive_api.py -v`
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
  - Test: `pytest tests/integration/test_quiz_api.py -v`
  - Screenshot: Swagger UI execution of `/api/v1/quiz/generate` showing generated quiz questions.

---

## Phase 7: Reading Data & Community Feedback (Features I & E)

### [BE-13] Tab-Isolated Conversations & Message History
- **Feature Reference**: Feature D (`FR-CNT-05~07`), Feature I (`FR-HIS-01~10`), `ADR-012`
- **Description**: Manage reading conversation threads, guaranteeing strict tab isolation via `reading_session_id`, chronological message retrieval, source grounding flags, and soft deletion with tombstone persistence.
- **Plan & Codebase**:
  - `app/schemas/conversation.py`: `ConversationResponse`, `MessageResponse` (with `is_grounded`, `uncertainty_flag`).
  - `app/services/conversation_service.py`: Create sessions, bind `reading_session_id`, append messages (in an atomic transaction that bumps `conversations.updated_at = NOW()` and `conversations.version = version + 1`), list conversations with search, and soft delete conversations (`is_deleted = TRUE`).
  - `app/routers/conversations.py`: `GET /conversations`, `GET /conversations/{id}/messages` (returns 404 if conversation is soft-deleted), `DELETE /conversations/{id}`.
- **Acceptance Criteria**:
  - Conversations from different browser tabs remain isolated using client-provided `reading_session_id`; mismatched un-bound requests reject with `400 TAB_CONTEXT_MISMATCH` (`FR-CNT-05`).
  - Appending a message atomically increments conversation `version` and updates `updated_at`, ensuring sync detection and proper sorting.
  - Historical messages include `is_grounded` and `uncertainty_flag` metadata.
  - `DELETE /conversations/{id}` performs soft delete (`is_deleted = TRUE`), generating a sync tombstone retained for 30 days. Child messages are hidden from GET queries.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_conversations_api.py -v`
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
  - `DELETE /api/v1/reading/highlights/{id}` soft-deletes a highlight (`is_deleted = TRUE`, `version = version + 1`, `updated_at = NOW()`), returns `204 No Content`, and preserves a sync tombstone for cross-device synchronization (`FR-HIS-06`).
  - `DELETE /api/v1/reading/history` clears browsing logs and atomically sets `conversations.page_url = NULL, conversations.page_title = NULL` to eliminate past browsing ghost footprints under GDPR (`FR-HIS-05`, `FR-HIS-07`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_reading_history_api.py -v`
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
  - Test: `pytest tests/integration/test_feedback_api.py -v`
  - Screenshot: Swagger UI response for `POST /api/v1/ai/feedback` returning `201 Created`.

---

## Phase 8: Multi-Device Sync & Concurrency (Feature J)

### [BE-16] Multi-Device Incremental Synchronization & Conflict Resolver
- **Feature Reference**: Feature J (`FR-SYN-01~08`), `ADR-007`, `ADR-013`
- **Description**: Implement incremental pull and push endpoints for multi-device data synchronization using optimistic locking to prevent silent data overwrites. Uses a Composite Cursor `(updated_at, id)` to prevent skipped records.
- **Plan & Codebase**:
  - `app/schemas/sync.py`: `SyncPullRequest` (with Base64 composite cursor `{"t": "timestamp", "id": "uuid"}`), `SyncPullResponse`, `SyncPushRequest`, `SyncConflictResponse`.
  - `app/services/sync_service.py`: Query mutable entities (`conversations`, `highlights`, `user_settings`) using `(updated_at, id)` composite cursor. Excludes `messages` (loaded on-demand). Compare entity `version` and `updated_at`.
  - `app/cli/purge_tombstones.py`: CLI maintenance utility (`python -m app.cli.purge_tombstones --days 30`) to permanently delete tombstones older than 30 days (PostgreSQL `ON DELETE CASCADE` purges child messages and feedback).
  - `app/routers/sync.py`: Mount `POST /api/v1/sync/pull` and `POST /api/v1/sync/push`.
- **Acceptance Criteria**:
  - `POST /sync/pull` returns modified records paginated by composite cursor `(updated_at, id)` and `limit` (max 100), along with `next_cursor` and `has_more`.
  - `POST /sync/push` applies mutations atomically via conditional SQL update (`WHERE id = :id AND version = :base_version RETURNING id`), strictly preventing multi-threaded race condition silent overwrites (`FR-SYN-05`).
  - In a conflict situation (stale version submitted), server returns `409 SYNC_CONFLICT` with both versions, strictly preventing silent data loss (`FR-SYN-05`).
  - In-flight unsent drafts are excluded from synchronization (`FR-SYN-07`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_sync_engine.py -v`
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
  - Command: `pytest -v --cov=app --cov-report=term-missing`
  - Screenshot: Terminal output showing 100% passed test suite and code coverage summary table.

---

## Phase 10: Admin Management, Telemetry & Rate Limiting (Platform Ops)

### [BE-18] Admin Portal API, Telemetry Engine & Redis Rate Limiter
- **Feature Reference**: Web Management Portal, Feature L (`FR-OPS-01~05`)
- **Description**: Implement platform telemetry aggregation, user management (suspend/ban accounts), feedback browsing, and Redis-backed IP/User rate limiting (`slowapi`).
- **Plan & Codebase**:
  - `app/core/limiter.py`: Configure Redis-backed `slowapi.Limiter` to protect AI endpoints from burst abuse (keys by `user_id` for authenticated routes; uses `X-Forwarded-For` with proxy headers for public routes; falls back to in-memory if Redis down).
  - `app/cli/create_admin.py`: CLI command (`python -m app.cli.create_admin --email ... --password ...`) to bootstrap the initial superuser account.
  - `app/schemas/admin.py`: `TelemetryResponse`, `AdminUserListResponse`, `UserStatusUpdateRequest`, `AdminFeedbackResponse`.
  - `app/services/admin_service.py`: Aggregate request volume, upstream model breakdown (without reading user prompt text), update account statuses, list feedback logs.
  - `app/routers/admin.py`: Mount `GET /api/v1/admin/telemetry`, `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{id}/status`, `GET /api/v1/admin/feedback` protected by `require_admin` dependency.
- **Acceptance Criteria**:
  - All `/api/v1/admin/*` endpoints strictly reject non-admin users with `403 FORBIDDEN_RESOURCE`.
  - Telemetry numbers are aggregated purely from counters and logs with **zero plaintext user reading materials exposed** (strict privacy isolation guarantee).
  - Admin feedback table applies heuristic PII redaction to the `comment` field before presentation.
  - Rejects attempts by an administrator to suspend, ban, or modify their own status (`400 CANNOT_MODIFY_SELF_STATUS`).
  - Banning/suspending a user updates PostgreSQL `users.status`, revokes all refresh tokens, and immediately sets `revoked_users:{user_id}` in Redis (TTL=3600s). Re-activating deletes the Redis key.
  - Excessive requests hit rate limits with standard `429 Too Many Requests` headers; SSE endpoint limits active concurrency to max 2 streams.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_admin_portal.py -v`
  - Screenshot: Swagger/Postman output showing `GET /api/v1/admin/telemetry` returning telemetry JSON and `PATCH /api/v1/admin/users/{id}/status` successfully banning an account.
