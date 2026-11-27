# API Endpoints Specification

Base URL: `/api/v1`

Text destined for PostgreSQL TEXT/VARCHAR/JSONB, including URL/search query parameters, must be valid UTF-8 Unicode without NUL (`U+0000`). Invalid request text returns `422 VALIDATION_ERROR` with the field location before persistence; it is rejected rather than silently stripped. Invalid text inside sync mutations returns `400 INVALID_SYNC_MUTATION` and rolls back the entire batch. Invalid provider-generated persistent content is an upstream error (`UPSTREAM_AI_ERROR`), not a client validation or database error.

Unsupported provider strings (body `provider`, settings `default_provider`, and provider route parameters) return `400 UNSUPPORTED_PROVIDER`. Missing required fields, wrong types and unrelated enum validation remain `422 VALIDATION_ERROR`; malformed JSON, including invalid byte encoding, remains `400 INVALID_JSON`.

Backend routes are implemented in `app/routers/`; generated `/openapi.json` describes the current Pydantic request/response schemas. Verification status and client-only responsibilities: `.docs/development/implementation-status.md`.

### CORS and rate-limit responses

- Origins allowed by `CORS_ORIGINS` receive CORS headers on handled API errors, including middleware-generated `429 RATE_LIMIT_EXCEEDED` responses. CORS wraps the operational/rate-limit middleware.
- `Retry-After` and `X-Request-ID` are exposed to browser clients. Origins outside the allowlist receive no `Access-Control-Allow-Origin`; preflight requests bypass rate limiting.
- CORS and correlation also enclose Starlette's server-error handler. Unexpected `500 INTERNAL_SERVER_ERROR` replies, including faults inside operational middleware, retain one generated `X-Request-ID` and the allowlisted origin's CORS headers. The wrapper order is CORS → correlation → server-error handler → operational middleware → FastAPI exception/router stack. Error handlers log with the same request ID; the FastAPI application still exposes its normal routes/OpenAPI/dependency overrides.

### Response Envelope Conventions
- **Standard Success**: `{"data": {...}, "message": "Optional message"}`
- **List / Paginated**: `{"data": {"items": [...], "total": 100, "page": 1, "page_size": 20, "total_pages": 5}}`
- **Error Response**: `{"detail": "Human-readable error", "code": "ERROR_CODE", "field": null}`
- Swagger documents validation errors using the same `ApiErrorResponse` envelope. The default FastAPI `HTTPValidationError` detail array is not the runtime response format.
- **Envelope Exceptions**:
  1. `204 No Content`: Empty response body (Logout, Deletions).
  2. `GET /api/v1/health`: Raw JSON object (unwrapped) for monitoring compatibility (Kubernetes, Prometheus).
  3. `POST /api/v1/ai/stream`: Server-Sent Events stream (`text/event-stream`).

---

## 1. System Health & Diagnostics (`/api/v1/health` — Feature L)

### 1.1 GET `/api/v1/health` (Readiness Probe)
- **Description**: Container readiness probe checking database connectivity and Redis cache status (enforces 1.5s timeout on dependency pings to prevent cascading pod kill loops).
- **Degraded Mode Policy**:
  - PostgreSQL is a mandatory dependency: if down, returns `503 Service Unavailable` (`status: "unhealthy"`).
  - Redis is a soft dependency with graceful degradation: if Redis is down while PostgreSQL is healthy, returns `200 OK` (`status: "degraded"`). This keeps the container eligible for routing while application fallbacks (in-memory rate limiting, direct DB token checks) take over.
- **Auth**: Public
- **Response**: `200 OK` (when healthy or in degraded mode) or `503 Service Unavailable` (when database is down)
  - *Healthy Example (200 OK)*:
    ```json
    {
      "status": "healthy",
      "environment": "development",
      "version": "0.1.0",
      "uptime_seconds": 3600,
      "checks": {
        "database": { "status": "healthy", "latency_ms": 1.2 },
        "redis": { "status": "healthy", "latency_ms": 0.5 }
      },
      "timestamp": "2026-11-21T00:00:00Z"
    }
    ```
  - *Degraded Mode Example (200 OK)*:
    ```json
    {
      "status": "degraded",
      "environment": "development",
      "version": "0.1.0",
      "uptime_seconds": 3600,
      "checks": {
        "database": { "status": "healthy", "latency_ms": 1.5 },
        "redis": { "status": "unhealthy", "error": "Connection refused" }
      },
      "timestamp": "2026-11-21T00:00:00Z"
    }
    ```
- **Database Failure Example (503 Service Unavailable)**:
  ```json
  {
    "status": "unhealthy",
    "environment": "development",
    "version": "0.1.0",
    "checks": {
      "database": { "status": "unhealthy", "error": "Connection refused" },
      "redis": { "status": "healthy", "latency_ms": 0.5 }
    },
    "timestamp": "2026-11-21T00:00:00Z"
  }
  ```

### 1.2 GET `/api/v1/health/live` (Liveness Probe)
- **Description**: Lightweight container liveness probe verifying the FastAPI server process is responsive without touching DB or Redis.
- **Auth**: Public
- **Response**: `200 OK` `{"status": "alive"}`

---

## 2. Authentication & Session (`/api/v1/auth` — Feature A)

