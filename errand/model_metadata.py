"""Model metadata registry — fetch, cache, and look up model capabilities."""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import ModelMetadataCache

logger = logging.getLogger(__name__)

REGISTRY_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
REGISTRY_FETCH_TIMEOUT = 30.0
REFRESH_INTERVAL_DAYS = 7
REFRESH_DEBOUNCE_SECONDS = 3600  # 1 hour


@dataclass
class ModelMetadata:
    supports_reasoning: bool | None
    max_output_tokens: int | None


def normalize_model_name(name: str) -> str:
    """Normalize a model name for registry lookup.

    Strips provider prefixes, colon tags, @ suffixes, and lowercases.
    """
    # Take last path segment: "deepseek/deepseek-r1" -> "deepseek-r1"
    base = name.split("/")[-1]
    # Strip colon suffix: "deepseek-r1:8b" -> "deepseek-r1"
    base = base.split(":")[0]
    # Strip @ suffix: "claude-3-7-sonnet@20250219" -> "claude-3-7-sonnet"
    base = base.split("@")[0]
    return base.lower()


def _alt_normalize(name: str) -> str | None:
    """Generate an alternate normalization by inserting hyphens between letters and digits.

    Ollama often uses names like 'phi4', 'llama3.2', 'granite3.2' while the
    LiteLLM registry uses 'phi-4', 'llama-3.2', 'granite-3.2'.
    Returns None if the alternate is the same as the original.
    """
    import re
    # Only insert hyphen when not already preceded by a hyphen
    # e.g. "phi4" -> "phi-4" but "deepseek-r1" stays unchanged
    alt = re.sub(r"(?<!-)([a-z])(\d)", r"\1-\2", name)
    return alt if alt != name else None


async def lookup_model_metadata(
    model_name: str, session: AsyncSession
) -> ModelMetadata:
    """Look up model metadata from the cache using multi-pass matching.

    Pass 1: exact match on normalized name.
    Pass 2: prefix match — find entries whose normalized_name starts with
    the input followed by '-' or '.'.
    Pass 3: retry passes 1-2 with alternate normalization (insert hyphens
    between letters and digits, e.g. 'phi4' -> 'phi-4').
    """
    normalized = normalize_model_name(model_name)

    result = await _lookup_with_name(normalized, session)
    if result is not None:
        return result

    # Pass 3: try alternate normalization (phi4 -> phi-4, llama3.2 -> llama-3.2)
    alt = _alt_normalize(normalized)
    if alt is not None:
        result = await _lookup_with_name(alt, session)
        if result is not None:
            return result

    return ModelMetadata(supports_reasoning=None, max_output_tokens=None)


async def _lookup_with_name(
    normalized: str, session: AsyncSession
) -> ModelMetadata | None:
    """Try exact then prefix match for a single normalized name."""
    # Exact match
    result = await session.execute(
        select(ModelMetadataCache).where(
            ModelMetadataCache.normalized_name == normalized
        )
    )
    exact = result.scalar_one_or_none()
    if exact is not None:
        return ModelMetadata(
            supports_reasoning=exact.supports_reasoning,
            max_output_tokens=exact.max_output_tokens,
        )

    # Prefix match
    result = await session.execute(
        select(ModelMetadataCache).where(
            (ModelMetadataCache.normalized_name.like(f"{normalized}-%"))
            | (ModelMetadataCache.normalized_name.like(f"{normalized}.%"))
        )
    )
    prefix_matches = result.scalars().all()
    if prefix_matches:
        any_reasoning = any(m.supports_reasoning for m in prefix_matches)
        output_tokens = [
            m.max_output_tokens
            for m in prefix_matches
            if m.max_output_tokens is not None
        ]
        return ModelMetadata(
            supports_reasoning=any_reasoning,
            max_output_tokens=min(output_tokens) if output_tokens else None,
        )

    return None


