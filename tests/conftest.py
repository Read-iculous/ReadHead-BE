"""Offline defaults; opt-in integration runs supply disposable storage URLs."""

import base64
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "readhead-regression-only-signing-secret-0001")
os.environ.setdefault("ENCRYPTION_MASTER_KEY", base64.b64encode(b"x" * 32).decode())
os.environ.setdefault("CORS_ORIGINS", "chrome-extension://*,http://localhost:3000")
