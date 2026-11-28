# Authentication Flow

## 1. Overview
ReadHead-BE supports three login methods:
1. **Email & Password** (with salted bcrypt hashing)
2. **Google OAuth2** (using Google Identity token verification or web flow)
3. **GitHub OAuth2** (using OAuth authorization code exchange)

Successful login and OAuth issue a standard JWT pair; registration returns the user profile only:
- **Access Token**: Short-lived (15 mins), used in HTTP headers: `Authorization: Bearer <access_token>`.
- **Refresh Token**: Long-lived (30 days), stored in the database to allow revocation and silent session renewal.

## 2. Authentication Flows

### 2.1 Email & Password Registration & Login
All bcrypt-bound password inputs (registration, login and deletion confirmation) reject NUL and enforce their UTF-8 byte limits at the schema boundary. Invalid values return 422 before invoking hash/verify; error payloads do not echo credentials.

```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/register (email, pass) ->|
       |                                                |-- Hash password with bcrypt
       |                                                |-- Create User record in DB
       |<- 201 Created (User profile data) -------------|
       |                                                |
       |----- POST /api/v1/auth/login (email, pass) ---->|
       |                                                |-- Verify bcrypt password & check status == active
       |                                                |-- Create auth_sessions row / refresh token in DB
       |<- 200 OK (access_token, refresh_token) --------|
```

### 2.2 Google & GitHub OAuth2 Flow
For Chrome Extensions, Google OAuth verifies a signed Google ID Token, while GitHub OAuth exchanges an authorization code.

Validate provider response types before looking up/linking users. Google tokeninfo must include a non-empty bounded string subject, syntactically valid email, explicit boolean verification flag (including Google's `"true"`/`"false"` representations), integer expiry (including tokeninfo's decimal string representation), trusted issuer and matching audience. GitHub requires a non-empty code-exchange token, positive integer profile ID and typed email/primary/verified records. Malformed payloads return `401 TOKEN_INVALID`; unverified Google email returns `403 EMAIL_NOT_VERIFIED`, and a valid GitHub email list without a verified primary email returns `400 OAUTH_EMAIL_MISSING`. Optional display metadata must be strings or null. Reject invalid identity data before any database mutation.

```
Extension Client                                  ReadHead-BE               OAuth Provider
       |                                                |                         |
       |-- Obtain id_token (Google) or code (GitHub) ---------------------------->|
       |<-- id_token / auth_code -----------------------------------------------|
       |                                                |                         |
       |-- POST /api/v1/auth/oauth/google (id_token) -->|                         |
       |   OR /api/v1/auth/oauth/github (code)          |                         |
       |                                                |-- Verify token/code --->|
       |                                                |<-- Verified Profile ----|
       |                                                |-- Enforce: email_verified == true
       |                                                |-- (GitHub: fetch /user/emails if private)
       |                                                |-- Find or auto-link User
       |                                                |-- Issue ReadHead JWTs   |
       |<- 200 OK (access_token, refresh_token) --------|
```

### 2.3 Token Refresh Flow & Rotation
Access tokens expire after 15 minutes; refresh tokens expire after 30 days. Login and OAuth create an `auth_sessions` row. Every token pair in the rotation chain carries the same JWT `sid` (the session UUID), plus `sub`, `jti`, and an explicit access/refresh token type. `sid` is unrelated to the browser's `reading_session_id`.

All session lifecycle writers use one PostgreSQL lock order: **user → auth session(s) → refresh token(s)**. Lock and refresh the user row before taking session locks, including grace-cache validation, rotation, logout and revocation. This prevents a session/FK lock inversion with suspension or account deletion. Login/OAuth also lock and reload the user immediately before issuing a session: verification may have overlapped an account status change. If suspension/deletion commits first, no new session is issued; if issuance commits first, subsequent suspension revokes that session too.

#### 2.3.1 Authoritative Session Check and Grace Cache
1. Verify JWT signature, issuer, token type and expiry (clock leeway: 60 seconds). Return `401 TOKEN_INVALID` or `401 REFRESH_TOKEN_EXPIRED` as appropriate.
2. Load the user and `auth_sessions` by authenticated `sub` and `sid`. Missing/deleted users return `401 UNAUTHORIZED`; suspended/banned users return `401 USER_SUSPENDED`; revoked/expired sessions return `401 REFRESH_TOKEN_REVOKED`/`401 REFRESH_TOKEN_EXPIRED`. PostgreSQL is authoritative even if Redis is healthy.
3. A grace mapping is `refresh_grace:{sid}:{old_token_hash} -> {sid, replacement_token_id, token_pair}`, TTL 30 seconds. Before returning a cached pair, revalidate the session and replacement token under the session row lock. A revoked session or a replacement revoked for logout/security must never be returned. If the replacement has itself rotated, follow its grace mapping to a still-active successor without a fixed hop limit. Track visited token hashes to reject corrupt cycles; missing/expired/invalid mappings retain the temporary-failure behavior below.
4. Index cache keys in `refresh_grace_keys:{sid}` with TTL refreshed to at least 30 seconds after the last mapping. Enumerate these exact keys for session cleanup; never use a global wildcard deletion. Cache entries left by a failed cleanup are unusable because the authoritative session check rejects them. Store no token pairs in PostgreSQL or logs.

