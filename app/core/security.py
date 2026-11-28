"""Password hashing, JWT encoding and AES-256-GCM keyring encryption."""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import AppException

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def utcnow() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    """Hash a validated password with salted bcrypt."""
    return password_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Compare a password against its bcrypt hash."""
    return password_context.verify(password, hashed)


def token_hash(token: str) -> str:
    """Return a non-reversible refresh-token lookup hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def encode_token(
    user_id: UUID, sid: UUID, kind: str, expires: datetime, jti: UUID | None = None
) -> str:
    """Issue a signed, typed JWT bound to one auth session."""
    cfg = get_settings()
    return jwt.encode(
        dict(
            sub=str(user_id),
            sid=str(sid),
            jti=str(jti or uuid4()),
            type=kind,
            iss="readhead",
            iat=utcnow(),
            exp=expires,
        ),
        cfg.jwt_secret_key.get_secret_value(),
        algorithm=cfg.jwt_algorithm,
    )


def decode_token(token: str, kind: str) -> dict:
    """Validate signature, required claims, issuer, expiry and token type."""
    cfg = get_settings()
    try:
        claims = jwt.decode(
            token,
            cfg.jwt_secret_key.get_secret_value(),
            algorithms=[cfg.jwt_algorithm],
            issuer="readhead",
            options=dict(
                leeway=60,
                require_exp=True,
                require_sub=True,
                require_iat=True,
                require_jti=True,
            ),
        )
        if claims.get("type") != kind:
            raise ValueError("wrong token type")
        for name in ("sub", "sid", "jti"):
            UUID(claims[name])
        return claims
    except ExpiredSignatureError as exc:
        code = "REFRESH_TOKEN_EXPIRED" if kind == "refresh" else "TOKEN_EXPIRED"
        raise AppException(401, code, "Token has expired") from exc
    except (JWTError, ValueError, KeyError, TypeError) as exc:
        raise AppException(
            401, "TOKEN_INVALID", "Invalid authentication token"
        ) from exc


def make_pair(user_id: UUID, sid: UUID, refresh_id: UUID) -> tuple[dict, datetime]:
    """Issue a token pair and return its refresh expiry."""
    cfg, now = get_settings(), utcnow()
    expiry = now + timedelta(days=cfg.refresh_token_expire_days)
    seconds = cfg.access_token_expire_minutes * 60
    return (
        dict(
            access_token=encode_token(
                user_id, sid, "access", now + timedelta(seconds=seconds)
            ),
            refresh_token=encode_token(user_id, sid, "refresh", expiry, refresh_id),
            token_type="bearer",
            expires_in=seconds,
        ),
        expiry,
    )


def encrypt_secret(plaintext: str, version: str | None = None) -> str:
    """Encrypt with a fresh nonce and a versioned authentication tag."""
    cfg = get_settings()
    version = version or cfg.current_key_version
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(cfg.keyring[version]).encrypt(
        nonce, plaintext.encode(), version.encode()
    )

    def enc(value: bytes) -> str:
        return base64.b64encode(value).decode()

    return ":".join((version, enc(nonce), enc(encrypted[:-16]), enc(encrypted[-16:])))


def decrypt_secret(ciphertext: str) -> str:
    """Authenticate and decrypt a versioned vault value."""
    try:
        version, nonce, body, tag = ciphertext.split(":")
        key = get_settings().keyring[version]

        def dec(value: str) -> bytes:
            return base64.b64decode(value, validate=True)

        return (
            AESGCM(key)
            .decrypt(dec(nonce), dec(body) + dec(tag), version.encode())
            .decode()
        )
    except (ValueError, KeyError, InvalidTag, UnicodeError) as exc:
        raise AppException(
            500, "ENCRYPTION_ERROR", "Unable to decrypt stored key"
        ) from exc
