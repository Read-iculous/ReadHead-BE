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
- **Description**: Register a new user via email and password. Password registration REQUIRES email verification through Resend before login is possible: the account is created with `is_verified = FALSE`, a verification email is dispatched fire-and-forget, and login remains blocked (`403 EMAIL_NOT_VERIFIED`) until the emailed link is confirmed.
- Registration NEVER fails because of mail delivery: if Resend errors (429/5xx/timeout), registration still returns `201 Created` with `verification_email_sent: false` after 3 internal retries with exponential backoff; the user can request a new email via `POST /auth/verify-email/resend`. See auth-flow §2.7.
- Registration/login normalize email using `strip().casefold()` and enforce the 255-character column bound (RFC-style local@domain form) on the normalized value as well as the input. OAuth email validation applies the same bound; malformed upstream identity data returns `401 TOKEN_INVALID` before account lookup/writes.
- **Password rule**: 8–72 UTF-8 bytes; NUL (`U+0000`) rejected; complexity (mixed case, digit, symbol) is RECOMMENDED but not server-enforced in the MVP.
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
      "is_verified": false,
      "verification_email_sent": true,
      "created_at": "2026-11-21T00:00:00Z"
    }
  }
  ```
- **Error codes**: `409 EMAIL_ALREADY_EXISTS` (duplicate), `422 VALIDATION_ERROR` (password out of 8–72 bytes, NUL, or email invalid/over 255 normalized characters).

### 2.2 POST `/api/v1/auth/login`
- **Description**: Authenticate with email and password. Accounts with `is_verified = FALSE` are BLOCKED before session issuance.
- **Email verification gate**: After credential verification succeeds and before creating the `auth_sessions` row, check `users.is_verified`. If `FALSE`, return `403 EMAIL_NOT_VERIFIED` — no session, no tokens, no refresh path:
  ```json
  {
    "detail": "Email address has not been verified. Confirm the link we emailed you or request a new one.",
    "code": "EMAIL_NOT_VERIFIED",
    "field": null,
    "can_resend": true
  }
  ```
  `can_resend: true` signals the client it may call `POST /auth/verify-email/resend`. Uniform `401 INVALID_CREDENTIALS` for wrong passwords keeps this response non-enumerating (the 403 is only returned for an existing account with correct credentials).
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

### 2.7 Email Verification & Password Reset (`/api/v1/auth` — Feature A, BE-19)
All four endpoints share anti-enumeration discipline: responses never reveal whether an email address is registered, already verified or awaiting verification. Rate limits combine the shared `AUTH_REQUESTS_PER_MINUTE` bucket (20/min per client identity) with the per-email resend cap (default 3/hour). Email delivery uses Resend and is fire-and-forget: mail failures never fail the HTTP response (see auth-flow §2.7–2.8).

#### 2.7.1 POST `/api/v1/auth/verify-email/resend`
- **Description**: Re-send the email verification link. **Auth optional**: an authenticated caller is attributed to their own account; an unauthenticated caller supplies the email in the body. Rate limit: 3/hour per email address (plus the shared auth bucket) to prevent email bombing; the counter applies even to unknown addresses so response timing/volume cannot distinguish them.
- **Anti-enumeration**: ALWAYS returns `200 OK` with the same neutral message for unknown, already-verified and recently-resent addresses. No `verification_email_sent` echo beyond the uniform message; no user enumeration.
- **Auth**: Optional (Bearer accepted; email in body when absent)
- **Request Body**: `{"email": "user@example.com"}` (optional when authenticated)
- **Response**: `200 OK`
  ```json
  {"data": null, "message": "If that address can be verified, a new email has been sent."}
  ```
- **Error codes**: `429 RATE_LIMIT_EXCEEDED` (shared bucket or per-email cap exhausted, `Retry-After` header), `422 VALIDATION_ERROR` (malformed email).

#### 2.7.2 POST `/api/v1/auth/verify-email`
- **Description**: Consume a verification token from the emailed link. Idempotent-safe: expired and unknown tokens return distinct 400 codes; an already-verified account receives a neutral success so link double-clicks do not surface errors.
- **Token semantics**: The plaintext token exists only in the email link; the server hashes it (SHA-256) and looks up `email_verification_tokens`. Valid consumption sets `used_at` and `users.is_verified = TRUE` in one transaction.
- **Auth**: Public (token in body IS the credential)
- **Request Body**: `{"token": "url_safe_256_bit_token_from_email"}`
- **Response**: `200 OK`
  ```json
  {"data": {"verified": true}, "message": "Email verified. You can now sign in."}
  ```
  Already-verified (replayed link): `200 OK` `{"data": {"verified": true}, "message": "Email already verified."}`
- **Error codes**: `400 VERIFICATION_TOKEN_EXPIRED` (known hash, past `expires_at`), `400 VERIFICATION_TOKEN_INVALID` (unknown hash or already-consumed token), `422 VALIDATION_ERROR` (missing/malformed token).

#### 2.7.3 POST `/api/v1/auth/forgot-password`
- **Description**: Request a password reset link. Sends a 60-minute reset link via Resend when the address exists. **Anti-enumeration: ALWAYS `200 OK` with an identical neutral message** whether or not the account exists; response time is held stable (token hashing/email dispatch deferred or padded) so timing cannot distinguish registered addresses.
- **Abuse controls**: Shares the per-email cap (3/hour) and the shared auth bucket with §2.7.1 to prevent email bombing; repeated requests for an existing pending token may reuse/replace it without extending attacker-controlled behavior.
- **Auth**: Public
- **Request Body**: `{"email": "user@example.com"}`
- **Response**: `200 OK`
  ```json
  {"data": null, "message": "If an account exists for that address, a reset link has been sent."}
  ```
- **Error codes**: `429 RATE_LIMIT_EXCEEDED`, `422 VALIDATION_ERROR` (malformed email).

#### 2.7.4 POST `/api/v1/auth/reset-password`
- **Description**: Consume a reset token and set a new password. On success: update the bcrypt hash, mark the token used, and **revoke EVERY `auth_sessions` row of the user with reason `security`** (mechanism of auth-flow §2.5) — all devices must sign in again. The response is returned after commit; subsequent requests from old tokens fail the authoritative session check.
- **Password rule**: identical to registration — 8–72 UTF-8 bytes, NUL rejected (`422 VALIDATION_ERROR`), complexity recommended.
- **Auth**: Public (token in body IS the credential)
- **Request Body**: `{"token": "url_safe_256_bit_token_from_email", "new_password": "NewSecurePassword123!"}`
- **Response**: `200 OK`
  ```json
  {"data": null, "message": "Password updated. Please sign in again on all devices."}
  ```
- **Error codes**: `400 RESET_TOKEN_EXPIRED` (known hash, past `expires_at`), `400 RESET_TOKEN_INVALID` (unknown hash or already-consumed token), `422 VALIDATION_ERROR` (password rule violations).

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
      "ui_language": "vi",
      "explanation_level": "standard",
      "personalization_consent": false,
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
- **Language fields**:
  - `ui_language` (extension UI language) accepts only `vi` or `en`; any other value returns `400 UNSUPPORTED_LANGUAGE` (with `field="ui_language"`). It governs interface text only and is intentionally separate from translation.
  - `target_language` (translation output) accepts one of the supported translation languages: `vi`, `en`, `ja`, `zh`, `ko`, `fr`, `de`, `es`; any other value returns `400 UNSUPPORTED_LANGUAGE` (with `field="target_language"`).
- **`personalization_consent` (boolean, ADR-017)**: Explicit opt-in for using `reading_history` and AI interactions for personalization. Semantics:
  - Defaults to `FALSE` and is **independent of `privacy_mode_enabled`** — enabling Privacy Mode does not change consent, and revoking consent does not enable Privacy Mode (and vice versa).
  - Revoking consent sets the flag to `FALSE` only; it does **NOT** delete previously stored data (the client prompts the user about existing data).
  - Takes effect immediately: the flag is re-read under the user row lock before any personalization use (ISSUE-015 pattern, ADR-017).
  - The field is part of the synchronized `settings` entity (§8), so revocation propagates to all devices.
- Domain blacklist matching normalizes hosts and patterns to IDNA and strips the DNS root dot after conversion. Unicode root-dot forms U+3002 / U+FF0E / U+FF61 cannot bypass a blocked hostname; wildcard semantics are preserved.
- **Response**: `200 OK` (Updated settings object with incremented version)

### 3.5 PATCH `/api/v1/users/me` (Profile & Email Change — BE-19)
- **Description**: Update profile fields. `full_name` (display name) is a simple write. Changing `email` is a verified transition:
  - The request MUST include `current_password` for password accounts (OAuth-only accounts omit it); it is verified with bcrypt before any change. Wrong password → `401 INVALID_CREDENTIALS`.
  - The new email is normalized (`strip().casefold()`) and must satisfy the 255-character bound and uniqueness; duplicates → `409 EMAIL_ALREADY_EXISTS`.
  - The change sets `users.is_verified = FALSE` and sends a verification email via Resend to the NEW address (fire-and-forget; the response never fails because of mail errors).
  - **Grace semantics**: the OLD email remains the login identity and keeps receiving login 403s/no 403s per its prior verified state until the new address is verified. After verification of the new address, the new email replaces the login identity. Re-sending uses `POST /auth/verify-email/resend`.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "full_name": "John Doe",
    "email": "new@example.com",
    "current_password": "CurrentPassword123!"
  }
  ```
