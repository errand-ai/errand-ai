"""Server capability detection for cloud registration.

Derives the list of capabilities from runtime configuration to report
to errand-cloud on WebSocket connect.
"""
import logging
from pathlib import Path

import database
from models import Setting
from sqlalchemy import select

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
