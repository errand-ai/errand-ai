"""Tests for EXCLUDED_CATALOG_TOOLS: admin/eval MCP tools must never surface to
task LLMs — absent from the catalog and refused by discover_tools.

Covers the lazy-mcp-tool-registry spec (llm-eval-framework change).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import MockRunContextWrapper as _MockRunContextWrapper

from tool_registry import (
    EXCLUDED_CATALOG_TOOLS,
    ToolVisibilityContext,
    build_tool_catalog,
    discover_tools,
)


def _make_mock_server(name, tools):
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
async def test_excluded_tools_absent_from_catalog_and_known():
    # The Errand MCP server exposes eval/admin tools alongside normal ones; the
    # excluded ones must not appear in the catalog or in all_known_tools (which
    # is what discover_tools and the auto-enable recovery gate on).
    server = _make_mock_server("errand", [
        ("record_eval_result", "Record an eval result"),
        ("clone_task_profile", "Clone a profile"),
        ("search_tasks", "Search task history"),
        ("task_status", "Get task status"),
        ("new_task", "Create a task"),
    ])
    catalog, all_known = await build_tool_catalog([server], hot_list=set())

    assert "record_eval_result" not in catalog
    assert "clone_task_profile" not in catalog
    assert "search_tasks" not in catalog
    # Normal tools still catalogued.
    assert "- task_status:" in catalog
    assert "- new_task:" in catalog
    # all_known excludes the admin tools entirely.
    assert all_known == {"task_status", "new_task"}
    assert not (EXCLUDED_CATALOG_TOOLS & all_known)


def test_discover_tools_refuses_excluded_even_if_known():
    # Belt-and-suspenders: even if an excluded tool somehow appears in
    # all_known_tools, discover_tools refuses it and reports it as not found —
    # never revealing it as available.
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"search_tasks", "task_status"},  # search_tasks should be refused
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["search_tasks", "task_status"])

    assert "search_tasks" not in ctx.enabled_tools
    assert "task_status" in ctx.enabled_tools
    assert "Enabled: task_status" in result
    assert "Not found: search_tasks" in result
    assert "Enabled: search_tasks" not in result


def test_discover_tools_refuses_all_excluded_by_name():
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set(EXCLUDED_CATALOG_TOOLS))
    wrapper = _MockRunContextWrapper(ctx)
    result = discover_tools(wrapper, sorted(EXCLUDED_CATALOG_TOOLS))
    assert ctx.enabled_tools == set()
    for name in EXCLUDED_CATALOG_TOOLS:
        assert name in result  # each reported under "Not found"
    assert "Enabled:" not in result