### 2.1 POST `/api/v1/auth/register`
- **Description**: Register a new user via email and password.
- Registration/login normalize email using `strip().casefold()` and enforce the 255-character column bound on the normalized value as well as the input. OAuth email validation applies the same bound; malformed upstream identity data returns `401 TOKEN_INVALID` before account lookup/writes.
- **Auth**: Public
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "John Doe"
  }
  ```
- **Response**: `201 Created`
  ```json
  {
    "data": {
      "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
      "email": "user@example.com",
      "full_name": "John Doe",
      "role": "user",
      "status": "active",
      "created_at": "2026-11-21T00:00:00Z"
    }
  }
  ```

### 2.2 POST `/api/v1/auth/login`
- **Description**: Authenticate with email and password.
- **Auth**: Public
- **Request Body**: `{"email": "user@example.com", "password": "SecurePassword123!"}`
- **Password boundary**: Login accepts 1–72 UTF-8 bytes, checked before bcrypt. Registration requires 8–72 UTF-8 bytes. A multi-byte password plus any suffix beyond 72 bytes returns `422 VALIDATION_ERROR`; it must not authenticate as a truncated prefix.
- Registration, login and password confirmation for account deletion reject NUL (`U+0000`) before hashing/verification, using one shared bcrypt-input validator. Unsupported password input returns `422 VALIDATION_ERROR` with `field="password"`, never a bcrypt exception/server error.
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 900
    }
  }
  ```

### 2.3 POST `/api/v1/auth/oauth/google`
- Provider responses are validated before account lookup/writes: bounded string subject/email, explicit verified flag, numeric expiry, matching audience and trusted issuer. Malformed identity payloads return `401 TOKEN_INVALID`, never a database/attribute error.
- **Description**: Login/Register via Google Identity ID Token. Enforces `email_verified == true`. Auto-links with existing email if previously registered via password. Rejects unverified email with `403 EMAIL_NOT_VERIFIED`.
- **Auth**: Public
- **Request Body**: `{"id_token": "google_jwt_identity_token"}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 900
    }
  }
  ```

### 2.4 POST `/api/v1/auth/oauth/github`
- Code exchange must return a non-empty token; profile ID and verified/primary email records are validated before linking. A valid email list without a verified primary email returns `400 OAUTH_EMAIL_MISSING`; malformed provider payloads return `401 TOKEN_INVALID`.
- **Description**: Login/Register via GitHub OAuth2 Authorization Code. Queries `GET https://api.github.com/user/emails` to retrieve primary verified email. Returns `400 OAUTH_EMAIL_MISSING` if no verified email exists.
- **Auth**: Public
- **Request Body**: `{"code": "github_auth_code"}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 900
    }
  }
  ```

### 2.5 POST `/api/v1/auth/refresh`
- **Description**: Rotate within the JWT `sid` session. PostgreSQL user/session validity is checked before any cached result. Login/OAuth creates the session; every rotation keeps the same `sid`.
- **Protocol**:
  1. Validate refresh JWT signature, issuer, type and expiry; verify `sub`/`sid` ownership and active DB user/session. Return `401 TOKEN_INVALID`, `401 REFRESH_TOKEN_EXPIRED`, `401 USER_SUSPENDED` or `401 REFRESH_TOKEN_REVOKED` as appropriate (deleted user: `401 UNAUTHORIZED`).
  2. Look up `refresh_grace:{sid}:{old_token_hash}` (30s TTL). Revalidate the session and cached successor under the session row lock before returning it; see auth-flow §2.3.1 for a successor that has also rotated.
  3. On a miss, use Redis lock `lock:refresh:{sid}:{old_token_hash}` (5s owner-checked lease). **Recheck grace cache after acquiring the lock**. Under a PostgreSQL session-row lock, recheck validity and atomically mark the old token `rotated`, insert/link its successor and extend session expiry. A conditional update on the active old token prevents duplicate rotation even if Redis/its lease fails.
  4. Commit, then cache/index the result by session. Release the lock only if its owner still matches. Contenders wait at most 2s (50ms polling); they must revalidate the session before using any winning result.
- **Temporary failures**: Lock timeout or a token rotated within 30s whose grace result is unavailable returns `503 REFRESH_TEMPORARILY_UNAVAILABLE`, `Retry-After: 1`. Preserve sessions/credentials/drafts. The extension may retry refresh at most twice and first consults its shared token store; it never automatically replays an AI request. A permanently lost winning result requires explicit sign-in. A token rotated more than 30s ago returns `401 REFRESH_TOKEN_REVOKED`; missing cache alone never revokes unrelated sessions.
- **Redis outage**: Use the same DB locking/conditional-update guard. If Redis fails after commit, return the winner's generated pair; siblings without its result follow the temporary-failure contract. No token-pair recovery copy is stored in PostgreSQL. Canonical details: `.docs/technical/auth-flow.md` §2.3.
- **Auth**: Public (refresh JWT required in body)
- **Request Body**: `{"refresh_token": "jwt..."}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 900
    }
  }
  ```

