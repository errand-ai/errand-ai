"""Unit tests for tool_registry.py — hot list, tool filter, catalog, discover_tools."""

# Mocks are set up in conftest.py (shared with test_main.py)

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import MockRunContextWrapper as _MockRunContextWrapper

from tool_registry import (
    ToolVisibilityContext,
    build_tool_catalog,
    create_tool_filter,
    discover_tools,
    get_hot_list,
    _truncate_description,
    DEFAULT_HOT_TOOLS,
)


# --- get_hot_list() ---


def test_get_hot_list_defaults():
    """Returns default hot list when HOT_TOOLS not set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HOT_TOOLS", None)
        result = get_hot_list()
    assert result == DEFAULT_HOT_TOOLS


def test_get_hot_list_from_env():
    """Parses HOT_TOOLS env var."""
    with patch.dict(os.environ, {"HOT_TOOLS": "retain,recall,list_applications"}):
        result = get_hot_list()
    assert result == {"retain", "recall", "list_applications"}


def test_get_hot_list_strips_whitespace():
    """Handles whitespace in HOT_TOOLS."""
    with patch.dict(os.environ, {"HOT_TOOLS": " retain , recall "}):
        result = get_hot_list()
    assert result == {"retain", "recall"}


def test_get_hot_list_empty_env():
    """Empty HOT_TOOLS falls back to defaults."""
    with patch.dict(os.environ, {"HOT_TOOLS": ""}):
        result = get_hot_list()
    assert result == DEFAULT_HOT_TOOLS


# --- create_tool_filter() ---


def test_tool_filter_allows_hot_listed():
    """Hot-listed tools pass the filter."""
    ctx = ToolVisibilityContext(enabled_tools={"retain", "recall"}, all_known_tools={"retain", "recall", "reflect"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "retain"
    assert filter_fn(filter_context, tool) is True


def test_tool_filter_blocks_unknown():
    """Truly unknown tools (not in all_known_tools) are blocked."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "sync_application"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "nonexistent_tool"
    assert filter_fn(filter_context, tool) is False


def test_tool_filter_allows_after_explicit_enable():
    """Tools explicitly added to enabled_tools pass the filter."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "sync_application"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    # Explicitly enable the tool (as discover_tools would)
    ctx.enabled_tools.add("sync_application")

    tool = MagicMock()
    tool.name = "sync_application"
    assert filter_fn(filter_context, tool) is True


def test_tool_filter_auto_enables_known_undiscovered():
    """Known but undiscovered tools are auto-enabled by the filter."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "gdrive_read_file"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "gdrive_read_file"
    assert filter_fn(filter_context, tool) is True
    assert "gdrive_read_file" in ctx.enabled_tools


def test_tool_filter_auto_enable_logs_warning(caplog):
    """Auto-enabling a known undiscovered tool logs a warning."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "gdrive_read_file"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "gdrive_read_file"

    with caplog.at_level(logging.WARNING, logger="tool_registry"):
        filter_fn(filter_context, tool)

    assert any("Auto-enabled undiscovered tool: gdrive_read_file" in msg for msg in caplog.messages)


def test_tool_filter_auto_enabled_no_repeat_warning(caplog):
    """Once auto-enabled, subsequent calls do not log additional warnings."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "gdrive_read_file"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "gdrive_read_file"

    with caplog.at_level(logging.WARNING, logger="tool_registry"):
        filter_fn(filter_context, tool)  # First call — auto-enables + warns
        caplog.clear()
        filter_fn(filter_context, tool)  # Second call — already enabled, no warn

    assert not any("Auto-enabled" in msg for msg in caplog.messages)


# --- build_tool_catalog() ---


def _make_mock_server(name, tools):
    """Create a mock MCP server with tool list."""
    server = AsyncMock()
    server.name = name
    mock_tools = []
    for tool_name, tool_desc in tools:
        t = MagicMock()
        t.name = tool_name
        t.description = tool_desc
        mock_tools.append(t)
    server.list_tools.return_value = mock_tools
    return server


@pytest.mark.asyncio
async def test_build_tool_catalog_multiple_servers():
    """Generates XML catalog with multiple servers, excluding hot-listed tools."""
    argocd = _make_mock_server("argocd", [
        ("list_applications", "List all ArgoCD applications"),
        ("get_application", "Get details of an ArgoCD application"),
    ])
    hindsight = _make_mock_server("hindsight", [
        ("retain", "Store a memory"),
        ("recall", "Search memories"),
        ("reflect", "Reflect on memories"),
    ])
    hot_list = {"retain", "recall"}

    catalog, all_known = await build_tool_catalog([argocd, hindsight], hot_list)

    assert "<available_mcp_tools>" in catalog
    assert "- list_applications:" in catalog
    assert "- get_application:" in catalog
    assert "- reflect:" in catalog
    # Hot-listed tools should NOT appear in catalog
    assert "- retain:" not in catalog
    assert "- recall:" not in catalog
    # All known tools includes everything
    assert all_known == {"list_applications", "get_application", "retain", "recall", "reflect"}