async def refresh_model_metadata_cache(session: AsyncSession) -> int:
    """Fetch the LiteLLM registry and upsert normalized entries into the cache.

    Returns the number of entries upserted, or 0 on failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(REGISTRY_URL, timeout=REGISTRY_FETCH_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.warning("Failed to fetch model metadata registry (HTTP error)")
        return 0
    except Exception:
        logger.warning("Failed to fetch model metadata registry", exc_info=True)
        return 0

    if not isinstance(data, dict):
        logger.warning("Model metadata registry is not a JSON object")
        return 0

    # Aggregate by normalized name
    aggregated: dict[str, dict] = defaultdict(
        lambda: {"reasoning_votes": 0, "max_outputs": [], "source_keys": []}
    )
    for key, value in data.items():
        if key == "sample_spec" or not isinstance(value, dict):
            continue
        normalized = normalize_model_name(key)
        entry = aggregated[normalized]
        entry["source_keys"].append(key)
        if value.get("supports_reasoning"):
            entry["reasoning_votes"] += 1
        max_out = value.get("max_output_tokens")
        if isinstance(max_out, int) and max_out > 0:
            entry["max_outputs"].append(max_out)

    # Upsert into DB
    now = datetime.now(timezone.utc)
    count = 0
    for normalized, agg in aggregated.items():
        supports_reasoning = agg["reasoning_votes"] > 0
        max_output = min(agg["max_outputs"]) if agg["max_outputs"] else None

        result = await session.execute(
            select(ModelMetadataCache).where(
                ModelMetadataCache.normalized_name == normalized
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.supports_reasoning = supports_reasoning
            existing.max_output_tokens = max_output
            existing.source_keys = agg["source_keys"]
            existing.updated_at = now
        else:
            try:
                session.add(
                    ModelMetadataCache(
                        normalized_name=normalized,
                        supports_reasoning=supports_reasoning,
                        max_output_tokens=max_output,
                        source_keys=agg["source_keys"],
                        updated_at=now,
                    )
                )
                await session.flush()
            except IntegrityError:
                await session.rollback()
                # Another refresh already inserted this row — update it
                result = await session.execute(
                    select(ModelMetadataCache).where(
                        ModelMetadataCache.normalized_name == normalized
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.supports_reasoning = supports_reasoning
                    existing.max_output_tokens = max_output
                    existing.source_keys = agg["source_keys"]
                    existing.updated_at = now
        count += 1

    await session.commit()
    logger.info("Model metadata cache refreshed: %d entries", count)
    return count


async def is_cache_stale(session: AsyncSession, max_age_seconds: int | None = None) -> bool:
    """Check if the cache is empty or older than max_age_seconds."""
    if max_age_seconds is None:
        max_age_seconds = REFRESH_INTERVAL_DAYS * 86400

    result = await session.execute(
        select(func.max(ModelMetadataCache.updated_at))
    )
    latest = result.scalar_one_or_none()
    if latest is None:
        return True
    # Handle naive datetimes (e.g. from SQLite) by assuming UTC
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - latest).total_seconds()
    return age > max_age_seconds


async def batch_lookup_model_metadata(
    model_names: list[str], session: AsyncSession
) -> dict[str, ModelMetadata]:
    """Look up metadata for multiple models using a single DB query.

    Pre-loads all cache entries into memory, then matches each model name
    using the same multi-pass logic as lookup_model_metadata.
    """
    # Load all cache entries in one query
    result = await session.execute(select(ModelMetadataCache))
    all_entries = result.scalars().all()

    # Build index by normalized name
    by_name: dict[str, ModelMetadataCache] = {}
    for entry in all_entries:
        by_name[entry.normalized_name] = entry

    def _match(normalized: str) -> ModelMetadata | None:
        # Exact match
        exact = by_name.get(normalized)
        if exact is not None:
            return ModelMetadata(
                supports_reasoning=exact.supports_reasoning,
                max_output_tokens=exact.max_output_tokens,
            )
        # Prefix match
        prefix_matches = [
            e for name, e in by_name.items()
            if name.startswith(f"{normalized}-") or name.startswith(f"{normalized}.")
        ]
        if prefix_matches:
            any_reasoning = any(m.supports_reasoning for m in prefix_matches)
            output_tokens = [
                m.max_output_tokens for m in prefix_matches
                if m.max_output_tokens is not None
            ]
            return ModelMetadata(
                supports_reasoning=any_reasoning,
                max_output_tokens=min(output_tokens) if output_tokens else None,
            )
        return None

    results: dict[str, ModelMetadata] = {}
    for model_name in model_names:
        normalized = normalize_model_name(model_name)
        meta = _match(normalized)
        if meta is None:
            alt = _alt_normalize(normalized)
            if alt is not None:
                meta = _match(alt)
        if meta is None:
            meta = ModelMetadata(supports_reasoning=None, max_output_tokens=None)
        results[model_name] = meta

    return results


async def run_periodic_refresh(session_factory) -> None:
    """Background loop that checks staleness hourly and refreshes when needed."""
    while True:
        await asyncio.sleep(3600)  # check every hour
        try:
            async with session_factory() as session:
                if await is_cache_stale(session):
                    await refresh_model_metadata_cache(session)
        except Exception:
            logger.exception("Periodic model metadata refresh failed")


# Track last refresh attempt to debounce on-demand refreshes (mutable container
# avoids the need for a `global` statement that confuses linters).
_refresh_state: dict[str, datetime | None] = {"last_attempt": None}

# Lock to protect the debounce check against concurrent callers
_refresh_lock = asyncio.Lock()


async def maybe_trigger_refresh(session_factory) -> None:
    """Trigger a background refresh if debounce allows it.

    Intended to be called fire-and-forget from the model list endpoint.
    """
    async with _refresh_lock:
        now = datetime.now(timezone.utc)
        last = _refresh_state["last_attempt"]
        if (
            last is not None
            and (now - last).total_seconds() < REFRESH_DEBOUNCE_SECONDS
        ):
            return

        _refresh_state["last_attempt"] = now

    async def _refresh():
        try:
            async with session_factory() as session:
                await refresh_model_metadata_cache(session)
        except Exception:
            logger.exception("Background model metadata refresh failed")

    asyncio.create_task(_refresh())
