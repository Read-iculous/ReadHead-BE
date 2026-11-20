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
```

---

## Phase 1: Foundation & Database

### [BE-01] Project Scaffolding, Core Config & Health Endpoint
- **Feature Reference**: Feature L (`FR-OPS-01~05`), `NFR-MNT-01`
- **Description**: Initialize the project directory layout, dependencies, environment settings via Pydantic Settings, database session lifecycle, error handlers, and a public `/api/v1/health` endpoint.
- **Plan & Codebase**:
  - `requirements.txt` & `requirements-dev.txt`: Pin FastAPI, Uvicorn, SQLAlchemy, asyncpg, Pydantic, etc.
  - `app/core/config.py`: Implement `Settings` class loading `.env` parameters (`DATABASE_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEY`, `CORS_ORIGINS`).
  - `app/core/database.py`: Configure asynchronous engine `create_async_engine`, sessionmaker `AsyncSessionLocal`, and `get_db` dependency.
  - `app/core/exceptions.py`: Define base `AppException` and exception handlers for standard JSON envelopes.
  - `app/routers/health.py`: Create `GET /api/v1/health` returning system status and DB ping.
  - `app/main.py`: Assemble FastAPI instance, CORS middleware, router mounting, and lifespan management.
- **Acceptance Criteria**:
  - Server starts cleanly via `uvicorn app.main:app --port 8000`.
  - `GET /api/v1/health` returns `200 OK` with JSON `{"status": "healthy", "database": "connected"}`.
  - CORS middleware accepts origins configured in `CORS_ORIGINS`.
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
  - Screenshot: PostgreSQL GUI (pgAdmin / DBeaver / terminal `\dt`) showing all 10 tables created with correct foreign key constraints.

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
  - `app/services/auth_service.py`: Business logic for credential checking, duplicate email validation, and token rotation.
  - `app/routers/auth.py`: Endpoints `POST /register`, `POST /login`, `POST /refresh`, `POST /logout`.
- **Acceptance Criteria**:
  - `POST /register` with valid data returns `201 Created` and initial tokens.
  - Duplicate registration returns `409 EMAIL_ALREADY_EXISTS`.
  - Invalid login returns `401 INVALID_CREDENTIALS`.
  - `POST /refresh` with valid refresh token issues a new access token; revoked token returns `401 REFRESH_TOKEN_REVOKED`.
  - `POST /logout` marks the refresh token as revoked.
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_auth_api.py -v`
  - Screenshot: Postman or Swagger UI showing `POST /api/v1/auth/login` returning tokens and subsequent authenticated call to `/api/v1/users/me` with Bearer header.

---

### [BE-04] OAuth2 Integration (Google & GitHub)
- **Feature Reference**: Feature A (`FR-ACC-01`), `.docs/technical/auth-flow.md`
- **Description**: Implement third-party OAuth2 authentication endpoints for Google and GitHub, linking external identities to ReadHead user accounts.
- **Plan & Codebase**:
  - `app/schemas/auth.py`: `GoogleAuthRequest` (id_token/code), `GitHubAuthRequest` (code).
  - `app/services/auth_service.py`: Add `authenticate_google()` and `authenticate_github()` using `httpx.AsyncClient` to verify provider tokens and fetch profiles.
  - Link or create user in `oauth_accounts` table; generate standard ReadHead JWT pair.
  - `app/routers/auth.py`: Mount `POST /api/v1/auth/oauth/google` and `POST /api/v1/auth/oauth/github`.
- **Acceptance Criteria**:
  - Valid OAuth payload authenticates existing user or creates a new user profile with `is_verified: true`.
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
- **Description**: Provide secure storage for user-provided LLM API keys (OpenAI, Gemini, Claude). Keys are encrypted at rest with AES-256-GCM, masked in responses, validated via upstream ping check before storage, and isolated per provider.
- **Plan & Codebase**:
  - `app/core/security.py`: Add `encrypt_secret()` and `decrypt_secret()` using `ENCRYPTION_MASTER_KEY`.
  - `app/schemas/api_key.py`: `ApiKeyCreateRequest`, `ApiKeyResponse` (with masked `key_hint`), `KeyValidationResponse`.
  - `app/services/api_key_service.py`: Add methods to store, retrieve, delete, and test keys. Enforce max 1 active key per provider.
  - `app/routers/api_keys.py`: Endpoints `GET /api/keys`, `POST /api/keys`, `DELETE /api/keys/{provider}`, `POST /api/keys/{provider}/validate`.
- **Acceptance Criteria**:
  - Plaintext key is encrypted before writing to PostgreSQL; database inspect shows ciphertext.
  - `GET /api-keys` returns only masked previews (`sk-...4aF9`), never the decrypted key.
  - `POST /api-keys/{provider}/validate` performs a lightweight ping to the external provider:
    - If valid: returns `200 OK` with `valid: true`.
    - If invalid: returns `400 KEY_VALIDATION_FAILED` and rejects activation.
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
  - `app/core/ai/grounding.py`: Prompt engineering templates enforcing source-grounding priority, uncertainty declarations, and citation markers (`BR-12~14`).
- **Acceptance Criteria**:
  - All three adapters implement the exact same interface and yield standardized chunk strings.
  - Unit tests with mock responses verify that each adapter properly handles rate limits, token timeouts, and authentication errors.
  - Grounding prompts instruct models to explicitly declare when answers rely on external training data vs current page text.
- **Verification / Screenshot**:
  - Test: `pytest tests/unit/test_ai_adapters.py -v`
  - Output: Test log showing mocked streaming chunks successfully yielded from all three adapters.