@pytest.mark.asyncio
async def test_build_tool_catalog_all_hot_listed():
    """Returns empty string when all tools are hot-listed."""
    server = _make_mock_server("hindsight", [
        ("retain", "Store a memory"),
        ("recall", "Search memories"),
    ])
    hot_list = {"retain", "recall"}

    catalog, all_known = await build_tool_catalog([server], hot_list)

    assert catalog == ""
    assert all_known == {"retain", "recall"}


@pytest.mark.asyncio
async def test_build_tool_catalog_server_all_hot():
    """Server with all hot-listed tools is omitted from catalog."""
    hot_server = _make_mock_server("hindsight", [
        ("retain", "Store a memory"),
        ("recall", "Search memories"),
    ])
    normal_server = _make_mock_server("argocd", [
        ("list_applications", "List all ArgoCD applications"),
    ])
    hot_list = {"retain", "recall"}

    catalog, _ = await build_tool_catalog([hot_server, normal_server], hot_list)

    assert "- list_applications:" in catalog
    # Hot-listed tools from hindsight should not appear
    assert "- retain:" not in catalog
    assert "- recall:" not in catalog


@pytest.mark.asyncio
async def test_build_tool_catalog_empty_servers():
    """Returns empty catalog for no servers."""
    catalog, all_known = await build_tool_catalog([], {"retain"})
    assert catalog == ""
    assert all_known == set()


@pytest.mark.asyncio
async def test_build_tool_catalog_truncates_descriptions():
    """Long descriptions are truncated."""
    long_desc = "This is a very long description. It has multiple sentences and goes on for a while."
    server = _make_mock_server("test", [("tool1", long_desc)])

    catalog, _ = await build_tool_catalog([server], set())

    # Should contain first sentence only
    assert "This is a very long description." in catalog
    assert "It has multiple sentences" not in catalog


# --- _truncate_description() ---


def test_truncate_description_first_sentence():
    """Truncates to first sentence."""
    assert _truncate_description("First sentence. Second sentence.") == "First sentence."


def test_truncate_description_short():
    """Short descriptions are unchanged."""
    assert _truncate_description("Short desc") == "Short desc"


def test_truncate_description_long_no_sentence():
    """Long text without sentence boundary is cut at 100 chars."""
    long_text = "x" * 200
    result = _truncate_description(long_text)
    assert len(result) == 103  # 100 + "..."
    assert result.endswith("...")


def test_truncate_description_empty():
    """Empty description returns empty string."""
    assert _truncate_description("") == ""


# --- discover_tools ---


def test_discover_tools_enables_existing():
    """discover_tools adds known tools to enabled set."""
    ctx = ToolVisibilityContext(
        enabled_tools={"retain"},
        all_known_tools={"retain", "list_applications", "get_application"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["list_applications", "get_application"])

    assert "list_applications" in ctx.enabled_tools
    assert "get_application" in ctx.enabled_tools
    assert "Enabled: list_applications, get_application" in result


def test_discover_tools_reports_unknown():
    """discover_tools reports unknown tools."""
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"list_applications"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["list_applications", "nonexistent_tool"])

    assert "list_applications" in ctx.enabled_tools
    assert "Enabled: list_applications" in result
    assert "Not found: nonexistent_tool" in result


def test_discover_tools_idempotent():
    """Re-enabling already-enabled tool is idempotent."""
    ctx = ToolVisibilityContext(
        enabled_tools={"retain"},
        all_known_tools={"retain"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["retain"])

    assert "Enabled: retain" in result
    assert "retain" in ctx.enabled_tools


def test_discover_tools_empty_list():
    """Empty tool list returns appropriate message."""
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set())
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, [])

    assert result == "No tools specified."


# --- connect_mcp_servers passes tool_filter ---
# These tests import main.py which requires additional mocking (agents.run, openai, etc.)
# They are tested in test_main.py which has the full mock setup.


# --- Integration test: lazy loading flow ---


@pytest.mark.asyncio
async def test_lazy_loading_integration():
    """Integration: agent with lazy loading — discover_tools and auto-enable both work."""
    # Set up hot list and visibility context
    hot_list = {"retain", "recall"}
    ctx = ToolVisibilityContext(
        enabled_tools=set(hot_list),
        all_known_tools={"retain", "recall", "list_applications", "sync_application"},
    )

    # Create filter
    filter_fn = create_tool_filter()

    # Simulate filter context
    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    # Hot-listed tools pass through
    hot_tool = MagicMock()
    hot_tool.name = "retain"
    assert filter_fn(filter_context, hot_tool) is True

    # Unknown tools are blocked
    unknown_tool = MagicMock()
    unknown_tool.name = "totally_unknown"
    assert filter_fn(filter_context, unknown_tool) is False

    # Known but undiscovered tools are auto-enabled
    deferred_tool = MagicMock()
    deferred_tool.name = "list_applications"
    assert filter_fn(filter_context, deferred_tool) is True
    assert "list_applications" in ctx.enabled_tools

    # Agent can also explicitly discover tools
    wrapper = _MockRunContextWrapper(ctx)
    result = discover_tools(wrapper, ["sync_application"])
    assert "Enabled: sync_application" in result

    sync_tool = MagicMock()
    sync_tool.name = "sync_application"
    assert filter_fn(filter_context, sync_tool) is True
