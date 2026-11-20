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
       |<- 201 Created (User profile, Tokens) ----------|
       |                                                |
       |----- POST /api/v1/auth/login (email, pass) ---->|
       |                                                |-- Verify bcrypt password
       |                                                |-- Create session / refresh token
       |<- 200 OK (access_token, refresh_token) --------|
```

### 2.2 Google & GitHub OAuth2 Flow
For Chrome Extensions, OAuth typically runs using `chrome.identity.launchWebAuthFlow` or by sending the provider's `id_token` / `code` directly to the backend.

```
Extension Client                                  ReadHead-BE               OAuth Provider
       |                                                |                         |
       |-- Obtain id_token/auth_code from provider ----------------------------->|
       |<-- id_token or code ---------------------------------------------------|
       |                                                |                         |
       |-- POST /api/v1/auth/oauth/google (token/code) ->|                         |
       |                                                |-- Verify with Google -->|
       |                                                |<-- Profile (email, id) -|
       |                                                |-- Find or create User   |
       |                                                |-- Issue ReadHead JWTs   |
       |<- 200 OK (access_token, refresh_token) --------|
```

### 2.3 Token Refresh Flow & Rotation
When an API request returns `401 Unauthorized` with error code `TOKEN_EXPIRED`:
```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/refresh (refresh_token) >|
       |                                                |-- Verify token signature & DB revocation
       |                                                |-- Rotate: issue new access & refresh tokens
       |                                                |-- Cache rotated pair in Redis (30s TTL)
       |<- 200 OK (new access_token, refresh_token) ----|
```

#### 2.3.1 Multi-Tab Concurrency Grace Period (30 Seconds)
When multiple browser tabs make concurrent refresh requests upon access token expiry:
1. The first request successfully rotates the token pair and caches the mapping `hash(old_refresh_token) -> new_token_pair` in Redis with a **30-second TTL**.
2. Subsequent concurrent requests arriving within 30 seconds presenting the same old token are served the newly generated token pair without error.
3. Requests presenting an expired/rotated token after 30 seconds trigger **Token Reuse Detection**, immediately invalidating all refresh tokens for that user account.

### 2.4 Logout & Session Revocation
```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/logout (refresh_token) ->|
       |                                                |-- Mark refresh token as revoked
       |<- 204 No Content ------------------------------|
```

### 2.5 Multi-Account Isolation & Storage Purge (`FR-ACC-04`)
To prevent cross-account data leakage on shared browser environments:
- Upon receiving a successful logout response, the client must purge all credentials, drafts (`draft_*`), and cached DOM extracts from `chrome.storage.local`.
- Background service worker broadcasts `ACTION_PURGE_SESSION` across all active extension frames, redirecting any open Side Panels to `/login`.
