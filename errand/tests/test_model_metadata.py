import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from model_metadata import (
    _alt_normalize,
    is_cache_stale,
    lookup_model_metadata,
    normalize_model_name,
    refresh_model_metadata_cache,
)
from models import ModelMetadataCache

_CACHE_TABLE_SQL = """
CREATE TABLE model_metadata_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_name TEXT NOT NULL UNIQUE,
    supports_reasoning BOOLEAN NOT NULL,
    max_output_tokens INTEGER,
    source_keys TEXT NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_CACHE_TABLE_SQL))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# --- Normalization tests ---


class TestNormalizeModelName:
    def test_ollama_style_with_tag(self):
        assert normalize_model_name("deepseek-r1:8b") == "deepseek-r1"

    def test_ollama_style_latest(self):
        assert normalize_model_name("deepseek-r1:latest") == "deepseek-r1"

    def test_provider_prefixed(self):
        assert normalize_model_name("deepseek/deepseek-r1") == "deepseek-r1"

    def test_deep_provider_path(self):
        assert normalize_model_name(
            "fireworks_ai/accounts/fireworks/models/deepseek-r1"
        ) == "deepseek-r1"

    def test_vertex_ai_at_suffix(self):
        assert normalize_model_name(
            "vertex_ai/claude-3-7-sonnet@20250219"
        ) == "claude-3-7-sonnet"

    def test_plain_name(self):
        assert normalize_model_name("mistral") == "mistral"

    def test_uppercase_normalized(self):
        assert normalize_model_name("DeepSeek-R1:8B") == "deepseek-r1"

    def test_colon_and_path_combined(self):
        assert normalize_model_name("ollama/deepseek-r1:70b") == "deepseek-r1"


class TestAltNormalize:
    def test_inserts_hyphen_between_letters_and_digits(self):
        assert _alt_normalize("phi4-mini-reasoning") == "phi-4-mini-reasoning"

    def test_llama_style(self):
        assert _alt_normalize("llama3.2-vision") == "llama-3.2-vision"

    def test_granite_style(self):
        assert _alt_normalize("granite3.2-vision") == "granite-3.2-vision"

    def test_returns_none_when_no_change(self):
        assert _alt_normalize("deepseek-r1") is None

    def test_already_hyphenated(self):
        assert _alt_normalize("phi-4-reasoning") is None


# --- Lookup tests ---


class TestLookupModelMetadata:
    async def test_exact_match(self, db_session: AsyncSession):
        db_session.add(ModelMetadataCache(
            normalized_name="deepseek-r1",
            supports_reasoning=True,
            max_output_tokens=8192,
            source_keys=["deepseek/deepseek-r1"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        result = await lookup_model_metadata("deepseek-r1:8b", db_session)
        assert result.supports_reasoning is True
        assert result.max_output_tokens == 8192

    async def test_prefix_match(self, db_session: AsyncSession):
        db_session.add(ModelMetadataCache(
            normalized_name="qwen3-30b-a3b",
            supports_reasoning=True,
            max_output_tokens=4096,
            source_keys=["openrouter/qwen3-30b-a3b"],
            updated_at=datetime.now(timezone.utc),
        ))
        db_session.add(ModelMetadataCache(
            normalized_name="qwen3-coder-flash",
            supports_reasoning=False,
            max_output_tokens=8192,
            source_keys=["openrouter/qwen3-coder-flash"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        result = await lookup_model_metadata("qwen3:8b", db_session)
        assert result.supports_reasoning is True
        assert result.max_output_tokens == 4096  # min across matches

    async def test_no_match(self, db_session: AsyncSession):
        result = await lookup_model_metadata("totally-unknown:7b", db_session)
        assert result.supports_reasoning is None
        assert result.max_output_tokens is None

    async def test_reasoning_flag_aggregation(self, db_session: AsyncSession):
        """If any prefix-matched entry has reasoning, result is True."""
        db_session.add(ModelMetadataCache(
            normalized_name="phi-4-reasoning",
            supports_reasoning=True,
            max_output_tokens=4096,
            source_keys=["phi-4-reasoning"],
            updated_at=datetime.now(timezone.utc),
        ))
        db_session.add(ModelMetadataCache(
            normalized_name="phi-4-mini",
            supports_reasoning=False,
            max_output_tokens=8192,
            source_keys=["phi-4-mini"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        result = await lookup_model_metadata("phi-4:latest", db_session)
        # phi-4 prefix matches phi-4-reasoning and phi-4-mini
        assert result.supports_reasoning is True
        assert result.max_output_tokens == 4096

    async def test_alt_normalization_match(self, db_session: AsyncSession):
        """Lookup falls back to alt normalization (phi4 -> phi-4)."""
        db_session.add(ModelMetadataCache(
            normalized_name="phi-4-mini-reasoning",
            supports_reasoning=True,
            max_output_tokens=4096,
            source_keys=["azure_ai/Phi-4-mini-reasoning"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        # phi4-mini-reasoning normalizes to "phi4-mini-reasoning" (no match)
        # alt normalization: "phi-4-mini-reasoning" (exact match!)
        result = await lookup_model_metadata("phi4-mini-reasoning:3.8b", db_session)
        assert result.supports_reasoning is True
        assert result.max_output_tokens == 4096

    async def test_alt_normalization_prefix_match(self, db_session: AsyncSession):
        """Alt normalization also tries prefix matching."""
        db_session.add(ModelMetadataCache(
            normalized_name="granite-3.2-8b",
            supports_reasoning=False,
            max_output_tokens=8192,
            source_keys=["some/granite-3.2-8b"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        # granite3.2 -> alt: granite-3.2 -> prefix matches granite-3.2-*
        result = await lookup_model_metadata("granite3.2:latest", db_session)
        assert result.supports_reasoning is False
        assert result.max_output_tokens == 8192

    async def test_exact_match_preferred_over_prefix(self, db_session: AsyncSession):
        """Exact match should be returned even if prefix matches exist."""
        db_session.add(ModelMetadataCache(
            normalized_name="llama3",
            supports_reasoning=False,
            max_output_tokens=4096,
            source_keys=["llama3"],
            updated_at=datetime.now(timezone.utc),
        ))
        db_session.add(ModelMetadataCache(
            normalized_name="llama3-reasoning",
            supports_reasoning=True,
            max_output_tokens=8192,
            source_keys=["llama3-reasoning"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        result = await lookup_model_metadata("llama3:8b", db_session)
        # Exact match on "llama3" should win
        assert result.supports_reasoning is False
        assert result.max_output_tokens == 4096


# --- Registry fetch tests ---


def _make_registry(**models):
    """Build a minimal registry dict for testing."""
    return {k: v for k, v in models.items()}


class TestRefreshModelMetadataCache:
    async def test_successful_fetch_and_parse(self, db_session: AsyncSession):
        registry = _make_registry(**{
            "deepseek/deepseek-r1": {
                "supports_reasoning": True,
                "max_output_tokens": 8192,
                "litellm_provider": "deepseek",
            },
            "ollama/llama3": {
                "supports_reasoning": False,
                "max_output_tokens": 8192,
                "litellm_provider": "ollama",
            },
        })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = registry
        mock_response.raise_for_status = MagicMock()

        with patch("model_metadata.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            count = await refresh_model_metadata_cache(db_session)

        assert count == 2
        result = await lookup_model_metadata("deepseek-r1:8b", db_session)
        assert result.supports_reasoning is True
        assert result.max_output_tokens == 8192

    async def test_network_error_returns_zero(self, db_session: AsyncSession):
        with patch("model_metadata.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            count = await refresh_model_metadata_cache(db_session)

        assert count == 0

    async def test_invalid_json_returns_zero(self, db_session: AsyncSession):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("bad", "", 0)
        mock_response.raise_for_status = MagicMock()

        with patch("model_metadata.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            count = await refresh_model_metadata_cache(db_session)

        assert count == 0

    async def test_reasoning_aggregation_across_providers(self, db_session: AsyncSession):
        """If one provider says reasoning=true and another says false, result is true."""
        registry = _make_registry(**{
            "deepseek/deepseek-r1": {
                "supports_reasoning": True,
                "max_output_tokens": 8192,
            },
            "fireworks_ai/accounts/fireworks/models/deepseek-r1": {
                "supports_reasoning": False,
                "max_output_tokens": 20480,
            },
        })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = registry
        mock_response.raise_for_status = MagicMock()

        with patch("model_metadata.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await refresh_model_metadata_cache(db_session)

        result = await lookup_model_metadata("deepseek-r1", db_session)
        assert result.supports_reasoning is True
        # Conservative: min across providers
        assert result.max_output_tokens == 8192

    async def test_sample_spec_excluded(self, db_session: AsyncSession):
        registry = {
            "sample_spec": {"supports_reasoning": True, "max_output_tokens": 999},
            "real-model": {"supports_reasoning": False, "max_output_tokens": 4096},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = registry
        mock_response.raise_for_status = MagicMock()

        with patch("model_metadata.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            count = await refresh_model_metadata_cache(db_session)

        assert count == 1  # sample_spec excluded


# --- Cache staleness tests ---


class TestIsCacheStale:
    async def test_empty_cache_is_stale(self, db_session: AsyncSession):
        assert await is_cache_stale(db_session) is True

    async def test_fresh_cache_not_stale(self, db_session: AsyncSession):
        db_session.add(ModelMetadataCache(
            normalized_name="test",
            supports_reasoning=False,
            max_output_tokens=4096,
            source_keys=["test"],
            updated_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()
        assert await is_cache_stale(db_session) is False

    async def test_old_cache_is_stale(self, db_session: AsyncSession):
        db_session.add(ModelMetadataCache(
            normalized_name="test",
            supports_reasoning=False,
            max_output_tokens=4096,
            source_keys=["test"],
            updated_at=datetime.now(timezone.utc) - timedelta(days=8),
        ))
        await db_session.commit()
        assert await is_cache_stale(db_session) is True

    async def test_custom_max_age(self, db_session: AsyncSession):
        db_session.add(ModelMetadataCache(
            normalized_name="test",
            supports_reasoning=False,
            max_output_tokens=4096,
            source_keys=["test"],
            updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ))
        await db_session.commit()
        # 2 hours old, max_age 1 hour → stale
        assert await is_cache_stale(db_session, max_age_seconds=3600) is True
        # 2 hours old, max_age 3 hours → not stale
        assert await is_cache_stale(db_session, max_age_seconds=10800) is False
