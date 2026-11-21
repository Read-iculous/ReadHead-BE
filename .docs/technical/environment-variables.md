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
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Lifespan of Access Tokens (default: 1 hour) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` | Lifespan of Refresh Tokens (default: 30 days) |
| `ENCRYPTION_MASTER_KEY` | **Yes** | — | 32-byte base64-encoded key for AES-256-GCM vault encryption (primary key) |
| `ENCRYPTION_MASTER_KEYS`| No | `{}` | JSON dictionary of key versions for zero-downtime rotation e.g. `{"v1":"...", "v2":"..."}` |
| `CURRENT_KEY_VERSION` | No | `"v1"` | Active version prefix for encrypting new keys (`v1`, `v2`) |
| `GOOGLE_CLIENT_ID` | Conditional | `""` | Google OAuth2 Client ID for extension login |
| `GOOGLE_CLIENT_SECRET` | Conditional | `""` | Google OAuth2 Client Secret |
| `GITHUB_CLIENT_ID` | Conditional | `""` | GitHub OAuth2 Client ID |
| `GITHUB_CLIENT_SECRET` | Conditional | `""` | GitHub OAuth2 Client Secret |
| `CORS_ORIGINS` | No | `chrome-extension://*` | Comma-separated list of allowed origins (e.g., extension IDs, dev tools) |

## 2. `.env.example` Template
```ini
ENVIRONMENT=development
DEBUG=true
PORT=8000

# Database & Cache
DATABASE_URL=postgresql+asyncpg://readhead_user:readhead_pass@localhost:5432/readhead_db
REDIS_URL=redis://localhost:6379/0

# Security & JWT (Must be strictly distinct from ENCRYPTION_MASTER_KEY)
JWT_SECRET_KEY=change_this_to_a_super_secret_high_entropy_random_string_32_chars_min
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Symmetrical Key Vault (AES-256-GCM Master Keyring - Must NEVER match JWT_SECRET_KEY)
# Generate via: python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
ENCRYPTION_MASTER_KEY=your_base64_encoded_32_byte_master_encryption_key_here
CURRENT_KEY_VERSION=v1
# ENCRYPTION_MASTER_KEYS={"v1":"key1_base64...","v2":"key2_base64..."}

# OAuth Providers
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# CORS
CORS_ORIGINS=chrome-extension://*,http://localhost:3000,http://localhost:5173
```
