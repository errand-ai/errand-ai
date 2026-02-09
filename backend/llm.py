import logging
import os

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Setting

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_client: AsyncOpenAI | None = None


def init_llm_client() -> None:
    global _client
    base_url = os.environ.get("LITELLM_BASE_URL")
    api_key = os.environ.get("LITELLM_API_KEY")
    if base_url and api_key:
        _client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        logger.info("LLM client initialized (base_url=%s)", base_url)
    else:
        _client = None
        logger.warning("LLM client not configured: LITELLM_BASE_URL or LITELLM_API_KEY missing")


def get_llm_client() -> AsyncOpenAI | None:
    return _client


async def _get_model(session: AsyncSession) -> str:
    result = await session.execute(select(Setting).where(Setting.key == "llm_model"))
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        return str(setting.value)
    return DEFAULT_MODEL


def _fallback_title(description: str) -> str:
    words = description.split()
    return " ".join(words[:5]) + "..."


async def generate_title(description: str, session: AsyncSession) -> tuple[str, bool]:
    """Generate a short title from a task description using the LLM.

    Returns (title, success) where success indicates if LLM was used.
    """
    client = get_llm_client()
    if client is None:
        return _fallback_title(description), False

    model = await _get_model(session)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Summarize the following task description into a short title of 2-5 words. Return only the title, nothing else.",
                },
                {"role": "user", "content": description},
            ],
            timeout=5.0,
        )
        title = response.choices[0].message.content.strip()
        if not title:
            return _fallback_title(description), False
        return title, True
    except Exception:
        logger.exception("LLM title generation failed")
        return _fallback_title(description), False