#### 2.3.2 Distributed Lock, Database Guard and Failure Outcomes
1. After a grace-cache miss, acquire `lock:refresh:{sid}:{old_token_hash}` using a unique owner value and a 5-second lease. Contenders poll at 50ms intervals for at most 2 seconds. Timeout returns `503 REFRESH_TEMPORARILY_UNAVAILABLE` with `Retry-After: 1`, without revoking any session.
2. **After acquiring the lock, check the grace cache again.** This covers another request completing between the initial cache lookup and lock acquisition. Validate any cached result as in §2.3.1.
3. Lock and refresh the `users` row first, then lock the `auth_sessions` row with `SELECT ... FOR UPDATE`, recheck user/session validity, then load the token by `(session_id, token_hash)`. Use an atomic conditional token update (`WHERE id = :id AND session_id = :sid AND is_revoked = FALSE RETURNING id`) and insert its successor in the same transaction. Mark the old token `revocation_reason = 'rotated'`, set `revoked_at`, and link `replaced_by_token_id`. Update the session expiry to the new refresh expiry. Only one transaction may rotate a given token, including when a Redis lease expires or Redis is unavailable.
4. Commit before caching the new pair. Register the mapping under the session cache-key index, then return the pair. Release/renew the Redis lock only when its stored owner value matches this request (atomic compare-and-delete/renew); a request must not release another owner's lease.
5. If Redis is unavailable, use the same PostgreSQL session-row lock and conditional update. If Redis fails after DB commit, the winning request still receives its generated pair. No plaintext/encrypted token-pair recovery copy is stored in PostgreSQL in the MVP.
6. A sibling presenting a token marked `rotated` within 30 seconds, without an available grace result, receives `503 REFRESH_TEMPORARILY_UNAVAILABLE` (`Retry-After: 1`). Keep credentials/drafts; check the extension's shared token store and retry only the refresh operation with a bounded policy (at most two retries; never retry an AI generation automatically). If the winning result was lost permanently, explicitly ask the user to sign in again.
7. A rotated token older than the 30-second window returns `401 REFRESH_TOKEN_REVOKED`. A cache miss, lock timeout, lease expiry or Redis failure alone is **not evidence of a security incident** and must not revoke other sessions. `logout` revocation remains a normal session termination; only an explicit security event sets reason `security` and revokes the affected session(s). Do not classify every `is_revoked = TRUE` record as token theft.

### 2.4 Logout & Session Revocation
- Authenticate the access-token `sid`; verify that the supplied refresh token belongs to the same user and session (including an older token in that chain).
- Acquire the user lock before the same session row lock used by rotation, set `auth_sessions.revoked_at` and `revocation_reason = 'logout'`, and revoke all still-active refresh tokens in that session with reason `logout` in one DB transaction. Commit, then delete every exact grace-cache key indexed by `refresh_grace_keys:{sid}` and the index itself. Logout affects this session, not unrelated devices.
- For A -> B -> C rotation followed by logout using C, all cached mappings A -> B and B -> C become unusable. Cleanup failure must not restore access: all authenticated requests validate the authoritative session (`401 UNAUTHORIZED` for a revoked access-token session), and refresh returns `401 REFRESH_TOKEN_REVOKED`.
- In-flight stream loops check both `revoked_users:{user_id}` and `revoked_sessions:{sid}` in normal operation. Publish `revoked_sessions:{sid}` after logout, with TTL covering the remaining access-token lifetime plus clock leeway. Redis failure follows ADR-010's declared degraded-stream policy.
- Logout returns `204 No Content`; Redis cleanup failure is logged without credentials and does not roll back the DB revocation.

