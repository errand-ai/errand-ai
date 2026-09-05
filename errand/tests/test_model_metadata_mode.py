"""Model mode — telling a chat model from an embedding model.

A plain `/v1/models` listing carries no indication of what a model is for, and a
name heuristic does not rescue it: a substring check for "embed" misses `bge-m3`
entirely. The registry errand already downloads records a `mode` per model, and
its alternate normalisation already reconciles Ollama-style `phi4` with the
registry's `phi-4` — so the registry is both the more correct source and the
smaller change.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from model_metadata import (
    batch_lookup_model_metadata,
    lookup_model_metadata,
    refresh_model_metadata_cache,
)
from models import ModelMetadataCache

_CACHE_TABLE_SQL = """
CREATE TABLE model_metadata_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_name TEXT NOT NULL UNIQUE,
    supports_reasoning BOOLEAN NOT NULL,
    max_output_tokens INTEGER,
    mode TEXT,
    source_keys TEXT NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_CACHE_TABLE_SQL))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _entry(name: str, mode: str | None, **kwargs) -> ModelMetadataCache:
    return ModelMetadataCache(
        normalized_name=name,
        supports_reasoning=kwargs.get("supports_reasoning", False),
        max_output_tokens=kwargs.get("max_output_tokens"),
        mode=mode,
        source_keys=[name],
        updated_at=datetime.now(timezone.utc),
    )


class TestModeLookup:
    async def test_chat_model_classified(self, db_session: AsyncSession):
        db_session.add(_entry("gpt-4o", "chat"))
        await db_session.commit()

        assert (await lookup_model_metadata("gpt-4o", db_session)).mode == "chat"

    async def test_embedding_model_classified(self, db_session: AsyncSession):
        db_session.add(_entry("text-embedding-3-small", "embedding"))
        await db_session.commit()

        result = await lookup_model_metadata("text-embedding-3-small", db_session)
        assert result.mode == "embedding"

    async def test_embedding_model_without_embed_in_its_name(self, db_session: AsyncSession):
        """The case a substring heuristic gets wrong."""
        db_session.add(_entry("bge-m3", "embedding"))
        await db_session.commit()

        assert (await lookup_model_metadata("bge-m3", db_session)).mode == "embedding"

    async def test_local_runtime_naming_reconciled(self, db_session: AsyncSession):
        """Ollama says `phi4`; the registry says `phi-4`."""
        db_session.add(_entry("phi-4", "chat"))
        await db_session.commit()

        assert (await lookup_model_metadata("phi4", db_session)).mode == "chat"

    async def test_provider_prefix_and_tag_stripped(self, db_session: AsyncSession):
        db_session.add(_entry("qwen3-embedding", "embedding"))
        await db_session.commit()

        result = await lookup_model_metadata("library/qwen3-embedding:8b", db_session)
        assert result.mode == "embedding"

    async def test_unknown_model_reports_unknown_without_error(self, db_session: AsyncSession):
        result = await lookup_model_metadata("nothing-like-this:7b", db_session)

        assert result.mode is None
        assert result.supports_reasoning is None

    async def test_prefix_match_carries_a_mode(self, db_session: AsyncSession):
        db_session.add(_entry("qwen3-30b-a3b", "chat"))
        await db_session.commit()

        assert (await lookup_model_metadata("qwen3:8b", db_session)).mode == "chat"

    async def test_prefix_match_with_disagreeing_modes_prefers_the_majority(self, db_session):
        db_session.add(_entry("qwen3-30b-a3b", "chat"))
        db_session.add(_entry("qwen3-coder-flash", "chat"))
        db_session.add(_entry("qwen3-embedding", "embedding"))
        await db_session.commit()

        assert (await lookup_model_metadata("qwen3:8b", db_session)).mode == "chat"


class TestBatchModeLookup:
    async def test_batch_resolves_mode_per_model(self, db_session: AsyncSession):
        db_session.add(_entry("gpt-4o", "chat"))
        db_session.add(_entry("text-embedding-3-small", "embedding"))
        await db_session.commit()

        result = await batch_lookup_model_metadata(
            ["gpt-4o", "text-embedding-3-small", "unheard-of"], db_session
        )

        assert result["gpt-4o"].mode == "chat"
        assert result["text-embedding-3-small"].mode == "embedding"
        assert result["unheard-of"].mode is None

    async def test_batch_applies_alternate_normalization(self, db_session: AsyncSession):
        db_session.add(_entry("phi-4", "chat"))
        await db_session.commit()

        result = await batch_lookup_model_metadata(["phi4"], db_session)
        assert result["phi4"].mode == "chat"


class TestRefreshExtractsMode:
    async def test_mode_is_extracted_from_the_registry(self, db_session: AsyncSession, monkeypatch):
        registry = {
            "sample_spec": {"mode": "chat"},
            "gpt-4o": {"mode": "chat", "max_output_tokens": 16384},
            "text-embedding-3-small": {"mode": "embedding"},
            "whisper-1": {"mode": "audio_transcription"},
        }
        await _refresh_with(registry, db_session, monkeypatch)

        assert (await lookup_model_metadata("gpt-4o", db_session)).mode == "chat"
        assert (await lookup_model_metadata("text-embedding-3-small", db_session)).mode == "embedding"
        assert (await lookup_model_metadata("whisper-1", db_session)).mode == "audio_transcription"

    async def test_missing_mode_stays_unknown(self, db_session: AsyncSession, monkeypatch):
        await _refresh_with({"mystery-model": {"max_output_tokens": 100}}, db_session, monkeypatch)

        assert (await lookup_model_metadata("mystery-model", db_session)).mode is None

    async def test_aggregated_entries_take_the_majority_mode(self, db_session, monkeypatch):
        """Many registry keys collapse onto one normalized name."""
        registry = {
            "openai/gpt-4o": {"mode": "chat"},
            "azure/gpt-4o": {"mode": "chat"},
            "weird/gpt-4o": {"mode": "completion"},
        }
        await _refresh_with(registry, db_session, monkeypatch)

        assert (await lookup_model_metadata("gpt-4o", db_session)).mode == "chat"

    async def test_a_refresh_updates_the_mode_of_an_existing_row(self, db_session, monkeypatch):
        db_session.add(_entry("gpt-4o", None))
        await db_session.commit()

        await _refresh_with({"gpt-4o": {"mode": "chat"}}, db_session, monkeypatch)

        assert (await lookup_model_metadata("gpt-4o", db_session)).mode == "chat"


async def _refresh_with(registry: dict, session: AsyncSession, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock, patch

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = registry
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("model_metadata.httpx.AsyncClient", return_value=ctx):
        await refresh_model_metadata_cache(session)