### 2.6 POST `/api/v1/auth/logout`
- **Description**: Verify the refresh token belongs to the authenticated access-token `sid`, then atomically revoke that `auth_sessions` row and all active tokens in its rotation chain (`logout` reason). Delete every exact grace mapping indexed by `refresh_grace_keys:{sid}`; mappings keyed by earlier tokens must also become unusable. Publish the session-revocation marker. DB revocation is authoritative if Redis cleanup fails. Other device sessions remain active; see auth-flow §2.4.
- **Auth**: Required
- **Request Body**: `{"refresh_token": "jwt..."}`
- **Response**: `204 No Content`

---

## 3. User & Settings (`/api/v1/users` — Features A, B, G)

### 3.1 GET `/api/v1/users/me`
- **Description**: Get current user profile and linked accounts.
- **Auth**: Required
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
      "email": "user@example.com",
      "full_name": "John Doe",
      "avatar_url": null,
      "role": "user",
      "status": "active",
      "is_verified": false,
      "created_at": "2026-11-21T00:00:00Z"
    }
  }
  ```

### 3.2 DELETE `/api/v1/users/me`
- **Description**: Delete user account and cascade delete all personal data (`FR-HIS-07`).
- Deletion also removes owned Redis private quizzes and their per-user index. Quiz publication revalidates the account/session under the same PostgreSQL user lock used by deletion, preventing in-flight generation from recreating content afterward. Live legacy unindexed quizzes are found using incremental SCAN and deleted only after verifying ownership. Other users' quizzes are preserved.
- If Redis cleanup cannot be confirmed, return `503 SERVICE_DEGRADED` before committing account deletion; do not report 204 while personal cache data may remain. The user may retry deletion.
- **Auth**: Required
- **Request Body**: `{"confirmation": "DELETE_ACCOUNT", "password": "..."}`
- If supplied, password confirmation accepts 1–72 UTF-8 bytes. Overflow is rejected with `422 VALIDATION_ERROR` before bcrypt and before any account deletion; OAuth-only accounts may omit the password.
- **Response**: `204 No Content`

### 3.3 GET `/api/v1/users/me/settings`
- **Description**: Get preferences, accessibility profile, proactive assistance, and privacy settings.
- **Auth**: Required
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "default_provider": "gemini",
      "default_model": "gemini-1.5-flash",
      "target_language": "vi",
      "explanation_level": "standard",
      "accessibility_profile": {
        "dyslexia_font": true,
        "font_size_delta": 2,
        "line_spacing": 1.6,
        "bionic_reading": false,
        "high_contrast": false
      },
      "proactive_assistance_enabled": true,
      "proactive_sensitivity": "medium",
      "data_protection_mode": true,
      "privacy_mode_enabled": false,
      "blacklisted_domains": ["*.bank.com", "internal.corp"],
      "version": 1
    }
  }
  ```

### 3.4 PATCH `/api/v1/users/me/settings`
- **Description**: Update user preferences or accessibility settings. Requires optimistic version lock.
- **Auth**: Required
- **Request Body**: Partial settings object including `"version": 1`.
- Changing `default_provider` without specifying `default_model` selects that provider's configured default in `DEFAULT_MODELS`. An explicit model is preserved; updating the same provider without a model preserves an existing custom model. Sync push settings uses the same rules. This selects a provider/model pairing; actual model availability still depends on the upstream account.
- Domain blacklist matching normalizes hosts and patterns to IDNA and strips the DNS root dot after conversion. Unicode root-dot forms U+3002 / U+FF0E / U+FF61 cannot bypass a blocked hostname; wildcard semantics are preserved.
- **Response**: `200 OK` (Updated settings object with incremented version)

---

## 4. User API Keys (BYOK Vault) (`/api/v1/api-keys` — Feature C)

### 4.1 GET `/api/v1/api-keys`
- **Description**: List user's registered AI providers and masked key previews.
- **Auth**: Required
- **Response**: `200 OK`