- **Response**: `200 OK` (Updated profile; includes `email` (pending new one when changing), `is_verified` and `verification_email_sent` when an email change was requested)
- **Error codes**: `401 INVALID_CREDENTIALS`, `409 EMAIL_ALREADY_EXISTS`, `422 VALIDATION_ERROR`.

### 3.6 GET `/api/v1/users/me/usage` (AI Usage Tracking — BE-20)
- **Description**: Personal AI usage aggregates from the `usage_daily` table: per-day counts and token totals grouped by provider and model. Pure aggregate metadata — Privacy Mode **still records usage** (no message IDs, prompts or response content are ever linked), so private-mode generations appear in the totals too.
- **Data caveats**: Numbers may be under-counted for streams cancelled mid-flight before the provider's usage frame; missing usage metadata stores zeros. `usage_daily` is NOT part of `/sync` (§8).
- **Privacy guard**: Admin endpoints expose NO per-user usage in the MVP; this endpoint serves only the authenticated owner.
- **Auth**: Required
- **Query Params**: `period=day` (`day` | `month`), `from=YYYY-MM-DD`, `to=YYYY-MM-DD` (defaults: current day / current month; bounded range e.g. max 366 days → out-of-range returns `422 VALIDATION_ERROR`)
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "period": "day",
      "items": [
        {
          "date": "2026-11-21",
          "provider": "gemini",
          "model": "gemini-1.5-flash",
          "request_count": 12,
          "input_tokens": 8430,
          "output_tokens": 2711
        }
      ]
    }
  }
  ```

### 3.7 GET `/api/v1/users/me/export` (Data Export — GDPR Bundle)
- **Description**: Synchronous JSON bundle of **all** data the platform stores about the authenticated user: profile, settings, reading history, highlights, conversations (each with its messages), quiz records and AI feedback. Serves the user dashboard's "export my data" action (GDPR-style portability); MD/PDF rendering of the export is a **client-side responsibility** — the backend produces JSON only.
- **Delivery**: `200 OK` with `Content-Disposition: attachment; filename="readhead-export-<timestamp>.json"` and the bundle as the body (inside the standard `data` envelope).
- **Synchronous contract**: The MVP builds the bundle synchronously. For very large accounts the response may take seconds; if the serialized bundle exceeds a configured size threshold (default **50 MB**, configurable via env), the backend includes a `"size_warning"` note field in the bundle header advising the client to offer a download prompt rather than inline rendering. No async job/queue is introduced.
- **Privacy Mode**: Ephemeral private-mode data (private conversations/messages, ephemeral quizzes) has no database rows and is therefore naturally absent from the bundle; only persisted data is exported.
- **Rate limit**: General API bucket **plus a dedicated stricter cap of 5 requests/minute** per user to prevent export abuse (exceeding it returns `429 RATE_LIMIT_EXCEEDED` with `Retry-After`).
- **Auth**: Required
- **Response**: `200 OK` (shape — arrays may be empty):
  ```json
  {
    "data": {
      "exported_at": "2026-11-21T00:00:00Z",
      "profile": { "id": "uuid", "email": "user@example.com", "full_name": "John Doe", "created_at": "..." },
      "settings": { "...": "full user_settings object (§3.3)" },
      "reading_history": [ { "page_url": "...", "page_title": "...", "reading_time_seconds": 45, "visited_at": "..." } ],
      "highlights": [ { "id": "uuid", "page_url": "...", "highlighted_text": "...", "user_note": "...", "color": "yellow", "created_at": "..." } ],
      "conversations": [
        {
          "id": "uuid",
          "title": "...",
          "page_url": "...",
          "created_at": "...",
          "messages": [ { "sender_role": "user", "content": "...", "created_at": "..." } ]
        }
      ],
      "quiz_records": [ { "page_url": "...", "total_questions": 5, "score": 4, "is_submitted": true, "created_at": "...", "submitted_at": "..." } ],
      "ai_feedback": [ { "message_id": "uuid", "rating": "helpful", "report_reason": null, "comment": null, "created_at": "..." } ],
      "size_warning": "Bundle exceeds 50 MB; offer a file download instead of inline rendering."
    }
  }
  ```
- **Error codes**: `429 RATE_LIMIT_EXCEEDED` (5/min export cap or general bucket), `503 SERVICE_DEGRADED` not applicable (pure DB read).

### 3.8 GET `/api/v1/users/me/reading-insights?from&to` (Comprehension Insights — Tầng 2)
- **Description**: Rule-based comprehension insight aggregates per `(user, domain)` (Tầng 2), computed **on-the-fly** from `quiz_records` and `messages`⋈`conversations` — no new table, no ML, no sync entity. Dwell/reading time is only a secondary signal. Thresholds and rules are **configuration constants/env values, never hard-coded logic**, so tuning does not require code changes. See ADR-018.
- **Consent gate (ADR-017)**: *Viewing* the insight requires NO consent — it aggregates the user's own data and is returned whenever sufficient data exists. *Using* the insight to modulate AI behavior (e.g. the proactive `insight` field, §5.3) DOES require `personalization_consent`, re-read under the user row lock at the point of use per ADR-017. This endpoint therefore always returns the data; enforcement lives in §5.3.
- **Privacy Mode**: While Privacy Mode is enabled no new signals are written (no history rows, no conversations/messages, no persistent quizzes). Aggregates are computed exclusively from previously stored rows; the response degrades naturally as old data ages out of the range.
- **Reset semantics**: Because everything is computed on-the-fly, deleting the underlying data (`DELETE /reading/history`, bulk/single conversation delete, account deletion) immediately resets the signals — there is no cached aggregate to purge.
- **Auth**: Required
- **Query Params**: `from`, `to` — `YYYY-MM-DD` UTC bounds, required bounded range (max 366 days; out-of-range returns `422 VALIDATION_ERROR`).
- **Rules (configurable thresholds)**:
  - **Quiz trend**: `avg_quiz_score` is the mean of `score / total_questions` over the domain's submitted quizzes in range. Compare the average of the most recent 5 quizzes against the previous 5 (configurable window): lower-and-below-threshold (avg < 0.6 by default) → `"declining"`; higher → `"improving"`; otherwise `"stable"`. A decay of `medium`/`high` difficulty_signal requires BOTH a low recent average AND a decline versus the earlier window.
  - **Assist frequency (`assist_request_rate`)**: user-turn count per domain (from `messages` of `sender_role='user'` joined to `conversations.page_url`) normalized by the domain's visit count. `messages` currently lacks a `task` column, so user-turns are the proxy for assistance requests (ADR-018 limitation).
  - **Difficulty signal**: `none` | `low` | `medium` | `high` derived from the quiz decay rule plus assist-frequency normalization; **dwell/reading time alone never raises the signal** (it only corroborates when another signal already fired — false-positive guard).
  - **`has_sufficient_data`**: `false` when the domain has fewer than 2 submitted quizzes AND fewer than 3 user turns (configurable minima); such items still appear with `sample_size` so the client can render "not enough data yet".
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "items": [
        {
          "domain": "example.com",
          "avg_quiz_score": 0.55,
          "quiz_trend": "declining",
          "assist_request_rate": 1.8,
          "difficulty_signal": "medium",
          "sample_size": 7,
          "has_sufficient_data": true
        }
      ]
    }
  }
  ```