### 2.5 Account Deletion, Suspension and Security Events
- Ban/suspend updates `users.status` and `is_active`, revokes every `auth_sessions` row for that user and all active refresh tokens with reason `security`; account deletion cascades sessions and tokens. Use the same session-row locking discipline as rotation, in deterministic session-ID order.
- **Password reset (BE-19)** reuses this exact mechanism: a successful `POST /auth/reset-password` revokes EVERY `auth_sessions` row of the user — and all active refresh tokens — with reason `security`, in deterministic session-ID order under the same user-first lock order. No `revoked_users:{user_id}` user-level marker is set (the account itself remains active); per-session markers are published so in-flight streams terminate. Unlike suspension, reactivation steps do not apply; the user simply signs in again on each device.
- After DB commit, publish `revoked_users:{user_id}` (TTL 3600s), publish `revoked_sessions:{sid}` for every revoked session, and clean the user's session-indexed grace entries. Session markers last at least 240 seconds (covering the 180-second maximum stream plus leeway) or the access lifetime plus 60 seconds, whichever is longer. Logout uses the same session-marker helper. A later cached pair still fails the DB user/session check if cleanup is incomplete.
- Reactivation updates status to `active`, sets `is_active = TRUE` and clears only the user marker; revoked sessions and their stream-cancellation markers stay revoked. A suspend/reactivate pair between two provider tokens must still stop an old stream with `UNAUTHORIZED`; a new login creates a different, usable session.
- User-marker reconciliation runs in a short post-commit transaction: re-read the latest user under `FOR UPDATE` and retain that lock through the Redis set/delete. A delayed publisher uses the latest committed status, not its obsolete request body; a newer status writer cannot overtake a marker operation already holding the lock. This preserves both suspend→reactivate and reactivate→suspend ordering. Missing users remain marked as revoked. Redis publication stays best-effort and DB revocation remains authoritative on new requests.
- Redis outage does not bypass DB user/session validation for new requests. Active streams follow ADR-010 (Redis checks skipped during the declared outage).

### 2.6 Multi-Account Isolation & Storage Purge (`FR-ACC-04`)
To prevent cross-account data leakage on shared browser environments:
- Upon receiving a successful logout response, the client must purge all credentials, drafts (`draft_*`), and cached DOM extracts from `chrome.storage.local`.
- Background service worker broadcasts `ACTION_PURGE_SESSION` across all active extension frames, redirecting any open Side Panels to `/login`.

### 2.7 Email Verification Flow (Mandatory — BE-19)
Password registration REQUIRES email verification before login. OAuth (Google/GitHub) logins are exempt: the provider must already assert `email_verified == true`.

```
Extension Client                                  ReadHead-BE               Resend
       |                                                |                      |
       |-- POST /api/v1/auth/register (email, pass) --->|                      |
       |                                                |-- bcrypt hash, create user (is_verified = FALSE)
       |                                                |-- create email_verification_tokens row (SHA-256 hash only)
       |                                                |-- fire-and-forget: POST /emails ----->|
       |<- 201 Created (verification_email_sent) ------------------------------------|
       |                                                |                      |
       |   (user clicks emailed link)                   |                      |
       |-- POST /api/v1/auth/verify-email {token} ----->|                      |
       |                                                |-- SHA-256(token), compare_digest lookup
       |                                                |-- mark used_at, set users.is_verified = TRUE
       |<- 200 OK -------------------------------------------------|           |
       |                                                |                      |
       |-- POST /api/v1/auth/login --------------------->|                      |
       |                                                |-- verify password & is_verified == TRUE
       |<- 200 OK (access_token, refresh_token) --------|
```

- **Registration**: `201 Created` is returned immediately; email dispatch is fire-and-forget. The response includes `verification_email_sent: boolean`. Register NEVER fails because of mail errors.
- **Token storage**: 256-bit URL-safe CSPRNG token (`secrets.token_urlsafe(32)`); the plaintext exists only inside the emailed link. The database (`email_verification_tokens`) stores the SHA-256 hex digest, `expires_at` (TTL `VERIFICATION_TOKEN_TTL_HOURS`, default 24h) and nullable `used_at`. Comparisons use `secrets.compare_digest`.
- **Link**: `{APP_BASE_URL}/verify-email?token=...` rendered by the extension/dashboard, which submits the token to `POST /auth/verify-email`.
- **Verification outcomes**: valid → mark used + `is_verified = TRUE` (single transaction); expired (past `expires_at`) → `400 VERIFICATION_TOKEN_EXPIRED`; unknown/already-used → `400 VERIFICATION_TOKEN_INVALID`; already-verified replay → neutral `200 "already verified"` (idempotent).
- **Login gate**: after credentials verify, `is_verified = FALSE` returns `403 EMAIL_NOT_VERIFIED` with `can_resend: true`; no session is created.
- **Resend**: `POST /auth/verify-email/resend` (auth optional) issues a fresh token/email. Rate limit: 3/hour per email address (default) plus the shared auth bucket (20/min). Anti-enumeration: uniform neutral 200 for unknown and already-verified addresses.
- **Resend delivery, retry & failure handling**: dispatch uses `httpx` against `https://api.resend.com/emails`. On `429`/`5xx`/timeout: retry up to 3 times with exponential backoff (e.g. 1s/2s/4s, jittered); a final failure logs the sanitized outcome (no recipient PII beyond the target address, no token) and reports `verification_email_sent: false` — registration/HTTP still succeed. Resend client errors (4xx other than 429, e.g. invalid API key or unverified domain) are not retried; they are configuration faults logged for operators.
- **Privacy**: no verification-link content, token or email body is ever logged (`FR-OPS-03` applies to mail payloads).