### 4.2 POST `/api/v1/api-keys`
- **Description**: Add or update an API key for a provider (UPSERT behavior). Validates key via ping before saving (`FR-KEY-03`). If a key already exists for the provider, it is atomically replaced only if the new key passes validation; if validation fails, the existing key remains intact. Key is encrypted at rest using AES-256-GCM.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "provider": "openai",
    "api_key": "sk-realplaintextkeyhere",
    "set_active": true
  }
  ```
- **Response**: `201 Created` `{"data": {"provider": "openai", "key_hint": "sk-...keyh", "is_active": true}}`

### 4.3 DELETE `/api/v1/api-keys/{provider}`
- **Description**: Remove an API key for a specific provider.
- **Auth**: Required
- **Response**: `204 No Content`

### 4.4 POST `/api/v1/api-keys/{provider}/validate`
- **Description**: Test if the stored key is valid by sending a ping check.
- **Auth**: Required
- **Response**: `200 OK` `{"data": {"valid": true, "message": "Key validated successfully"}}`

---

## 5. AI Reading Assistant & Privacy (`/api/v1/ai` — Features E, G, H)

### 5.1 POST `/api/v1/ai/check-sensitive` (Feature H Pre-flight Check)
- **Description**: Pre-flight inspection for sensitive credentials or PII across 100% of outbound text before sending to AI.
- **Auth**: Required
- **Request Body**: `{"text": "Text snippet to inspect..."}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "is_sensitive": true,
      "detected_types": ["api_key", "email"],
      "redacted_preview": "sk-****... found in text",
      "blocked_by_policy": true
    }
  }
  ```

### 5.2 POST `/api/v1/ai/stream` (SSE Endpoint — Feature E)
- **Description**: Unified Server-Sent Events stream for AI tasks (Explain, Summarize, Translate, Simplify, Chat).
- **Auth**: Required
- **Headers**: `Accept: text/event-stream`
- **Tab Context & Isolation**:
  - If `conversation_id` is supplied, server verifies ownership, active session binding and that the conversation is not soft-deleted. For an existing standard-mode conversation, both stored and requested `reading_session_id` must be non-null and equal; two null values do not constitute a binding. Otherwise return `400 TAB_CONTEXT_MISMATCH` before writing a message or acquiring a stream slot.
  - **Cleared History Exemption**: If `conversations.page_url IS NULL` (e.g. browsing history was anonymized via `DELETE /api/v1/reading/history`), URL matching is skipped, allowing the user to seamlessly resume the chat from their active tab.
  - If `page_url` is present on the conversation, inbound `page_url` must match; otherwise returns `400 TAB_CONTEXT_MISMATCH`.
- **Request Body**:
  ```json
  {
    "task": "explain", // "explain" | "summarize" | "translate" | "simplify" | "chat"
    "target_language": "vi", // Optional: ISO-639-1 code (e.g. "vi", "en", "ja", "fr") for task: "translate"
    "conversation_id": "uuid-optional",
    "reading_session_id": "uuid-optional", // Client tab/reading session UUID; null when initiated from Dashboard
    "tab_id": 101, // Tab isolation guarantee (FR-CNT-05)
    "page_url": "https://example.com/article",
    "page_title": "Example Article Title",
    "selected_text": "Selected snippet to explain...", // Max 10,000 bytes UTF-8
    "page_content": "Extracted clean text content of the article...", // Max 102,400 bytes UTF-8
    "content_type": "html_article", // "html_article" | "pdf_text"
    "user_prompt": "Explain this concept in simple terms", // Max 2,000 bytes UTF-8
    "provider": "gemini",
    "model": "gemini-1.5-flash",
    "bypass_protection": false, // Set true only if user confirmed override
    "ephemeral_history": [ // Optional: Multi-turn chat context exclusively for Privacy Mode (Max 10 messages, max 16KB UTF-8)
      { "role": "user", "content": "Previous question..." },
      { "role": "assistant", "content": "Previous answer..." }
    ]
  }
  ```
- **SSE Stream Output & Strict Execution Order**:
  - Re-read Privacy Mode under the user row lock before admission writes and before every final/partial response write. A request that started private stays ephemeral even if privacy is later disabled. If privacy becomes enabled before admission, skip conversation/user-message creation and rebuild context from private input; if enabled after admission, preserve already committed historical input but skip subsequent assistant/partial writes. Automatic history and post-generation quiz writes also serialize with the settings update through the user lock.
  - *Phase 1 (Pre-Stream Storage)*: In standard mode, the server opens a transient DB transaction, creates the conversation record (if new), and inserts the incoming `user message`. It allocates the ADR-013 sync timestamp and increments the conversation version for the append, then commits and releases the DB connection *before* contacting the upstream LLM. (In Privacy Mode, DB writes are skipped entirely).
    - For an existing conversation, read the latest ten persisted turns only after validating binding and acquiring its exclusive stream lease under the user lock. Apply outbound privacy checks and rebuild the prompt from this fresh history before appending the current user message. A prior stream completing before admission must appear in the next prompt; a still-running prior stream returns `409 CONVERSATION_BUSY`.
  - *Phase 2 (Active Streaming)*:
    ```text
    event: start
    data: {"conversation_id": "uuid", "message_id": "uuid"}

    event: token
    data: {"content": "This ", "index": 0}

    event: token
    data: {"content": "paragraph means...", "index": 1}

    event: citation
    data: {"source_id": "p-14", "text_snippet": "Neural networks process data in layers", "is_grounded": true, "confidence": null}
    ```
  - *Phase 3 (Post-Stream Persistence & Done Event)*:
    1. LLM streaming concludes.
    2. In standard mode, a fresh transient DB session is opened to insert the completed `assistant message` record and update `conversation.version = version + 1`, `conversation.updated_at = :sync_timestamp` allocated through ADR-013.
    3. The database transaction is committed.
    4. **`event: done` is emitted ONLY AFTER database commit succeeds**:
       ```text
       event: done
       data: {"message_id": "uuid", "finish_reason": "stop", "total_tokens": null, "provider": "gemini", "model": "gemini-1.5-flash", "is_grounded": true, "uncertainty_flag": false, "grounding_notes": "Grounding verified against page context p-14"}
       ```
       - `finish_reason` comes from the provider terminal frame: OpenAI `stop` / `length`, Claude `end_turn` or `stop_sequence` → `stop` and `max_tokens` / `model_context_window_exceeded` → `length`, Gemini `STOP` → `stop` and `MAX_TOKENS` → `length`.
       - `length` means incomplete output. Keep delivered text, but save it with `uncertainty_flag=true`, `is_grounded=false`, and `grounding_notes="truncated_by_provider: output token limit reached"`; the done event carries the same flags and `finish_reason="length"`. Private responses remain ephemeral. Clients must show that the result is incomplete rather than treating every done event as a complete answer. Never retry generation automatically.
       - A missing or unsupported terminal reason returns `UPSTREAM_AI_ERROR`, with no done event and no final assistant write. Non-streaming quiz/proactive generation requires a normal `stop`; truncated or unterminated output returns `502 UPSTREAM_AI_ERROR` instead of a successful quiz/hint, even if the received text parses as valid JSON.
    5. *Persistence Failure Handling*: If DB commit fails, the server **never emits `event: done`**; it emits `event: error` with code `PERSISTENCE_FAILED` (`{"code": "PERSISTENCE_FAILED", "detail": "Failed to persist response to conversation history"}`) so the client keeps the text in current UI memory, labels it "Not saved", and offers copying. MVP has no retry-save endpoint and must not automatically repeat the LLM call.
- **Error, Suspension & Disconnect Handling**:
  - If an upstream error occurs, the stream emits `event: error` and closes immediately. **No `done` event is sent after `error`**.
  - **In-Flight Cancellation**: Async generator inspects Redis key `revoked_users:{user_id}` on each token iteration. If user is banned/deleted mid-stream, stream terminates with `event: error` (`USER_SUSPENDED`); a `revoked_sessions:{sid}` marker from logout terminates that session stream with `UNAUTHORIZED`. Checks run between tokens in normal Redis operation.
    - Suspension/ban also marks every revoked auth session. Reactivation clears only the user marker, preserving the per-session markers so old streams cannot resume. Check revocation again after the upstream ends, before emitting citations/persisting/done. A new login uses a new session and is unaffected by old session markers.
  - **Redis Downtime mid-stream**: If Redis becomes unreachable during streaming, the generator logs a warning, skips in-flight cancellation checks, and delivers the stream to completion.
  - **Client Disconnect**:
    - *Standard Mode*: Partial tokens are saved to `messages` with `uncertainty_flag = true` and `grounding_notes = 'interrupted_by_client'`.
    - *Privacy Mode*: Ephemeral in-session chat only (RAM / `sessionStorage`). Zero rows are written to database `messages` even upon disconnect.
    - *Upstream Socket Management*: Upstream stream and HTTP-client exits run in bounded AnyIO shielded cleanup (10 seconds per release) so an already-cancelled ASGI scope cannot interrupt socket closure. Generation itself remains cancellable. The SSE service closes the upstream before any best-effort partial write and shields slot release; private requests never persist partial text. Cleanup timeouts emit a sanitized operational warning.
    - *Send-Side Disconnect*: A managed response owns finalization of the body generator and admission lease. Its `finally` closes the generator under shield even when cancellation lands in `send()` on ASGI 2.3 or a send raises `OSError` / `ClientDisconnect` on ASGI 2.4. Generator closure triggers the partial-save path for buffered, uncommitted standard-mode tokens. Failure during headers/start releases the lease without writing an empty assistant response; failure during done does not duplicate or overwrite the answer already committed. Cleanup does not depend on Starlette reaching a background task.

### 5.3 POST `/api/v1/ai/proactive-suggest` (Feature G)
- **Description**: Generates an unobtrusive proactive hint when a user slows down or rereads a complex section.
- **Completion validation**: A normal provider `stop` is necessary but not sufficient. Empty or whitespace-only text returns `502 UPSTREAM_AI_ERROR`; it must not become `has_suggestion=true` with an empty hint. Quiz generation shares the same completion boundary. No automatic retry is submitted.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "paragraph_text": "Complex academic or technical paragraph text...",
    "dwell_time_seconds": 25,
    "bypass_protection": false
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "has_suggestion": true,
      "suggestion_type": "key_concept",
      "hint": "This paragraph introduces Quantum Decoherence. Would you like a brief explanation?",
      "suggested_action": "explain"
    }
  }
  ```

