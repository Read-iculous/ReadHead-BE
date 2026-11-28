# Environment Variables

## 1. Configuration Reference
All environment variables are loaded and validated at startup using Pydantic Settings (`app/core/config.py`).

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `ENVIRONMENT` | No | `development` | Environment mode (`development`, `staging`, `production`) |
| `DEBUG` | No | `true` | Enables verbose logging and exception stack traces |
| `PORT` | No | `8000` | Port for the Uvicorn server |
| `DATABASE_URL` | **Yes** | — | Async PostgreSQL connection string: `postgresql+asyncpg://user:pass@localhost:5432/readhead` |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL for rate limiting, token blacklist & cache |
| `JWT_SECRET_KEY` | **Yes** | — | High-entropy secret key used to sign Access and Refresh JWTs |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Lifespan of Access Tokens (default: 15 minutes) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` | Lifespan of Refresh Tokens (default: 30 days) |
| `ENCRYPTION_MASTER_KEY` | Conditional | — | 32-byte base64-encoded key for AES-256-GCM. Used as default single key in dev or fallback if `ENCRYPTION_MASTER_KEYS` is omitted |
| `ENCRYPTION_MASTER_KEYS`| No | `{}` | JSON dictionary of key versions e.g. `{"v1":"...", "v2":"..."}`. **Takes precedence over `ENCRYPTION_MASTER_KEY`** |
| `CURRENT_KEY_VERSION` | No | `"v1"` | Active version prefix used when encrypting new API keys |
| `GOOGLE_CLIENT_ID` | Conditional | `""` | Google OAuth2 Client ID for extension login |
| `GOOGLE_CLIENT_SECRET` | Conditional | `""` | Google OAuth2 Client Secret |
| `GITHUB_CLIENT_ID` | Conditional | `""` | GitHub OAuth2 Client ID |
| `GITHUB_CLIENT_SECRET` | Conditional | `""` | GitHub OAuth2 Client Secret |
| `CORS_ORIGINS` | No | `chrome-extension://*` | Comma-separated list of allowed origins (e.g., extension IDs, dev tools) |
| `RESEND_API_KEY` | Conditional | `""` | Resend API key for transactional email delivery (email verification, password reset). **Required when email verification is enabled**; with an empty key, registration still succeeds but `verification_email_sent` is `false` and verification cannot complete |
| `MAIL_FROM_ADDRESS` | Conditional | `""` | Verified sender address for all Resend email (e.g. `no-reply@readhead.io`); must belong to a domain with SPF/DKIM/DMARC configured (see runbook in `.docs/development/commands.md`) |
| `APP_BASE_URL` | Conditional | `""` | Public backend base URL used to build verification and password-reset links inside emails (e.g. `https://api.readhead.io`) |
| `VERIFICATION_TOKEN_TTL_HOURS` | No | `24` | Lifetime of email verification tokens; expired tokens return `400 VERIFICATION_TOKEN_EXPIRED` |
| `PASSWORD_RESET_TOKEN_TTL_MINUTES` | No | `60` | Lifetime of password reset tokens; expired tokens return `400 RESET_TOKEN_EXPIRED` |
| `VERIFICATION_RESEND_LIMIT_PER_HOUR` | No | `3` | Maximum verification email resends per email address per hour (per-email limit; the shared `AUTH_REQUESTS_PER_MINUTE` auth bucket still applies) |

| `POSTGRES_PORT` | No | `5432` | Docker Compose host port; match the port in `DATABASE_URL` |
| `REDIS_PORT` | No | `6379` | Docker Compose host port; match the port in `REDIS_URL` |
| `AUTH_REQUESTS_PER_MINUTE` | No | `20` | Per-client auth fixed-window limit |
| `AI_REQUESTS_PER_MINUTE` | No | `30` | Per-identity AI/quiz initial request limit |
| `API_REQUESTS_PER_MINUTE` | No | `120` | Per-identity general API fixed-window limit |