- **Error codes**: `422 VALIDATION_ERROR` (missing/bad dates or range over 366 days). Rate bucket: general API bucket.

---

## 4. User API Keys (BYOK Vault) (`/api/v1/api-keys` — Feature C)

### 4.1 GET `/api/v1/api-keys`
- **Description**: List user's registered AI providers and masked key previews.
- **Auth**: Required
- **Response**: `200 OK`
  ```json
  {
    "data": [
      {
        "provider": "gemini",
        "is_active": true,
        "key_hint": "sk-...4F8a",
        "last_validated_at": "2026-11-21T00:00:00Z"
      }
    ]
  }
  ```

### 4.2 POST `/api/v1/api-keys`
- **Description**: Add or update an API key for a provider (UPSERT behavior). Validates key via ping before saving (`FR-KEY-03`). If a key already exists for the provider, it is atomically replaced only if the new key passes validation; if validation fails, the existing key remains intact. Key is encrypted at rest using AES-256-GCM.
- **Sync note**: This UPSERT is **last-write-wins with NO optimistic-version conflict check** — unlike synchronized Feature J entities, api-key writes never return `409 SYNC_CONFLICT` and `user_api_keys` rows are not part of `/sync` (§8). Concurrent writes from two devices simply resolve to the last committed key (validation-gated).
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
- **Description**: Remove an API key for a specific provider. Side effects on related state:
  - If the removed key row has `is_active = TRUE`, the active flag is cleared along with the row.
  - If the user's `default_provider` (settings) equals the deleted provider, `default_provider` reverts to `NULL`; any stored `default_model` for it is kept but unused until a provider is selected again. The next `/api/v1/ai/stream` without an explicit provider then returns `400 NO_ACTIVE_API_KEY` (no usable provider configured).
- **Auth**: Required
- **Response**: `204 No Content`
- **Error codes**: `404 API_KEY_NOT_FOUND` (no key registered for the provider).

