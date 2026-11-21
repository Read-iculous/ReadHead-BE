# Authentication Flow

## 1. Overview
ReadHead-BE supports three login methods:
1. **Email & Password** (with salted bcrypt hashing)
2. **Google OAuth2** (using Google Identity token verification or web flow)
3. **GitHub OAuth2** (using OAuth authorization code exchange)

All authentication paths culminate in issuing a standard JWT pair:
- **Access Token**: Short-lived (60 mins), used in HTTP headers: `Authorization: Bearer <access_token>`.
- **Refresh Token**: Long-lived (30 days), stored in the database to allow revocation and silent session renewal.

## 2. Authentication Flows

### 2.1 Email & Password Registration & Login
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
       |                                                |-- Create session / refresh token in DB
       |<- 200 OK (access_token, refresh_token) --------|
```

### 2.2 Google & GitHub OAuth2 Flow
For Chrome Extensions, Google OAuth verifies a signed Google ID Token, while GitHub OAuth exchanges an authorization code.

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
When an API request returns `401 Unauthorized` with error code `TOKEN_EXPIRED`:

```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/refresh (refresh_token) >|
       |                                                |-- 1. Verify JWT signature & expiration (PyJWT leeway=60s for clock drift)
       |                                                |-- 2. Check Redis 30s Grace Period cache
       |                                                |-- 3. Check DB revocation status:
       |                                                |      - If already revoked: Token Reuse detected!
       |                                                |        Revoke all user tokens & reject (401)
       |                                                |-- 4. Rotate: issue new access & refresh tokens
       |                                                |-- 5. Mark old token revoked in DB
       |                                                |-- 6. Cache rotated pair in Redis (30s TTL)
       |<- 200 OK (new access_token, refresh_token) ----|
```

#### 2.3.1 Multi-Tab Concurrency Grace Period (30 Seconds)
When multiple browser tabs make concurrent refresh requests upon access token expiry:
1. **Verification Order**:
   - First, the JWT signature and expiration timestamp are validated. Expired tokens outside their valid lifetime immediately return `401 REFRESH_TOKEN_EXPIRED`.
   - Next, Redis is checked for an active 30-second grace window mapping: `hash(old_refresh_token) -> new_token_pair`.
   - If found in Redis, the new token pair is returned immediately without re-rotating or raising an error.
   - If not found in Redis, the database `refresh_tokens` record is checked. If the token is already marked `is_revoked = TRUE`, this constitutes **Token Reuse Detection**: all active refresh tokens for the user account are immediately revoked, the Redis grace cache is purged, and `401 REFRESH_TOKEN_REVOKED` is returned.
2. **Normal Rotation**:
   - The first tab to arrive rotates the token: marks the old token `is_revoked = TRUE` in the DB, generates a new token pair, and writes `hash(old_refresh_token) -> new_token_pair` to Redis with a **30-second TTL**.
   - Subsequent concurrent requests from other tabs within 30 seconds are safely served the cached new token pair.

### 2.4 Logout & Session Revocation
```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/logout (refresh_token) ->|
       |                                                |-- Mark refresh token as revoked in DB
       |                                                |-- Purge token from Redis grace cache
       |<- 204 No Content ------------------------------|
```

### 2.5 Real-Time Account Deletion / Suspension Protocol
- When an account is suspended or banned by an administrator (`PATCH /api/v1/admin/users/{id}/status`) or deleted by the user (`DELETE /api/v1/users/me`):
  1. The database sets `users.status = 'banned'` (or cascades deletion) and revokes all refresh tokens.
  2. Redis key `revoked_users:{user_id}` is written with TTL = 3600 seconds.
  3. Every authenticated endpoint checks `revoked_users:{user_id}` via the auth dependency in sub-millisecond time. If present, requests fail with `401 USER_SUSPENDED`.
  4. Active in-flight AI streaming generators (`POST /api/v1/ai/stream`) inspect the cancellation flag on each yielded chunk; upon detecting user revocation, the stream emits `event: error` (`USER_SUSPENDED`) and terminates the socket immediately.

### 2.6 Multi-Account Isolation & Storage Purge (`FR-ACC-04`)
To prevent cross-account data leakage on shared browser environments:
- Upon receiving a successful logout response, the client must purge all credentials, drafts (`draft_*`), and cached DOM extracts from `chrome.storage.local`.
- Background service worker broadcasts `ACTION_PURGE_SESSION` across all active extension frames, redirecting any open Side Panels to `/login`.
