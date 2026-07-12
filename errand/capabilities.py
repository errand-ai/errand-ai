"""Server capability detection for cloud registration.

Derives the list of capabilities from runtime configuration to report
to errand-cloud on WebSocket connect.
"""
import logging
import os
from pathlib import Path

import database
from models import LlmProvider, Setting
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Version file at project root (dev layout: errand/errand/capabilities.py → errand/VERSION)
# In Docker the errand/ contents are flat under /app/, so also check parent/VERSION.
_HERE = Path(__file__).resolve().parent
_VERSION_PATHS = [_HERE.parent / "VERSION", _HERE / "VERSION"]


def get_server_version() -> str:
    """Read server version from VERSION file. Returns 'unknown' on failure."""
    for path in _VERSION_PATHS:
        try:
            return path.read_text().strip()
        except (FileNotFoundError, OSError):
            continue
    return "unknown"


async def get_capabilities() -> list[str]:
    """Derive capabilities list from runtime configuration.

    Always-present capabilities:
    - tasks, settings, mcp-servers, task-profiles, platforms

    Conditional capabilities:
    - voice-input: present when transcription_model is configured
    - litellm-mcp: present when LiteLLM MCP servers setting has entries
    """
    capabilities = ["tasks", "settings", "mcp-servers", "task-profiles", "platforms"]

    async with database.async_session() as session:
        # Check for voice-input (transcription model configured)
        result = await session.execute(
            select(Setting).where(Setting.key == "transcription_model")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            capabilities.append("voice-input")

        # Check for litellm-mcp (LiteLLM MCP servers enabled)
        result = await session.execute(
            select(Setting).where(Setting.key == "litellm_mcp_servers")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value and isinstance(setting.value, list) and len(setting.value) > 0:
            capabilities.append("litellm-mcp")

    return capabilities


# Capability keys consumed by the shared `@errand-ai/ui-components` settings
# cards (Wave 1). These use their own vocabulary (snake_case, per-card) and are
# distinct from the hyphenated cloud-registration capabilities above.
UI_ALWAYS_ON_CAPABILITIES = [
    "system_prompt",
    "mcp_servers",
    "skills_git_repo",
    "task_management",
    "telemetry",
]


async def get_ui_capabilities(session: AsyncSession) -> list[str]:
    """Capability keys advertised to the settings UI via ``GET /api/capabilities``.

    Always-on keys drive cards that are always available. Conditional keys gate
    optional integrations through the library's ``<CapabilityGate>``: if a key
    is absent the corresponding card does not render.

    Conditional keys:
    - ``cloud_storage`` — a cloud-storage provider (OneDrive) is configured in
      this server build (its MCP URL is set).
    - ``jira`` — the Jira platform integration is registered.
    - ``litellm_mcp`` — a LiteLLM proxy is detected at runtime (a ``litellm``
      LLM provider row exists, or the legacy ``OPENAI_BASE_URL`` env var is set).
    """
    capabilities = list(UI_ALWAYS_ON_CAPABILITIES)

    if os.environ.get("ONEDRIVE_MCP_URL"):
        capabilities.append("cloud_storage")

    try:
        from platforms import get_registry

        if get_registry().get("jira") is not None:
            capabilities.append("jira")
    except Exception:
        logger.debug("jira capability probe failed", exc_info=True)

    result = await session.execute(
        select(LlmProvider).where(LlmProvider.provider_type == "litellm").limit(1)
    )
    if result.scalar_one_or_none() is not None or os.environ.get("OPENAI_BASE_URL"):
        capabilities.append("litellm_mcp")

    return capabilities