### 4.4 POST `/api/v1/api-keys/{provider}/validate`
- **Description**: Test if the stored key is valid by sending a ping check.
- **Failure discrimination**:
  - The provider responded and rejected the key (auth/quota-class rejection) → `400 KEY_VALIDATION_FAILED`; the existing key's `is_active` is not promoted.
  - The provider could not be reached (network failure, timeout, 5xx) → `502 UPSTREAM_AI_ERROR` with detail `"provider unreachable"` — this is an infrastructure/upstream fault, NOT evidence that the key is bad, and must not deactivate the key.
- **Auth**: Required
- **Response**: `200 OK` `{"data": {"valid": true, "message": "Key validated successfully"}}`

---

## 5. AI Reading Assistant & Privacy (`/api/v1/ai` — Features E, G, H)

### 5.1 POST `/api/v1/ai/check-sensitive` (Feature H Pre-flight Check)
- **Description**: Pre-flight inspection for sensitive credentials or PII across 100% of outbound text before sending to AI.
- **Mixed-content policy for `page_content` (ADR-006 scope note)**: `page_content` carries the full extracted article text and is treated as potentially containing sensitive data mixed with ordinary reading content. When the pre-flight scan detects sensitive content inside `page_content`, the request is **blocked by default** (`400 SENSITIVE_DATA_DETECTED`). Because `page_content` is supplied wholesale by the client — the backend never re-extracts or edits the page, and the client cannot strip individual findings without destroying the reading context the AI needs — the **override via `bypass_protection: true` is the only path to proceed**. The override MUST follow the existing mechanism: the client shows a strong explicit user confirmation first, and the confirmed override is audit-logged (`sensitive_content_override_confirmed`, one log line per request with request ID and masked user ID — ISSUE-041). There is no domain whitelist: the domain blacklist (`DOMAIN_BLOCKED_BY_PRIVACY`) remains the only domain-level control and is not bypassable by `bypass_protection`.
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
- **Auth**: Required — verified once at the HTTP handshake only (Bearer token, user/key/provider validation, admission limits). **Access-token expiry during an active stream does NOT terminate it**: the already-admitted stream runs to completion even after the 15-minute access lifetime passes; only explicit revocation cancels in-flight streams (see In-Flight Cancellation below). Clients refresh tokens for subsequent requests, never for a running stream.
- **Headers**: `Accept: text/event-stream`
- **Language & Translation Behavior**:
  - `target_language` is optional and per-request: when supplied for `task: "translate"` it overrides the user's `target_language` setting for this request only; when omitted, the stored settings value is the fallback. The user's settings value is never modified by a per-request override.
  - Supplied `target_language` values are validated against the same supported set as settings (`vi`, `en`, `ja`, `zh`, `ko`, `fr`, `de`, `es`); an unsupported value returns `400 UNSUPPORTED_LANGUAGE` before any LLM dispatch. There is no `source_language` parameter: the source language is auto-detected from the submitted text by the model.
  - The translate task is prompt-level behavior: the system prompt instructs the model to **translate AND explain the meaning of domain/technical terms in context** (BR-05). The response remains a plain streamed text answer (`event: token`) — no separate terminology payload, schema or endpoint is involved.
- **Tab Context & Isolation**:
  - If `conversation_id` is supplied, server verifies ownership, active session binding and that the conversation is not soft-deleted. For an existing standard-mode conversation, both stored and requested `reading_session_id` must be non-null and equal; two null values do not constitute a binding. Otherwise return `400 TAB_CONTEXT_MISMATCH` before writing a message or acquiring a stream slot.
  - **Cleared History Exemption**: If `conversations.page_url IS NULL` (e.g. browsing history was anonymized via `DELETE /api/v1/reading/history`), URL matching is skipped, allowing the user to seamlessly resume the chat from their active tab.
  - If `page_url` is present on the conversation, inbound `page_url` must match; otherwise returns `400 TAB_CONTEXT_MISMATCH`.
- **Request Body**:
  ```json
  {
    "task": "explain", // "explain" | "summarize" | "translate" | "simplify" | "chat"
    "target_language": "vi", // Optional: one of the supported translation languages ("vi", "en", "ja", "zh", "ko", "fr", "de", "es") for task: "translate"; overrides the user's settings value for this request only
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
       data: {"message_id": "uuid", "finish_reason": "stop", "total_tokens": 4213, "input_tokens": 3120, "output_tokens": 1093, "provider": "gemini", "model": "gemini-1.5-flash", "is_grounded": true, "uncertainty_flag": false, "grounding_notes": "Grounding verified against page context p-14"}
       ```
       - **Usage metadata**: `total_tokens` remains as today; `input_tokens` and `output_tokens` are added. All three are **null when the provider does not return usage metadata** in its terminal frame (OpenAI requires `stream_options.include_usage`, Anthropic reports usage on the `message_delta` frame, Gemini provides `usageMetadata`); nulls are preserved, never fabricated (existing nullable `total_tokens` behavior is unchanged).
       - `finish_reason` comes from the provider terminal frame: OpenAI `stop` / `length`, Claude `end_turn` or `stop_sequence` → `stop` and `max_tokens` / `model_context_window_exceeded` → `length`, Gemini `STOP` → `stop` and `MAX_TOKENS` → `length`.
       - `length` means incomplete output. Keep delivered text, but save it with `uncertainty_flag=true`, `is_grounded=false`, and `grounding_notes="truncated_by_provider: output token limit reached"`; the done event carries the same flags and `finish_reason="length"`. Private responses remain ephemeral. Clients must show that the result is incomplete rather than treating every done event as a complete answer. Never retry generation automatically.
       - A missing or unsupported terminal reason returns `UPSTREAM_AI_ERROR`, with no done event and no final assistant write. Non-streaming quiz/proactive generation requires a normal `stop`; truncated or unterminated output returns `502 UPSTREAM_AI_ERROR` instead of a successful quiz/hint, even if the received text parses as valid JSON.
    5. *Persistence Failure Handling*: If DB commit fails, the server **never emits `event: done`**; it emits `event: error` with code `PERSISTENCE_FAILED` (`{"code": "PERSISTENCE_FAILED", "detail": "Failed to persist response to conversation history"}`) so the client keeps the text in current UI memory, labels it "Not saved", and offers copying. MVP has no retry-save endpoint and must not automatically repeat the LLM call.