### 5.4 POST `/api/v1/ai/feedback` (BR-15 — Evaluation & User Feedback)
- **Description**: Submit a helpful/unhelpful rating or inaccuracy report for an AI response.
- **Privacy Notice**: Feedback is voluntary diagnostic telemetry explicitly shared with system administrators to tune model prompts and report upstream bugs.
- **Auth**: Required (Message must belong to a conversation owned by the authenticated user)
- **Duplicate Handling**: Submitting feedback again for the same `(user_id, message_id)` atomically updates the existing rating.
- **Request Body**:
  ```json
  {
    "message_id": "uuid",
    "rating": "unhelpful", // "helpful" | "unhelpful"
    "report_reason": "inaccurate", // "inaccurate" | "hallucination" | "harmful" | "other"
    "comment": "The translation altered the legal meaning of clause 3"
  }
  ```
- **Response**: `201 Created`

### 5.5 POST `/api/v1/ai/conversations/{id}/bind` (Tab Rebind & Active Isolation)
- **Description**: Explicitly binds an active browser tab's reading session to an existing conversation. Required when reopening a conversation from history or switching active tabs.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "reading_session_id": "uuid",
    "page_url": "https://example.com/article"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "conversation_id": "uuid",
      "reading_session_id": "uuid",
      "is_bound": true
    }
  }
  ```
- **Error Conditions**:
  - `409 CONVERSATION_BUSY`: Conversation is currently in-flight streaming tokens in another tab.
  - `503 SERVICE_DEGRADED`: Redis coordination is unavailable; bind cannot safely check the active stream guard.
  - `400 TAB_CONTEXT_MISMATCH`: If conversation has an existing `page_url` and it does not match inbound `page_url` (except when `page_url` was cleared to `NULL`).

---

## 6. Comprehension Questions & Quizzes (`/api/v1/quiz` — Feature F)

### 6.1 POST `/api/v1/quiz/generate`
- **Description**: Generate 3-5 comprehension quiz questions based on article content (minimum 20 whitespace-delimited source words). Answers and explanations are hidden until submission.
- **Privacy Mode**: When `privacy_mode_enabled: true`, the generated quiz is stored in Redis (`ephemeral_quiz:{quiz_id}` with 30m TTL) instead of the PostgreSQL `quiz_records` table.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "page_text": "Article content to test...",
    "bypass_protection": false
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "quiz_id": "uuid",
      "questions": [
        {
          "question_id": 1,
          "question_text": "What is the primary role of transformer attention?",
          "options": ["Filter noise", "Weight token relationships", "Compress text", "Tokenize words"]
        }
      ]
    }
  }
  ```