### Keyring Startup Validation and Rotation
- A non-empty `ENCRYPTION_MASTER_KEYS` takes precedence; otherwise map `ENCRYPTION_MASTER_KEY` to `CURRENT_KEY_VERSION` as the single-key development fallback.
- Fail startup if the effective keyring is empty, a key does not decode to 32 bytes, `CURRENT_KEY_VERSION` is absent, or a signing secret is reused as any effective encryption key. Validate the effective keyring rather than only the ignored single-key variable.
- Follow `.docs/development/commands.md` for writer-first rotation. Every process must load both versions before any writer switches; remove an old live key only after all writers and records have migrated.

### Resend Email Delivery Notes
- `RESEND_API_KEY` and `MAIL_FROM_ADDRESS` must both be set for verification/reset emails to send. Emails are delivered through Resend's HTTPS API; no SMTP connection is used.
- **`@resend.dev` sender limitation**: The shared test sender `noreply@resend.dev` can only deliver to the email address of the Resend account that owns the API key — it cannot reach arbitrary users. It is suitable for local development/self-testing only; **production must verify a dedicated sending domain** (SPF, DKIM and DMARC) and switch `MAIL_FROM_ADDRESS` to an address on it.
- Before sending from production, configure the sending domain in Resend and publish **SPF, DKIM and DMARC** DNS records for it (see the runbook in `.docs/development/commands.md`). Unverified domains cause bounces/spam classification.
- The Resend API key itself lives only in `.env` and is never documented in any `.docs/` file.
- The resend rate limit (`VERIFICATION_RESEND_LIMIT_PER_HOUR`, default 3/hour per email address) may alternatively be hard-coded; the environment variable is the recommended configuration point.

## 2. `.env.example` Template
```ini
# ==============================================================================
# ReadHead-BE — Environment Variables Configuration Template
# ==============================================================================
# Copy this file to .env and fill in the actual values:
#   cp .env.example .env

# Server & Runtime
ENVIRONMENT=development
DEBUG=true
PORT=8000

# Optional host ports for Docker Compose (keep URLs below in sync)
POSTGRES_PORT=5432
REDIS_PORT=6379

# Database & Cache
DATABASE_URL=postgresql+asyncpg://readhead_user:readhead_password@localhost:5432/readhead_db
REDIS_URL=redis://localhost:6379/0

# Security & JWT Token Authentication
# Generate a secret: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=change_this_to_a_super_secret_high_entropy_random_string_32_chars_min
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

# Symmetrical Key Vault (AES-256-GCM Master Key for User API Keys)
# Generate a key: python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
ENCRYPTION_MASTER_KEY=your_base64_encoded_32_byte_master_encryption_key_here
CURRENT_KEY_VERSION=v1
# ENCRYPTION_MASTER_KEYS={"v1":"key1_base64...","v2":"key2_base64..."}

# OAuth2 Authentication Providers
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# CORS Settings (Accepts Chrome extension origins and local dev tools)
CORS_ORIGINS=chrome-extension://*,http://localhost:3000,http://localhost:5173,http://localhost:8000

# Fixed-window per-minute request limits; Redis outages use process-local counters
AUTH_REQUESTS_PER_MINUTE=20
AI_REQUESTS_PER_MINUTE=30
API_REQUESTS_PER_MINUTE=120

# Transactional Email (Resend) — required for email verification & password reset
# Get an API key at https://resend.com; the key itself goes here only, never in docs.
# noreply@resend.dev is the shared test sender: it can ONLY deliver to the email of the
# Resend account owning the key. Production must switch to a verified custom domain.
RESEND_API_KEY=
MAIL_FROM_ADDRESS=noreply@resend.dev
APP_BASE_URL=http://localhost:8000
VERIFICATION_TOKEN_TTL_HOURS=24
PASSWORD_RESET_TOKEN_TTL_MINUTES=60
VERIFICATION_RESEND_LIMIT_PER_HOUR=3
```