- **Error, Suspension & Disconnect Handling**:
  - If an upstream error occurs, the stream emits `event: error` and closes immediately. **No `done` event is sent after `error`**.
  - **Mid-stream provider auth errors**: If the provider rejects the stored user key during streaming (401/403-class upstream response), the stream emits `event: error` with code `403 UPSTREAM_KEY_INVALID` — a distinct code from `UPSTREAM_AI_ERROR` so the client can route the user to key management instead of showing a generic AI failure. The stream closes without `done`; the key is not auto-deleted.
  - **In-Flight Cancellation**: Async generator inspects Redis key `revoked_users:{user_id}` on each token iteration. If user is banned/deleted mid-stream, stream terminates with `event: error` (`USER_SUSPENDED`); a `revoked_sessions:{sid}` marker from logout terminates that session stream with `UNAUTHORIZED`. Checks run between tokens in normal Redis operation. These explicit revocation markers are the ONLY mid-stream cancellation triggers: an access token merely expiring, or a failed revocation check, never cuts a running stream.
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
- **Dedup TTL cache (ISSUE-043 resolution, ADR-017)**: Before dispatching any LLM call, the endpoint consults a Redis TTL cache keyed `(user_id, paragraph_hash)` (SHA-256 of the normalized paragraph text). Behavior:
  - **Cache hit** (same user re-suggests the same paragraph within the TTL) → returns `{"has_suggestion": false}` immediately **without calling the LLM**, regardless of `dwell_time_seconds`.
  - On a cache miss the request proceeds normally and the key is written with a **TTL of 300 seconds (5 minutes)** after a completed generation. Keys are written only for suggestions the provider actually produced (upstream errors write nothing).
  - The cache lives **only in Redis** — it is never persisted to PostgreSQL, is not part of `/sync`, requires no schema migration, and disappears harmlessly on Redis outage (degraded mode simply skips dedup and the endpoint behaves as before).
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
      "suggested_action": "explain",
      "insight": {
        "domain_difficulty": "medium",
        "suggested_action": "quiz"
      }
    }
  }
  ```
- **Insight-driven enrichment (Comprehension Insight, ADR-018 — optional field)**: The response MAY include an optional `insight` object `{domain_difficulty, suggested_action}` when the backend's on-the-fly per-domain aggregate (computed exactly like `GET /users/me/reading-insights`, §3.8) indicates elevated difficulty for the current domain. Rules:
  - **Consent gate**: `insight` is added **ONLY** when `personalization_consent == true`, re-read under the user row lock at request time (ADR-017). Without consent the field is never present — the plain hint still works, since it does not use personal data.
  - **Daily cap**: insight enrichment is capped at **2 per day per domain** (configurable; Redis counter with 24h TTL). When the cap is reached, `insight` is omitted but the ordinary hint still functions per the existing dedup rules.
  - **Dismissal memory**: If the user dismisses this insight-type suggestion, a Redis TTL cache (24h) suppresses further insight enrichment for that (user, domain) — separate from the 5-minute paragraph dedup cache, which continues to govern the plain hint.
  - **Privacy Mode**: no new signals are recorded and the aggregate reads only previously stored rows; without consent or with insufficient data the field is simply absent.

### 5.4 POST `/api/v1/ai/feedback` (BR-15 — Evaluation & User Feedback)
- **Description**: Submit a helpful/unhelpful rating or inaccuracy report for an AI response.
- **Privacy Notice**: Feedback is voluntary diagnostic telemetry explicitly shared with system administrators to tune model prompts and report upstream bugs.
- **Rate limit**: Covered by the **general API bucket** (`API_REQUESTS_PER_MINUTE`, 120/min per identity) — feedback performs no generation, so it is not counted against the AI bucket.
- **Validation**: `rating` must be `helpful` | `unhelpful` and `report_reason` (when supplied) must be `inaccurate` | `hallucination` | `harmful` | `other`; any other value returns `422 VALIDATION_ERROR` with the offending field attributed.
- **Privacy Mode note**: Private-mode messages are ephemeral (never persisted), so a feedback POST referencing an ephemeral message cannot satisfy the `ai_feedback.message_id` FK. The endpoint re-checks persistence state and returns `404 MESSAGE_NOT_FOUND` rather than attempting the write — the client should not offer feedback UI for private-mode responses.
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
- **Idempotency Guard**: Once submitted and graded, subsequent submissions for the same quiz attempt return `400 QUIZ_ALREADY_SUBMITTED` with message `"Quiz has already been submitted and graded"`. **Submitted quizzes cannot be retaken** — there is no reset or re-attempt endpoint; the user generates a new quiz instead.
- **Existence & expiry**: A quiz that does not exist, belongs to another user, was soft-deleted (tombstoned by account cleanup), or was a Privacy-Mode ephemeral quiz whose Redis entry has expired (30-minute TTL) returns `404 QUIZ_NOT_FOUND` — expiry is indistinguishable from absence and no data is reconstructed.
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

### 6.3 GET `/api/v1/quiz` (Quiz History — BE-22)
- **Description**: Paginated quiz history for the authenticated user, built from `quiz_records` (Privacy-Mode quizzes are NOT listed — they are Redis-ephemeral with a 30-minute TTL and leave no persistent rows; the list endpoint simply returns the persistent history). Supports dashboard-style filtering by date range, domain and submission status.
- **Auth**: Required
- **Rate bucket**: Covered by the **general API bucket** (`API_REQUESTS_PER_MINUTE`, 120/min per identity) — NOT the AI/quiz generation bucket (`AI_REQUESTS_PER_MINUTE`), since it performs no generation.
- **Query Params**:
  - `page` (default 1), `page_size` (default 20)
  - `from`, `to` — `YYYY-MM-DD` UTC date bounds on `created_at`, max range 366 days; out-of-range returns `422 VALIDATION_ERROR`
  - `domain` — optional host/URL filter (same IDNA normalization as the domain blacklist)
  - `status` — `submitted` | `unsubmitted` | `all` (default `all`); unsubmitted quizzes are generated-but-never-graded records
- **Response**: `200 OK` (standard list envelope)
  ```json
  {
    "data": {
      "items": [
        {
          "id": "d4a417df-1b4e-4b6e-a2b1-8b9f12345678",
          "page_url": "https://example.com/article",
          "page_title": "Example Article Title",
          "total_questions": 5,
          "score": 4,
          "is_submitted": false,
          "created_at": "2026-11-21T00:00:00Z",
          "submitted_at": null
        }
      ],
      "total": 42,
      "page": 1,
      "page_size": 20,
      "total_pages": 3
    }
  }
  ```
  - `total_questions` is derived from the stored `questions_payload` JSONB (no dedicated column).
  - Unsubmitted quizzes appear with `is_submitted: false`, `score: null`, `submitted_at: null`; a user with no quiz history receives an empty `items` array with `total: 0`, not an error.
- **Error codes**: `422 VALIDATION_ERROR` (bad dates/page params/out-of-range range).

### 6.4 GET `/api/v1/quiz/stats` (Quiz Statistics — BE-22)
- **Description**: Daily aggregate quiz statistics for the dashboard chart. Same persistent-history scope and Privacy-Mode exclusion as §6.3; same **general** rate bucket.
- **Auth**: Required
- **Query Params**: `from`, `to` — `YYYY-MM-DD` UTC, required bounded range (max 366 days; out-of-range returns `422 VALIDATION_ERROR`).
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "days": [
        { "date": "2026-11-20", "attempts": 3, "avg_score": 0.8 },
        { "date": "2026-11-21", "attempts": 5, "avg_score": 0.6 }
      ],
      "overall": { "total_submitted": 8, "avg_score": 0.675 }
    }
  }
  ```
  - Only **submitted** quizzes count as attempts; `avg_score` is the mean of `score / total_questions` per day and overall, rounded to 3 decimals. Days with no attempts may be returned as zero-attempt entries or omitted — clients must handle both.