### 6.2 POST `/api/v1/quiz/{quiz_id}/submit`
- **Answer types**: Option indices must be JSON integers. Booleans, numeric strings and floating-point values return `422 VALIDATION_ERROR` before an attempt is graded. Generated question IDs and correct-option indices are also validated without numeric coercion.
- **Description**: Submit user's selected answers for grading and receive explanations.
- **Idempotency Guard**: Once submitted and graded, subsequent submissions for the same quiz attempt return `400 QUIZ_ALREADY_SUBMITTED` with message `"Quiz has already been submitted and graded"`.
- **Auth**: Required
- **Request Body**: `{"answers": {"1": 1, "2": 0, "3": 2}}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "score": 3,
      "total": 3,
      "review": [
        {
          "question_id": 1,
          "selected_option": 1,
          "correct_option": 1,
          "is_correct": true,
          "explanation": "Paragraph 2 explicitly states that attention weights token relationships."
        }
      ]
    }
  }
  ```

---

## 7. Conversations, Reading History & Highlights (`/api/v1/conversations` & `/api/v1/reading` — Feature I)

### 7.1 GET `/api/v1/conversations`
- **Description**: List user's reading chat conversations.
- **Auth**: Required
- **Query Params**: `page=1&page_size=20&search=keyword`
- **Response**: `200 OK` `{"data": {"items": [...], "total": 15}}`

### 7.2 GET `/api/v1/conversations/{id}/messages`
- **Description**: Get message history for a specific conversation. Returns `404 CONVERSATION_NOT_FOUND` if parent conversation is soft-deleted.
- **Auth**: Required
- **Query Params**: `page=1&page_size=50&order=asc`
- **Response**: `200 OK` `{"data": {"items": [...], "total": 12, "page": 1, "page_size": 50, "total_pages": 1}}`

### 7.3 DELETE `/api/v1/conversations/{id}`
- **Description**: Soft delete a specific conversation session (`FR-HIS-04`). Sets `conversations.is_deleted = TRUE`, increments `version`, stamps `updated_at` through ADR-013, and generates a sync tombstone (retained for 30 days before permanent purging). Messages are automatically hidden.
- **Auth**: Required
- **Response**: `204 No Content`

### 7.4 POST `/api/v1/reading/history`
- **Description**: Record a read article with dwell time and optional cached summary.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "page_title": "Article Title",
    "reading_time_seconds": 45,
    "cached_summary": "Optional summary..."
  }
  ```
- **Response (Standard)**: `201 Created`
- **Response (Privacy Mode or Blacklisted Domain)**: `200 OK`
  ```json
  {
    "data": null,
    "message": "History logging skipped by privacy policy"
  }
  ```

### 7.5 GET `/api/v1/reading/history`
- **Description**: List browsing and reading history with pagination and search.
- **Auth**: Required
- **Query Params**: `page=1&page_size=20&search=keyword`
- **Response**: `200 OK` `{"data": {"items": [...], "total": 35, "page": 1, "page_size": 20, "total_pages": 2}}`

### 7.6 DELETE `/api/v1/reading/history`
- **Description**: Clear entire browsing/reading history for the account (`FR-HIS-05`). Does not delete account or API keys.
- **GDPR Footprint Anonymization & Sync Integrity**: Lock the user row and allocate `:sync_timestamp` through ADR-013; in addition to deleting all rows in `reading_history`, atomically execute inside the same transaction:
  ```sql
  UPDATE conversations 
  SET page_url = NULL, page_title = NULL, version = version + 1, updated_at = :sync_timestamp
  WHERE user_id = :user_id;
  ```
  - Incrementing `version` and updating `updated_at` guarantees other connected devices synchronize this anonymization immediately.
  - Cleared conversations permit subsequent chat interactions from any tab without triggering `TAB_CONTEXT_MISMATCH`.
- **Auth**: Required
- **Response**: `204 No Content`

### 7.7 POST `/api/v1/reading/highlights`
- **Description**: Save selected text passage and optional personal note.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "highlighted_text": "Important text passage",
    "user_note": "Remember for research paper",
    "color": "yellow"
  }
  ```
