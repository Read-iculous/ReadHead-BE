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

### 2.3 Token Refresh Flow
When an API request returns `401 Unauthorized` with error code `TOKEN_EXPIRED`:
```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/refresh (refresh_token) >|
       |                                                |-- Verify token signature
       |                                                |-- Check DB if token revoked
       |                                                |-- Issue new access_token
       |<- 200 OK (new access_token, refresh_token) ----|
```

### 2.4 Logout & Session Revocation
```
Extension Client                                  ReadHead-BE
       |                                                |
       |----- POST /api/v1/auth/logout (refresh_token) ->|
       |                                                |-- Mark refresh token as revoked
       |<- 204 No Content ------------------------------|
```