### 6.5 GET `/api/v1/quiz/{quiz_id}` (Quiz Detail & Review — BE-22)
- **Description**: Retrieve one quiz with its questions, the user's submitted answers (if any) and the per-question review/explanations. For an unsubmitted quiz, answers/explanations remain hidden (same contract as §6.1) and `is_submitted: false` is returned.
- **Auth**: Required (owner only; other users' quizzes return `404 QUIZ_NOT_FOUND`, not `403`)
- **Not found**: `404 QUIZ_NOT_FOUND` when the quiz does not exist, was tombstoned, or was an ephemeral Privacy-Mode quiz whose Redis entry expired (30-minute TTL) — see §6.2.
- **Rate bucket**: General API bucket (§6.3).
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "id": "d4a417df-1b4e-4b6e-a2b1-8b9f12345678",
      "page_url": "https://example.com/article",
      "page_title": "Example Article Title",
      "is_submitted": true,
      "created_at": "2026-11-21T00:00:00Z",
      "submitted_at": "2026-11-21T00:10:00Z",
      "questions": [
        {
          "question_id": 1,
          "question_text": "What is the primary role of transformer attention?",
          "options": ["Filter noise", "Weight token relationships", "Compress text", "Tokenize words"],
          "selected_option": 1,
          "correct_option": 1,
          "is_correct": true,
          "explanation": "Paragraph 2 explicitly states that attention weights token relationships."
        }
      ],
      "score": 4,
      "total": 5
    }
  }
  ```

---

## 7. Conversations, Reading History & Highlights (`/api/v1/conversations` & `/api/v1/reading` — Feature I)

### 7.1 GET `/api/v1/conversations`
- **Description**: List user's reading chat conversations. Soft-deleted rows (tombstones) are **excluded**: the list filters `is_deleted = FALSE`, so tombstoned conversations never appear in the response. Tombstones surface only through `POST /sync/pull` (§8.1).
- **Auth**: Required
- **Query Params**: `page=1&page_size=20&search=keyword`
- **Response**: `200 OK` — each item is a `ConversationSummary`:
  ```json
  {
    "data": {
      "items": [
        {
          "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
          "title": "Quantum Computing Notes",
          "page_url": "https://example.com/quantum",
          "created_at": "2026-11-21T00:00:00Z",
          "updated_at": "2026-11-21T00:02:00Z",
          "message_count": 6
        }
      ],
      "total": 15
    }
  }
  ```
- **`ConversationSummary` shape**: `id`, `title`, `page_url`, `created_at`, `updated_at`, and optional `message_count` (server-derived; may be omitted by lightweight list paths). The sync-only fields `version` and `is_deleted` deliberately do **not** appear in this list shape — `is_deleted` is implied `false` because tombstones are filtered out.

### 7.2 GET `/api/v1/conversations/{id}/messages`
- **Description**: Get message history for a specific conversation. Returns `404 CONVERSATION_NOT_FOUND` if parent conversation is soft-deleted.
- **Auth**: Required
- **Query Params**: `page=1&page_size=50&order=asc`
- **Response**: `200 OK` `{"data": {"items": [...], "total": 12, "page": 1, "page_size": 50, "total_pages": 1}}`

### 7.3 DELETE `/api/v1/conversations/{id}`
- **Description**: Soft delete a specific conversation session (`FR-HIS-04`). Sets `conversations.is_deleted = TRUE`, increments `version`, stamps `updated_at` through ADR-013, and generates a sync tombstone (retained for 30 days before permanent purging). Messages are automatically hidden.
- **Delete-while-streaming**: If the conversation currently holds an active stream lease (tokens are being streamed in any tab), the delete is rejected with `409 CONVERSATION_BUSY`. The client must stop the active stream first (or await its completion) and retry the delete; no tombstone is written by the rejected request.
- **Auth**: Required
- **Response**: `204 No Content`
- **Error codes**: `404 CONVERSATION_NOT_FOUND` (unknown ID, foreign owner or already tombstoned), `409 CONVERSATION_BUSY` (active stream lease).

### 7.3a DELETE `/api/v1/conversations` (Bulk Delete — FR-HIS-05)
- **Description**: Tombstone **all** non-deleted conversations of the authenticated user in one call (FR-HIS-05). Every conversation receives the soft-delete treatment of §7.3: `is_deleted = TRUE`, `version = version + 1`, `updated_at` stamped through ADR-013, one sync tombstone per row (retained 30 days). Tombstones appear in `POST /sync/pull` exactly like per-item deletions, so other devices remove them through the normal sync path. Messages are automatically hidden.
- **Streaming conversations**: A conversation holding an active stream lease is **skipped, not failed** — the bulk operation deletes everything else and reports the skip in the response. The client can stop the stream and re-run the bulk delete (re-running is idempotent: already-tombstoned conversations are not counted again).
- **Scope**: This endpoint touches only `conversations`. It does NOT clear `reading_history`, does not anonymize URLs and does not alter `DELETE /reading/history` (§7.6) semantics.
- **Auth**: Required
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "deleted_count": 12,
      "skipped_streaming": 1
    }
  }
  ```