- **Response**: `201 Created`
  ```json
  {
    "data": {
      "id": "uuid",
      "page_url": "https://example.com/article",
      "highlighted_text": "Important text passage",
      "user_note": "Remember for research paper",
      "color": "yellow",
      "version": 1,
      "created_at": "2026-11-21T00:00:00Z"
    }
  }
  ```

### 7.8 GET `/api/v1/reading/highlights`
- **Description**: List saved highlights with pagination and optional URL filter.
- **Auth**: Required
- **Query Params**: `page=1&page_size=20&page_url=https://example.com/article`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "items": [
        {
          "id": "uuid",
          "page_url": "https://example.com/article",
          "highlighted_text": "Important text passage",
          "user_note": "Remember for research paper",
          "color": "yellow",
          "created_at": "2026-11-21T00:00:00Z"
        }
      ],
      "total": 1,
      "page": 1,
      "page_size": 20,
      "total_pages": 1
    }
  }
  ```

### 7.9 DELETE `/api/v1/reading/highlights/{id}`
- **Description**: Soft-delete a web highlight (`is_deleted = true`, `version = version + 1`, `updated_at = :sync_timestamp` (ADR-013)), creating a sync tombstone propagated across devices via `sync/pull`.
- **Auth**: Required (Must own the highlight; returns `404 HIGHLIGHT_NOT_FOUND` if not found or unowned)
- **Response**: `204 No Content`

---

## 8. Multi-Device Synchronization (`/api/v1/sync` — Feature J)

### 8.1 POST `/api/v1/sync/pull`
- **Description**: Pull latest user-owned state changes and tombstones for conversations, highlights and settings. Messages are loaded separately. One opaque `cursor` and one `next_cursor` cover all three entity types; there are no per-entity cursor fields.
- **Pagination**: `limit` (1–100, default 100) applies to the combined rows ordered by `(updated_at ASC, entity_type ASC, id ASC)`; type values are `conversation`, `highlight`, `settings`. Group returned rows into the response fields after pagination. `updated_settings` is an object or `null`; absent entity groups are empty arrays/null. Fetch one extra row for `has_more`.
- **Cursor contract**: Base64url JSON, `v: 1`. A `position` cursor contains `kind`, `t`, `entity_type`, UUID `id`, and `anchor`; resume strictly after the tuple. A `checkpoint` contains `kind`, `t`, `anchor` and resumes at `updated_at > t`. Clients treat the whole string as opaque. Malformed/unsupported fields return `400 INVALID_SYNC_CURSOR`; `null` starts a full pull. Position example before encoding:
  ```json
  {
    "v": 1,
    "kind": "position",
    "t": "2026-11-21T00:02:00.000000Z",
    "entity_type": "conversation",
    "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
    "anchor": "2026-11-21T00:00:00.000000Z"
  }
  ```
- **Concurrent updates**: Writers and each short pull transaction lock the authenticated `users` row and use its monotonic `sync_clock` as specified in ADR-013. Never hold this lock across HTTP pages or an LLM stream. With more rows, return a position cursor at the last emitted tuple. On the final/empty page, advance `sync_clock` and return a completed checkpoint at that boundary. Subsequent writes receive later timestamps; a row edited again may be re-delivered with a higher version and is upserted by ID/version.
- **Retention**: Tombstones remain at least 30 days. Cursor `anchor` is the last completed checkpoint time (full-pull start for an initial scan), unchanged across pages. If older than 30 days, return `410 CURSOR_EXPIRED`:
  ```json
  {
    "detail": "Sync checkpoint expired. Rebuild the synced cache while preserving local work.",
    "code": "CURSOR_EXPIRED",
    "field": "cursor",
    "requires_full_sync": true
  }
  ```
- **Full resync**: Preserve credentials, drafts, ephemeral tab state and pending mutations. Fetch all pages with `cursor: null` initially into a user-scoped staging cache; after success atomically replace only the synced cache and store its final checkpoint. On failure preserve the old cache/checkpoint. Queue new local edits separately during rebuilding; compare pending mutation base versions against fresh server state and surface conflicts before submission. Never silently discard pending edits, resurrect deleted rows or replay queued AI requests. Account-switch/logout isolation is a separate purge operation.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "cursor": "eyJ2IjoxLCJraW5kIjoiY2hlY2twb2ludCIsInQiOiIyMDI2LTExLTIxVDAwOjAwOjAwLjAwMDAwMFoiLCJhbmNob3IiOiIyMDI2LTExLTIxVDAwOjAwOjAwLjAwMDAwMFoifQ==",
    "limit": 100
  }
  ```
