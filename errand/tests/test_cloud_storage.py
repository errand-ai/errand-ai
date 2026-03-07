"""Tests for cloud storage token refresh."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cloud_storage import refresh_token_if_needed
from models import PlatformCredential
from platforms.credentials import encrypt, decrypt
from tests.conftest import _create_tables


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _make_credentials(expired=False, no_refresh=False):
    creds = {
        "access_token": "old-access-token",
        "refresh_token": "" if no_refresh else "refresh-token-value",
        "expires_at": int(time.time()) - 600 if expired else int(time.time()) + 3600,
        "token_type": "Bearer",
        "user_email": "user@example.com",
        "user_name": "Test User",
    }
    return creds


@pytest.mark.anyio
async def test_token_still_valid(db_session, monkeypatch):
    """Valid token should be returned unchanged without HTTP call."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    creds = _make_credentials(expired=False)
    result = await refresh_token_if_needed("google_drive", creds, db_session)
    assert result is not None
    assert result["access_token"] == "old-access-token"


@pytest.mark.anyio
async def test_token_expired_refresh_success(db_session, monkeypatch):
    """Expired token should be refreshed via token endpoint."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    creds = _make_credentials(expired=True)

    # Store credential in DB
    db_session.add(PlatformCredential(
        platform_id="google_drive",
        encrypted_data=encrypt(creds),
        status="connected",
    ))
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(200, json={
        "access_token": "new-access-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    })
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        result = await refresh_token_if_needed("google_drive", creds, db_session)

    assert result is not None
    assert result["access_token"] == "new-access-token"
    assert result["expires_at"] > time.time()

    # Verify DB was updated
    db_result = await db_session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == "google_drive")
    )
    stored = decrypt(db_result.scalar_one().encrypted_data)
    assert stored["access_token"] == "new-access-token"


@pytest.mark.anyio
async def test_token_expired_refresh_rotates_refresh_token(db_session, monkeypatch):
    """When provider returns new refresh_token, it should be stored."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    creds = _make_credentials(expired=True)
    db_session.add(PlatformCredential(
        platform_id="google_drive",
        encrypted_data=encrypt(creds),
        status="connected",
    ))
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(200, json={
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
    })
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        result = await refresh_token_if_needed("google_drive", creds, db_session)

    assert result["refresh_token"] == "new-refresh"


@pytest.mark.anyio
async def test_revoked_refresh_token(db_session, monkeypatch):
    """Revoked refresh token returns None, doesn't block."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    creds = _make_credentials(expired=True)

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(400, json={"error": "invalid_grant"})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        result = await refresh_token_if_needed("google_drive", creds, db_session)

    assert result is None


@pytest.mark.anyio
async def test_no_refresh_token(db_session, monkeypatch):
    """Missing refresh token returns None."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    creds = _make_credentials(expired=True, no_refresh=True)
    result = await refresh_token_if_needed("google_drive", creds, db_session)
    assert result is None


@pytest.mark.anyio
async def test_no_client_credentials(db_session):
    """Missing client credentials returns None."""
    creds = _make_credentials(expired=True)
    result = await refresh_token_if_needed("google_drive", creds, db_session)
    assert result is None


@pytest.mark.anyio
async def test_microsoft_token_url(db_session, monkeypatch):
    """Microsoft uses tenant-specific token URL."""
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "my-tenant")

    creds = _make_credentials(expired=True)

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(200, json={
        "access_token": "ms-new-token",
        "expires_in": 3600,
    })
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        result = await refresh_token_if_needed("onedrive", creds, db_session)

    assert result is not None
    assert result["access_token"] == "ms-new-token"
    # Verify the correct token URL was used
    call_args = mock_client.post.call_args
    assert "my-tenant" in call_args[0][0]