- `deleted_count` — conversations tombstoned by this call; `skipped_streaming` — conversations left untouched because an active stream lease existed (may be `0`).

### 7.3b PATCH `/api/v1/conversations/{id}` (Rename)
- **Description**: Update a conversation's title. Sets `title`, increments `version`, stamps `updated_at` through ADR-013, and generates a sync `update` event so other devices receive the new title via `POST /sync/pull` (§8.1).
- **Tombstoned conversations**: A soft-deleted conversation returns `404 CONVERSATION_NOT_FOUND` — titles of tombstones are never modified.
- **Auth**: Required (owner only)
- **Request Body**:
  ```json
  {
    "title": "Renamed Conversation Title"
  }
  ```
- **Response**: `200 OK` — updated `ConversationSummary` (§7.1 shape) with the new `title` and `updated_at`.
- **Error codes**: `404 CONVERSATION_NOT_FOUND` (unknown ID, foreign owner or tombstoned), `422 VALIDATION_ERROR` (missing/empty/oversized title beyond `VARCHAR(255)`).

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
- **Per-page limit**: A page may hold at most **200 highlights**. When the count of non-deleted highlights for the same `page_url` already reaches 200, the request returns `422 VALIDATION_ERROR` with `field="page_url"` (the existing count is reported in the error detail). No new error code is introduced. Duplicated highlight text on a page is **allowed** — no dedup is applied.
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

### 7.9a PATCH `/api/v1/reading/highlights/{id}` (Edit Note / Color)
- **Description**: Update a highlight's mutable fields — `user_note` and/or `color`. Increments `version` by 1, stamps `updated_at` through ADR-013, and generates a sync `update` event so other devices pull the edited highlight. `highlighted_text` and `page_url` are immutable. Duplicate highlights are allowed and individually editable (no dedup).
- **Auth**: Required (owner only)
- **Request Body**:
  ```json
  {
    "user_note": "Updated note for the research paper",
    "color": "green"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "id": "uuid",
      "page_url": "https://example.com/article",
      "highlighted_text": "Important text passage",
      "user_note": "Updated note for the research paper",
      "color": "green",
      "version": 3,
      "updated_at": "2026-11-21T00:05:00Z"
    }
  }
  ```
- **Error codes**: `404 HIGHLIGHT_NOT_FOUND` (unknown ID, foreign owner or tombstoned), `422 VALIDATION_ERROR` (invalid `color` value outside the supported set, oversized `user_note`, or no mutable field supplied).

