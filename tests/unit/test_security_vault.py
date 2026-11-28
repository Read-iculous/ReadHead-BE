"""Direct vault coverage: crypto roundtrip, tamper protection and rotation CAS."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cli.rotate_keys import rotate
from app.core.exceptions import AppException
from app.core.security import decrypt_secret, encrypt_secret

SECRET = "sk-vault-unit-test-credential"


def test_roundtrip_and_fresh_nonce() -> None:
    first, second = encrypt_secret(SECRET), encrypt_secret(SECRET)
    assert first != second, "each encryption must use a fresh nonce"
    assert first.startswith("v1:") and len(first.split(":")) == 4
    assert decrypt_secret(first) == SECRET
    assert SECRET not in first


def test_tampered_ciphertext_is_rejected() -> None:
    version, nonce, body, tag = encrypt_secret(SECRET).split(":")
    raw = bytearray(base64.b64decode(body))
    raw[0] ^= 1
    tampered = ":".join((version, nonce, base64.b64encode(bytes(raw)).decode(), tag))
    with pytest.raises(AppException) as exc:
        decrypt_secret(tampered)
    assert exc.value.code == "ENCRYPTION_ERROR"
    assert SECRET not in str(exc.value)


def test_wrong_version_label_is_rejected() -> None:
    version, nonce, body, tag = encrypt_secret(SECRET).split(":")
    swapped = ":".join(("v9", nonce, body, tag))
    with pytest.raises(AppException) as exc:
        decrypt_secret(swapped)
    assert exc.value.code == "ENCRYPTION_ERROR"


def test_keyring_rejects_duplicate_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings

    same = base64.b64encode(b"q" * 32).decode()
    with pytest.raises(ValueError, match="distinct key material"):
        Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            jwt_secret_key="unit-test-signing-secret-0000000000000001",
            encryption_master_keys={"v1": same, "v2": same},
            current_key_version="v2",
            _env_file=None,
        )


@pytest.mark.asyncio
async def test_rotation_migrates_and_skips_undecryptable_rows() -> None:
    good_cipher = encrypt_secret(SECRET, "v1")
    broken_cipher = "v1:" + "damaged" * 6
    rows = [
        MagicMock(id="00000000-0000-0000-0000-000000000001", encrypted_key=good_cipher),
        MagicMock(
            id="00000000-0000-0000-0000-000000000002", encrypted_key=broken_cipher
        ),
    ]
    writes: list[dict] = []

    def fake_select(*args, **kwargs):
        context = MagicMock()

        def where(*a, **k):
            return context

        context.where = where
        context.order_by = MagicMock(return_value=context)
        context.limit = MagicMock(return_value=MagicMock(__call__=None))
        return context

    async def fake_execute(query):
        if hasattr(query, "values"):
            index = len(writes)
            writes.append(query)
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(
                return_value=None if index else rows[0].id
            )
            return result
        remaining, fake_execute.pending = fake_execute.pending, []
        return MagicMock(all=MagicMock(return_value=remaining))

    fake_execute.pending = rows

    with (
        patch("app.cli.rotate_keys.transaction") as txn,
        patch("app.cli.rotate_keys.engine") as engine_mock,
    ):
        engine_mock.dispose = AsyncMock()
        session = MagicMock()
        session.execute = AsyncMock(side_effect=fake_execute)
        txn.return_value.__aenter__ = AsyncMock(return_value=session)
        txn.return_value.__aexit__ = AsyncMock(return_value=None)
        cfg = MagicMock()
        cfg.keyring = {"v1": b"a" * 32, "v2": b"b" * 32}
        cfg.current_key_version = "v2"
        with (
            patch("app.cli.rotate_keys.get_settings", return_value=cfg),
            patch("app.core.security.get_settings", return_value=cfg),
            patch("app.cli.rotate_keys.encrypt_secret", wraps=encrypt_secret),
            patch(
                "app.cli.rotate_keys.decrypt_secret",
                side_effect=lambda cipher: (
                    SECRET
                    if cipher == good_cipher
                    else (_ for _ in ()).throw(
                        AppException(500, "ENCRYPTION_ERROR", "undecryptable")
                    )
                ),
            ),
        ):
            await rotate("v1", "v2")

    assert len(writes) == 1, "only the decryptable row is migrated"
    assert writes[0].compile().params["encrypted_key_1"] == good_cipher