- **Response**: `200 OK` (example with `limit: 100`; all four rows fit, so the cursor is a completed checkpoint)
  ```json
  {
    "data": {
      "updated_conversations": [
        {
          "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
          "title": "Quantum Computing Notes",
          "page_url": "https://example.com/quantum",
          "page_title": "Intro to Quantum",
          "version": 3,
          "is_deleted": false,
          "updated_at": "2026-11-21T00:02:00.000000Z"
        }
      ],
      "updated_highlights": [
        {
          "id": "a1a417df-1b4e-4b6e-a2b1-8b9f12345678",
          "page_url": "https://example.com/quantum",
          "highlighted_text": "Qubits exist in superposition",
          "color": "yellow",
          "version": 2,
          "is_deleted": false,
          "updated_at": "2026-11-21T00:03:00.000000Z"
        },
        {
          "id": "a2b528ef-2c5f-4c7f-b3c2-9c0f23456789",
          "is_deleted": true,
          "version": 4,
          "updated_at": "2026-11-21T00:04:00.000000Z"
        }
      ],
      "updated_settings": {
        "id": "b3c639fa-3d6a-4d8f-a4d3-ad10456789ab",
        "target_language": "vi",
        "explanation_level": "expert",
        "version": 5,
        "updated_at": "2026-11-21T00:04:30.000000Z"
      },
      "next_cursor": "eyJ2IjoxLCJraW5kIjoiY2hlY2twb2ludCIsInQiOiIyMDI2LTExLTIxVDAwOjA0OjMxLjAwMDAwMFoiLCJhbmNob3IiOiIyMDI2LTExLTIxVDAwOjA0OjMxLjAwMDAwMFoifQ==",
      "total_items_in_page": 4,
      "has_more": false
    }
  }
  ```

### 8.2 POST `/api/v1/sync/push`
- Invalid mutation schemas (including unknown `entity_type`/`action`, invalid UUID/version or non-object payload) and invalid mutable entity fields return `400 INVALID_SYNC_MUTATION`. All mutations in the batch roll back. Invalid outer request envelopes (missing/null/non-list/empty/oversized `mutations`) retain `422 VALIDATION_ERROR`; only errors within an indexed list element become mutation errors. Malformed JSON, including invalid JSON encoding, retains `400 INVALID_JSON`.
- **Description**: Push local batch changes. Returns `409 SYNC_CONFLICT` if optimistic lock versions do not match.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "mutations": [
      {
        "entity_type": "conversation",
        "action": "update",
        "entity_id": "uuid",
        "base_version": 2,
        "payload": { "title": "Updated Title" }
      }
    ]
  }
  ```
- **Response**: `200 OK` or `409 Conflict` (contains server version and conflict details).

---

## 9. Admin Telemetry & Management (`/api/v1/admin` — Role `admin` Only)

### 9.1 GET `/api/v1/admin/telemetry`
- **Description**: Aggregated operational metrics and upstream provider distribution. Zero personal user reading content is visible.
- **Auth**: Required (Role `admin`)
- **Query Params**: `timeframe=24h` (`24h`, `7d`, `30d`)
- **Metrics**: Content-free minute buckets retained for 31 days. Provider split counts dispatched AI operations; error rate includes non-2xx requests and SSE error events. No user text is collected.
- Operational middleware observes early rate-limit replies too: each `429` contributes one request/error and latency sample, retaining CORS, `Retry-After` and request-ID headers.
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "total_requests": 14205,
      "provider_split": {
        "gemini": 0.58,
        "openai": 0.28,
        "claude": 0.14
      },
      "error_rate": 0.012,
      "avg_latency_ms": 680
    }
  }
  ```

### 9.2 GET `/api/v1/admin/users`
- **Description**: List user accounts with role, status, and last activity timestamps.
- **Auth**: Required (Role `admin`)
- **Query Params**: `page=1&page_size=50&status=active`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "items": [
        {
          "id": "uuid",
          "email": "user@example.com",
          "full_name": "Nguyen Van A",
          "role": "user",
          "status": "active",
          "created_at": "2026-11-14T08:00:00Z"
        }
      ],
      "total": 128,
      "page": 1,
      "page_size": 50,
      "total_pages": 3
    }
  }
  ```

### 9.3 PATCH `/api/v1/admin/users/{id}/status`
- **Description**: Update user account status (e.g. suspend or ban). Rejects self-modification with `400 CANNOT_MODIFY_SELF_STATUS` if `id == current_user.id` to prevent accidental platform administrative lockout.
  - **Ban / Suspend**: Sets PostgreSQL `users.status = status` and matching `is_active`, revokes all user auth sessions and active refresh tokens in DB (`security` reason), cleans their session-indexed grace caches, and sets Redis marker `revoked_users:{user_id} = status` (TTL = 3600s) for immediate session invalidation.
  - **Reactivate (`active`)**: Sets `users.status = 'active'`, `is_active = TRUE`, and deletes `revoked_users:{user_id}` from Redis. Existing revoked sessions remain revoked; sign in again.
- **Auth**: Required (Role `admin`)
- **Request Body**: `{"status": "suspended"}` // "active" | "suspended" | "banned"
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "user_id": "uuid",
      "new_status": "suspended"
    }
  }
  ```

### 9.4 GET `/api/v1/admin/feedback`
- **Description**: Retrieve user satisfaction logs and categorized problem reports (BR-15).
- **Privacy Guardrail**: Feedback is voluntary diagnostic telemetry explicitly shared by users. The `comment` string passes through automatic heuristic PII redaction before presentation to protect inadvertent user pastes.
- **Auth**: Required (Role `admin`)
- **Query Params**: `page=1&page_size=50`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "items": [
        {
          "id": "uuid",
          "message_id": "uuid",
          "rating": "unhelpful",
          "report_reason": "inaccurate",
          "comment": "Paragraph translation altered legal context",
          "created_at": "2026-11-20T14:30:00Z"
        }
      ],
      "total": 15,
      "page": 1,
      "page_size": 50,
      "total_pages": 1
    }
  }
  ```
