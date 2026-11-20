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
| `ENCRYPTION_MASTER_KEY` | **Yes** | — | 32-byte URL-safe base64-encoded key for AES-256 key vault encryption |
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

# Security & JWT
JWT_SECRET_KEY=change_this_to_a_super_secret_high_entropy_random_string_32_chars_min
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Symmetrical Key Vault (AES-256 Master Key)
# Generate via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_MASTER_KEY=your_base64_encoded_32_byte_master_encryption_key_here

# OAuth Providers
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# CORS
CORS_ORIGINS=chrome-extension://*,http://localhost:3000,http://localhost:5173
```