### 2.8 Password Reset Flow (BE-19)
```
Extension Client                                  ReadHead-BE               Resend
       |                                                |                      |
       |-- POST /api/v1/auth/forgot-password ---------->|                      |
       |                                                |-- (account exists?) create password_reset_tokens row (hash only)
       |                                                |-- fire-and-forget: POST /emails ----->|
       |<- 200 OK (identical neutral message) ---------------------------------------|
       |                                                |                      |
       |   (user clicks emailed link, sets new password)|                      |
       |-- POST /api/v1/auth/reset-password ----------->|                      |
       |   {token, new_password}                        |-- consume token, update bcrypt hash
       |                                                |-- revoke ALL auth_sessions (reason 'security')
       |<- 200 OK -------------------------------------------------|           |
```

- **Forgot**: ALWAYS `200 OK` with the identical neutral message whether or not the address is registered; response timing is held stable (anti-enumeration). Token TTL: `PASSWORD_RESET_TOKEN_TTL_MINUTES`, default 60 minutes.
- **Reset**: consumes the token (same hash-at-rest/single-use semantics as §2.7), applies the registration password rule (8–72 bytes, NUL rejected), then **revokes every `auth_sessions` row of the user with reason `security`** using the §2.5 locking/revocation discipline. All devices are signed out; the user must log in again everywhere with the new password. The consumed token can never reset again.
- **Anti-enumeration**: invalid/expired tokens return distinct 400 codes only when a token was actually presented; the forgot-password stage never reveals account existence.
- **Failure handling**: mail dispatch follows the same fire-and-forget/retry policy as §2.7; repeated forgot requests are capped by the same per-email resend limit.

### 2.9 Change Email Flow (BE-19)
- `PATCH /api/v1/users/me` with a new `email` (plus `current_password` for password accounts) verifies the current password, checks uniqueness of the normalized new address, sets `is_verified = FALSE`, and sends a verification email to the NEW address (fire-and-forget, §2.7 retry policy).
- **Grace semantics**: the OLD email remains the effective login identity until the new address is verified; after verification, the new email replaces it. A stale/abandoned change simply leaves the account unverified on the old identity — login then follows the §2.7 unverified gate, and the user can re-request verification for whichever address is current.
- Re-sending the change-verification uses the same `POST /auth/verify-email/resend` limits. OAuth identity links are unaffected; account takeover protections (provider-verified linking + owner notification) apply as in §2.2 and the security notes below.

## 3. Security Considerations & Attack Scenarios

### 3.1 Brute Force & Credential Stuffing
- Auth endpoints share the 20/min fixed-window bucket; failures return uniform `401 INVALID_CREDENTIALS` payloads with stable shapes. No response, log or timing differentiates "unknown email" from "wrong password".

### 3.2 User Enumeration
- Register duplicates return `409` (inherent); forgot-password and verification-resend always return the same neutral 200 with stable timing for both known and unknown addresses. Resend counters apply to unknown addresses too, so per-email volume cannot probe existence.

### 3.3 Email Bombing
- Per-email cap (3/hour default) + shared auth bucket on resend/forgot; admin-triggered reset links are subject to the same cap and are audit-logged with the admin actor.

### 3.4 Token Theft & Brute-Force
- 256-bit CSPRNG tokens make online guessing infeasible; hashes-only storage neutralizes database leaks; single-use (`used_at`) plus TTL (24h / 60 min) bound replay windows; `secrets.compare_digest` prevents timing oracles. A successful password reset revokes all sessions (reason `security`), cutting off any attacker holding a stolen session.

### 3.5 Session Fixation
- Every login and OAuth issuance creates a NEW `auth_sessions` row with a fresh JWT `sid` and token pair; tokens are never reissued across logins, so a pre-authentication token cannot be carried into a post-authentication session.

### 3.6 Timing Attacks
- Password verification always runs bcrypt (dummy verify for unknown users) so response time does not depend on account existence; token comparisons use constant-time digest comparison; forgot-password responses pad/defer to a stable duration.

### 3.7 Link & Email Content Guidelines
- Emails contain no credentials or plaintext tokens beyond the single action link; links point at `{APP_BASE_URL}` routes only. Logging MUST NOT include mail payloads, tokens or verification/reset links (`FR-OPS-03`); structured logs record only sanitized outcomes (`sent`/`failed`, provider status class).

### 3.8 CSRF
- The API authenticates exclusively via the `Authorization: Bearer` header and sets no auth cookies; classic state-changing CSRF does not apply. Any future cookie-based surface must re-evaluate this section.
