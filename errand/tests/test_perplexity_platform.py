"""Tests for PerplexityPlatform."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from platforms.base import PlatformCapability
from platforms.perplexity import PerplexityPlatform


def test_perplexity_info():
    perplexity = PerplexityPlatform()
    info = perplexity.info()
    assert info.id == "perplexity"
    assert info.label == "Perplexity"
    assert PlatformCapability.TOOL_PROVIDER in info.capabilities
    schema_keys = [f["key"] for f in info.credential_schema]
    assert schema_keys == ["api_key"]
    # Verify schema field structure
    for field in info.credential_schema:
        assert field["key"] == "api_key"
        assert field["type"] == "password"
        assert field["required"] is True


@pytest.mark.asyncio
async def test_perplexity_verify_credentials_success():
    perplexity = PerplexityPlatform()
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
    
    with patch("platforms.perplexity.httpx.AsyncClient", return_value=mock_client):
        result = await perplexity.verify_credentials({"api_key": "pplx-valid-key"})
    
    assert result is True


@pytest.mark.asyncio
async def test_perplexity_verify_credentials_invalid_key():
    perplexity = PerplexityPlatform()
    
    mock_response = MagicMock()
    mock_response.status_code = 401
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
    
    with patch("platforms.perplexity.httpx.AsyncClient", return_value=mock_client):
        result = await perplexity.verify_credentials({"api_key": "invalid-key"})
    
    assert result is False


@pytest.mark.asyncio
async def test_perplexity_verify_credentials_no_key():
    perplexity = PerplexityPlatform()
    result = await perplexity.verify_credentials({})
    assert result is False


@pytest.mark.asyncio
async def test_perplexity_verify_credentials_api_error():
    perplexity = PerplexityPlatform()
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network error"))
    
    with patch("platforms.perplexity.httpx.AsyncClient", return_value=mock_client):
        result = await perplexity.verify_credentials({"api_key": "pplx-key"})
    
    assert result is False
