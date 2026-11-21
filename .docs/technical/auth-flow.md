# Authentication Flow

## 1. Overview
ReadHead-BE supports three login methods:
1. **Email & Password** (with salted bcrypt hashing)
2. **Google OAuth2** (using Google Identity token verification or web flow)
3. **GitHub OAuth2** (using OAuth authorization code exchange)

All authentication paths culminate in issuing a standard JWT pair:
- **Access Token**: Short-lived (15 mins), used in HTTP headers: `Authorization: Bearer <access_token>`.
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
       |                                                |-- 2. Security Check: Check account status (revoked_users:{user_id} & DB user.status)
       |                                                |      - If banned/suspended: Return 401 USER_SUSPENDED immediately
       |                                                |-- 3. Acquire Distributed Lock (lock:refresh:{hash(token)}, TTL=5s)
       |                                                |      - If Lock Acquired (Winner):
       |                                                |        a. Check DB revocation status (if revoked -> Token Reuse Detected!)
       |                                                |        b. Rotate: issue new access & refresh tokens
       |                                                |        c. Commit DB transaction: mark old token revoked, save new token
       |                                                |        d. Cache rotated pair in Redis: refresh_grace:{hash(token)} (30s TTL)
       |                                                |        e. Release Distributed Lock
       |                                                |      - If Lock Contended (Waiting concurrent request):
       |                                                |        a. Wait for lock release (polling with 50ms backoff, max 2s)
       |                                                |        b. Read from Redis Grace Cache: return cached pair immediately
       |<- 200 OK (new access_token, refresh_token) ----|
```

#### 2.3.1 Multi-Tab Concurrency Grace Period & Distributed Locking
When multiple browser tabs make concurrent refresh requests upon access token expiry:
1. **Strict Verification Order**:
   - **Step 1: Signature & Expiration**: The refresh JWT signature, issuer, and expiration are validated. Expired tokens outside valid lifetime immediately return `401 REFRESH_TOKEN_EXPIRED`.
   - **Step 2: Account Status & Revocation Check**: The server inspects Redis key `revoked_users:{user_id}` and `users.status`. If the account is banned, suspended, or deleted, the request is immediately rejected with `401 USER_SUSPENDED`. **Cached tokens are never returned to suspended accounts.**
   - **Step 3: Fast-Path Grace Cache Check**: If Redis holds an active grace mapping `refresh_grace:{hash(old_token)} -> new_token_pair`, the cached pair is returned immediately without touching the database.
   - **Step 4: Atomic Distributed Lock (`lock:refresh:{hash(old_token)}`)**:
     - If the cache misses, the request attempts to acquire a Redis distributed mutex `SET lock:refresh:{hash(old_token)} <req_id> NX EX 5`.
     - **Winner Request**:
       1. Verifies database record for `old_token`. If `is_revoked = TRUE`, this is a true **Token Reuse Attack**: immediately revoke all active refresh tokens for the user, purge any existing grace cache keys (`DEL refresh_grace:*`), and return `401 REFRESH_TOKEN_REVOKED`.
       2. Issues new access token (15 mins) and new refresh token (30 days).
       3. Commits database transaction: updates `old_token.is_revoked = TRUE` and inserts `new_token`.
       4. Writes `refresh_grace:{hash(old_token)} -> new_token_pair` to Redis with a **30-second TTL**.
       5. Releases the distributed lock.
       6. *Redis Failure Handling*: If Redis is unavailable or writing to Redis fails after the DB has successfully committed, the server logs a warning and returns the newly generated token pair directly to the client (graceful degraded rotation).
     - **Concurrent Sibling Request(s)**:
       1. If lock acquisition fails because another tab is already rotating, the sibling tab waits for lock release with a short exponential backoff (polling every 50ms, max 2000ms).
       2. Once released, it reads `refresh_grace:{hash(old_token)}` from Redis and receives the exact same token pair without executing duplicate rotation or triggering a false positive reuse detection.

### 2.4 Logout & Session Revocation
```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/logout (refresh_token) ->|
       |                                                |-- Mark refresh token as revoked in DB
       |                                                |-- Invalidate Redis grace cache: DEL refresh_grace:{hash(token)}
       |<- 204 No Content ------------------------------|
```

### 2.5 Real-Time Account Deletion / Suspension Protocol
- When an account is suspended or banned by an administrator (`PATCH /api/v1/admin/users/{id}/status`) or deleted by the user (`DELETE /api/v1/users/me`):
  1. The database sets `users.status = 'banned'` (or cascades deletion) and revokes all refresh tokens.
  2. Redis key `revoked_users:{user_id}` is written with TTL = 3600 seconds.
  3. All active Redis grace cache entries for the user's tokens are purged immediately (`DEL refresh_grace:{hash(token)}`).
  4. Every authenticated endpoint checks `revoked_users:{user_id}` via the auth dependency in sub-millisecond time. If present, requests fail with `401 USER_SUSPENDED`.
  5. Active in-flight AI streaming generators (`POST /api/v1/ai/stream`) inspect the cancellation flag on each yielded chunk; upon detecting user revocation, the stream emits `event: error` (`USER_SUSPENDED`) and terminates the socket immediately.

### 2.6 Multi-Account Isolation & Storage Purge (`FR-ACC-04`)
To prevent cross-account data leakage on shared browser environments:
- Upon receiving a successful logout response, the client must purge all credentials, drafts (`draft_*`), and cached DOM extracts from `chrome.storage.local`.
- Background service worker broadcasts `ACTION_PURGE_SESSION` across all active extension frames, redirecting any open Side Panels to `/login`.