### 7.10 GET `/api/v1/reading/history/stats` (Reading Statistics)
- **Description**: On-the-fly aggregate of the user's reading history for a bounded date range — no dedicated stats table, no sync entity. Computed from `reading_history` rows only (Privacy-Mode rows do not exist by definition). Covered by the **general API bucket** (`API_REQUESTS_PER_MINUTE`).
- **Auth**: Required
- **Query Params**: `from`, `to` — `YYYY-MM-DD` UTC bounds on `visited_at`, required bounded range (max 366 days; out-of-range returns `422 VALIDATION_ERROR`).
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "articles_count": 84,
      "total_reading_time_seconds": 51230,
      "top_domains": [
        { "domain": "example.com", "visits": 31, "reading_time_seconds": 20411 },
        { "domain": "docs.python.org", "visits": 18, "reading_time_seconds": 9902 }
      ],
      "recent": [
        {
          "id": "uuid",
          "page_url": "https://example.com/article",
          "page_title": "Example Article Title",
          "reading_time_seconds": 45,
          "visited_at": "2026-11-21T00:00:00Z"
        }
      ]
    }
  }
  ```
  - `top_domains` is host-normalized the same way as the domain blacklist (IDNA, root-dot strip) and capped at a small fixed size (e.g. top 5 by visits).
  - `recent` is a short list of the latest `HistoryItem` rows within the range (bounded, e.g. 10 items).
  - Deleting history (`DELETE /reading/history`, §7.6) immediately removes the underlying rows, so aggregates reset on the next call — there is no cached snapshot to invalidate.
- **Error codes**: `422 VALIDATION_ERROR` (missing/bad dates or range over 366 days).

---

## 8. Multi-Device Synchronization (`/api/v1/sync` — Feature J)

**Out-of-sync scope**: Synchronization covers exactly conversations, highlights and settings. **API keys (`user_api_keys`), usage aggregates (`usage_daily`) and quiz history (`quiz_records`) are deliberately NOT part of `/sync`** — they are not pulled, pushed, conflict-checked or tombstoned. API keys are per-provider UPSERTs with last-write-wins semantics (§4.2); usage is a server-side aggregate read via `GET /api/v1/users/me/usage` (§3.6); quiz history is a server-side record read via `GET /api/v1/quiz` (§6.3) — generated quizzes are created by the server, not by client mutation, so there is nothing for a client to push and no cursor that touches these entities.

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
        "ui_language": "en",
        "explanation_level": "expert",
        "personalization_consent": true,
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
- **Batch 409 semantics — ALL-OR-NOTHING (ISSUE-036)**: If **any** mutation in the batch hits a `409 SYNC_CONFLICT`, the entire batch is rolled back — no mutation from that request is applied, not even the non-conflicting ones. The single `409` response carries the first conflicting record (entity type, `entity_id`, client `base_version`, current server `version` and server row state) so the client can resolve and re-submit. Clients should not assume partial application.
- **Tombstone vs stale push**: Pushing an `update` with a stale `base_version` against a row that has meanwhile been **tombstoned** returns `409 SYNC_CONFLICT` whose conflicting record includes `server_record.is_deleted = true` — the client must treat the entity as deleted remotely and drop or recreate its local copy (never resurrect it silently, per ADR-013).
- **Duplicate `create` push**: Pushing a `create` whose `entity_id` already exists on the server (including a tombstoned row) returns `409 SYNC_CONFLICT` — the backend does **not** silently upsert by unique key. The client must pull (§8.1) to fetch the authoritative row/state before re-submitting.

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

### 9.5 POST `/api/v1/admin/users/{id}/send-reset-link` (Admin Password Reset Trigger — BE-19)
- **Description**: Lets an administrator trigger the same password-reset email a user would receive from "forgot password", backing the admin portal's reset-password-link button. The link/token mechanics, TTL (60 minutes) and revocation semantics are identical to `POST /auth/forgot-password` (§2.7.3): the user sets the new password themselves via `POST /auth/reset-password`; admins never set or view passwords.
- **Anti-abuse**: Response is neutral regardless of the target's existence/state (same anti-enumeration rule). Shares the per-email resend cap (3/hour) and logs the admin actor for audit. Rate-limited by the shared auth bucket plus the per-email cap.
- **Privacy guard**: No per-user usage or reading data is revealed by this endpoint.
- **Auth**: Required (Role `admin`)
- **Response**: `200 OK`
  ```json
  {"data": null, "message": "If that account exists, a reset link has been sent."}
  ```
- **Error codes**: `403 FORBIDDEN_RESOURCE` (non-admin), `429 RATE_LIMIT_EXCEEDED`, `404 USER_NOT_FOUND` (only for a malformed/nonexistent ID parameter, not a registered-but-state-unknown account).

---

## 10. Security Attack Scenarios & Cross-Cutting Hardening

Cross-cutting attack scenarios and the mandated mitigations. Endpoint-specific rules are also noted inline (§2.1, §2.2, §2.7, §3.5, §9.5).

### 10.1 Brute Force & Credential Stuffing
- The shared auth bucket limits all `/api/v1/auth/*` requests to `AUTH_REQUESTS_PER_MINUTE` (default 20/min) per client identity (trusted client-IP bucket for public routes).
- Failed logins return a **uniform `401 INVALID_CREDENTIALS`** — identical for unknown email and wrong password — with constant-shape payloads; no response distinguishes "email exists".
- Lockouts are never permanent in the MVP; the rate window is the throttle.

### 10.2 User Enumeration
- `POST /auth/register` duplicates return `409 EMAIL_ALREADY_EXISTS` (inherent to registration UX); `forgot-password` (§2.7.3) and `verify-email/resend` (§2.7.1) ALWAYS return the same neutral `200` message for known and unknown addresses.
- `forgot-password` responses keep stable timing (deferred/padded mail dispatch) so latency cannot leak account existence.
- `PATCH /users/me` email change returns `409 EMAIL_ALREADY_EXISTS` — acceptable because the caller is already authenticated; no unauthenticated enumeration surface exists there.

### 10.3 Email Bombing
- Verification/reset resend is capped at 3/hour **per email address** (default; `VERIFICATION_RESEND_LIMIT_PER_HOUR`), with the shared 20/min auth bucket as a second layer; unknown addresses count against the per-email cap too.
- Admin `send-reset-link` (§9.5) is subject to the same per-email cap and is audit-logged.

### 10.4 Token Brute-Force, Theft & Replay
- Tokens are 256-bit URL-safe CSPRNG values (`secrets.token_urlsafe(32)`); online guessing is infeasible.
- **Hash-at-rest**: the database stores only the SHA-256 hex digest; a database leak does not yield usable links. The plaintext token exists only inside the emailed link.
- **Single-use**: consumption sets `used_at` atomically; replayed tokens return `400 VERIFICATION_TOKEN_INVALID` / `400 RESET_TOKEN_INVALID`.
- **TTL**: verification 24h (`VERIFICATION_TOKEN_TTL_HOURS`), reset 60 minutes (`PASSWORD_RESET_TOKEN_TTL_MINUTES`).
- **Constant-time compare**: token lookups use `secrets.compare_digest` on hashes, preventing timing oracles.
- **Reset revokes everything**: successful password reset revokes all `auth_sessions` (reason `security`), so an attacker with an existing session loses access and a victim regains control by resetting.
- **No token leakage**: verification/reset links and tokens are never logged (`FR-OPS-03` applies to mail payloads), never echoed in API responses, and links are single-destination (no token in referrer-visible URLs beyond the link itself).

### 10.5 CSRF
- All state-changing endpoints authenticate exclusively via the `Authorization: Bearer` header — no auth cookies are set — making classic state-changing CSRF inapplicable to the backend API. The extension and dashboard store tokens client-side; servers must not introduce cookie sessions without revisiting this analysis.

### 10.6 Account Takeover via OAuth Auto-Link
- OAuth linking (Google/GitHub) proceeds only when the **provider explicitly confirms the email as verified**; unverified provider emails never auto-link (`403 EMAIL_NOT_VERIFIED` / `400 OAUTH_EMAIL_MISSING`).
- When a NEW provider identity is linked to an existing account (e.g. a password account later linked by Google), the backend sends the account owner a notification email ("A new sign-in provider was linked to your account") so silent takeover attempts are visible to the legitimate owner.
- Change-email (§3.5) requires `current_password` for password accounts and re-verifies ownership of the NEW address, keeping an OAuth attacker from pivoting the login identity.

### 10.7 SSRF
- `POST /api/v1/api-keys/{provider}/validate` (§4.4) and the AI gateway call ONLY fixed, allowlisted provider endpoints (OpenAI / Gemini / Anthropic base URLs). User-supplied `provider` values map to fixed adapters; no user-controlled URL is ever fetched server-side, eliminating SSRF via the validate/ping path.

### 10.8 Validate-Endpoint Abuse
- The validate ping hits external providers; it is covered by the general API rate bucket (`API_REQUESTS_PER_MINUTE`) and must not be used as a free oracle — responses reveal only `valid: true/false` or the two documented failure codes (`400 KEY_VALIDATION_FAILED`, `502 UPSTREAM_AI_ERROR`).