---

### [BE-09] Real-Time SSE AI Streaming Endpoint
- **Feature Reference**: Feature E (`FR-AI-01~12`), `ADR-002`, `ADR-009`
- **Description**: Implement the central `/api/v1/ai/stream` Server-Sent Events endpoint handling Explain, Summarize, Translate, Simplify (Accessibility), and Multi-turn Chat.
- **Plan & Codebase**:
  - `app/schemas/ai.py`: `AiStreamRequest` (with task enum: `explain`, `summarize`, `translate`, `simplify`, `chat`, `quiz`).
  - `app/services/ai_service.py`: Orchestrate user key decryption, conversation history injection, prompt construction, and async chunk generation.
  - `app/routers/ai.py`: Mount `POST /api/v1/ai/stream` using FastAPI's `StreamingResponse(media_type="text/event-stream")`.
  - Implement client disconnect detection (`asyncio.CancelledError`) to abort upstream streams gracefully (`ISSUE-001`).
  - Enforce rule against silent automated AI retries (`ADR-009`).
- **Acceptance Criteria**:
  - Returns `text/event-stream` with events `start`, `delta`, `metadata` (grounding info), and `done`.
  - If user has no active key for the provider, returns `400 NO_ACTIVE_API_KEY` before starting stream.
  - If upstream provider fails or runs out of quota, streams an error event and saves message draft locally without crashes.
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
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_quiz_api.py -v`
  - Screenshot: Swagger UI execution of `/api/v1/quiz/generate` showing generated quiz questions.

---

## Phase 7: Reading Data & Community Feedback (Features I & E)

### [BE-13] Tab-Isolated Conversations & Message History
- **Feature Reference**: Feature D (`FR-CNT-05~07`), Feature I (`FR-HIS-01~10`)
- **Description**: Manage reading conversation threads, guaranteeing strict tab isolation, chronological message retrieval, source grounding flags, and single-session deletion.
- **Plan & Codebase**:
  - `app/schemas/conversation.py`: `ConversationResponse`, `MessageResponse` (with `is_grounded`, `uncertainty_flag`).
  - `app/services/conversation_service.py`: Create sessions, append messages, list conversations with search, and delete specific conversations.
  - `app/routers/conversations.py`: `GET /conversations`, `GET /conversations/{id}/messages`, `DELETE /conversations/{id}`.
- **Acceptance Criteria**:
  - Conversations from different browser tabs remain isolated; messages cannot be appended across mismatched sessions (`FR-CNT-05`).
  - Historical messages include `is_grounded` and `uncertainty_flag` metadata.
  - `DELETE /conversations/{id}` deletes the session and cascades to messages (`FR-HIS-04`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_conversations_api.py -v`
  - Screenshot: Swagger UI response for `/api/v1/conversations/{id}/messages` showing message history with grounding metadata.

---

### [BE-14] Reading History & Web Highlights Storage
- **Feature Reference**: Feature I (`FR-HIS-01~06`, `BR-18~21`)
- **Description**: Store visited reading pages, dwell time, and user-saved text highlights with color tags and notes. Support bulk history clearance without deleting account credentials.
- **Plan & Codebase**:
  - `app/schemas/reading.py`: `ReadingHistoryCreate`, `ReadingHistoryResponse`, `HighlightCreate`, `HighlightResponse`.
  - `app/services/reading_service.py`: Record history (bypassed if privacy mode or blacklisted domain), save highlights, clear history.
  - `app/routers/reading.py`: `GET/POST /reading/history`, `DELETE /reading/history`, `GET/POST /reading/highlights`.
- **Acceptance Criteria**:
  - If `privacy_mode_enabled: true` or URL is blacklisted, `POST /reading/history` returns `200 OK` with null data without saving to DB.
  - Highlights are retrievable by `page_url` filter.
  - `DELETE /reading/history` clears browsing logs while preserving account credentials and API keys (`FR-HIS-05`, `FR-HIS-07`).
- **Verification / Screenshot**:
  - Test: `pytest tests/integration/test_reading_history_api.py -v`
  - Screenshot: Response of `DELETE /api/v1/reading/history` returning `204 No Content` and verifying database rows wiped.

---

### [BE-15] User Feedback & Accuracy Reporting
- **Feature Reference**: Feature E (`BR-15`, `BG-08`)
- **Description**: Allow users to rate AI responses (helpful / unhelpful) and report inaccuracies or hallucinations to track AI answer quality.
- **Plan & Codebase**:
  - `app/schemas/feedback.py`: `AiFeedbackCreateRequest` (`message_id`, `rating`, `report_reason`, `comment`).
  - `app/services/feedback_service.py`: Record feedback linked to user and message.
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
- **Feature Reference**: Feature J (`FR-SYN-01~08`), `ADR-007`
- **Description**: Implement incremental pull and push endpoints for multi-device data synchronization using optimistic locking to prevent silent data overwrites.
- **Plan & Codebase**:
  - `app/schemas/sync.py`: `SyncPullRequest`, `SyncPullResponse`, `SyncPushRequest`, `SyncConflictResponse`.
  - `app/services/sync_service.py`: Compare entity `version` and `updated_at`. If incoming mutation has a base version lower than current server version, raise a conflict.
  - `app/routers/sync.py`: Mount `POST /api/v1/sync/pull` and `POST /api/v1/sync/push`.
- **Acceptance Criteria**:
  - `POST /sync/pull` returns only records modified after `last_synced_at`.
  - `POST /sync/push` applies mutations atomically and increments entity version numbers.
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
