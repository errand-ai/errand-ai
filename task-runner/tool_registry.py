"""Lazy MCP tool loading — catalog generation, hot list, tool visibility, discover_tools."""

import logging
import os
from dataclasses import dataclass, field
from xml.sax.saxutils import escape as xml_escape

from agents import function_tool
from agents.run_context import RunContextWrapper

logger = logging.getLogger(__name__)


DEFAULT_HOT_TOOLS = {"web_search", "fetch_url", "retain", "recall"}


@dataclass
class ToolVisibilityContext:
    """Tracks which MCP tools are visible to the agent."""

    enabled_tools: set[str] = field(default_factory=set)
    all_known_tools: set[str] = field(default_factory=set)


def get_hot_list() -> set[str]:
    """Return the hot list of tool names that are always visible.

    Reads HOT_TOOLS env var (comma-separated) or returns defaults.
    """
    raw = os.environ.get("HOT_TOOLS", "")
    if raw.strip():
        return {name.strip() for name in raw.split(",") if name.strip()}
    return set(DEFAULT_HOT_TOOLS)


def create_tool_filter():
    """Return a ToolFilterCallable that checks enabled_tools on the run context."""

    def tool_filter(filter_context, tool) -> bool:
        ctx: ToolVisibilityContext = filter_context.run_context.context
        return tool.name in ctx.enabled_tools

    return tool_filter


def _truncate_description(desc: str, max_length: int = 100) -> str:
    """Truncate to first sentence or max_length characters."""
    if not desc:
        return ""
    # First sentence: split on '. ' or '.\n'
    for sep in (". ", ".\n"):
        idx = desc.find(sep)
        if idx != -1:
            sentence = desc[: idx + 1]
            if len(sentence) <= max_length:
                return sentence
            return sentence[:max_length] + "..."
    # No sentence boundary found
    if len(desc) <= max_length:
        return desc
    return desc[:max_length] + "..."


async def build_tool_catalog(servers: list, hot_list: set[str]) -> tuple[str, set[str]]:
    """Build a compact XML tool catalog from connected MCP servers.

    Returns (catalog_xml, all_known_tools) where catalog_xml is empty string
    if all tools are hot-listed.
    """
    all_known_tools: set[str] = set()
    deferred_lines: list[str] = []

    for server in servers:
        try:
            tools = await server.list_tools()
        except Exception as e:
            logger.warning("Failed to list tools from server '%s': %s", server.name, e)
            continue

        all_known_tools.update(t.name for t in tools)

        # Collect deferred (non-hot) tools for catalog display
        for t in tools:
            if t.name not in hot_list:
                desc = xml_escape(_truncate_description(t.description or ""))
                name = xml_escape(t.name)
                deferred_lines.append(f"- {name}: {desc}")

    if not deferred_lines:
        return "", all_known_tools

    header = "These MCP tools are available but not yet enabled. Call discover_tools with the exact tool name(s) listed below to enable them before use. Only discover tools you actually need for the current task."
    catalog = "<available_mcp_tools>\n" + header + "\n" + "\n".join(deferred_lines) + "\n</available_mcp_tools>"
    return catalog, all_known_tools


@function_tool
def discover_tools(ctx: RunContextWrapper[ToolVisibilityContext], tool_names: list[str]) -> str:
    """Enable MCP tools by name so they become available for use.

    Consult the <available_mcp_tools> catalog in the system prompt to find tool names.
    Only enable tools you need for the current task — do not speculatively enable tools.
    You can enable multiple tools in a single call.

    Args:
        tool_names: List of tool names to enable.
    """
    visibility: ToolVisibilityContext = ctx.context
    enabled = []
    not_found = []

    for name in tool_names:
        if name in visibility.all_known_tools:
            visibility.enabled_tools.add(name)
            enabled.append(name)
        else:
            not_found.append(name)

    parts = []
    if enabled:
        parts.append(f"Enabled: {', '.join(enabled)}")
    if not_found:
        parts.append(f"Not found: {', '.join(not_found)}")
    return ". ".join(parts) if parts else "No tools specified."
