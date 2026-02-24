"""Tests for internal credentials endpoint."""
import pytest
from httpx import AsyncClient

from models import PlatformCredential
from platforms.credentials import encrypt


@pytest.mark.asyncio
async def test_get_internal_credentials_success(client: AsyncClient, db_session, platform_credentials_table):
    """Test retrieving credentials when they exist."""
    # Create credentials in the database
    encrypted_data = encrypt({"api_key": "pplx-test-key-123"})
    cred = PlatformCredential(
        platform_id="perplexity",
        encrypted_data=encrypted_data,
        status="connected",
    )
    db_session.add(cred)
    await db_session.commit()

    # Request credentials via internal endpoint
    response = await client.get("/api/internal/credentials/perplexity")
    
    assert response.status_code == 200
    data = response.json()
    assert data == {"api_key": "pplx-test-key-123"}


@pytest.mark.asyncio
async def test_get_internal_credentials_not_configured(client: AsyncClient, db_session, platform_credentials_table):
    """Test response when no credentials are configured."""
    response = await client.get("/api/internal/credentials/perplexity")
    
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "No credentials configured"


@pytest.mark.asyncio
async def test_get_internal_credentials_unknown_platform(client: AsyncClient, db_session, platform_credentials_table):
    """Test response when platform doesn't exist in registry."""
    response = await client.get("/api/internal/credentials/nonexistent-platform")
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()
