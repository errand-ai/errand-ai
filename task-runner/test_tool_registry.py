"""Unit tests for tool_registry.py — hot list, tool filter, catalog, discover_tools."""

# Mocks are set up in conftest.py (shared with test_main.py)

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
    scan_installed_skills,
    submit_result,
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


def test_tool_filter_blocks_non_enabled():
    """Non-enabled tools are blocked by the filter."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "sync_application"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "sync_application"
    assert filter_fn(filter_context, tool) is False


def test_tool_filter_allows_after_enable():
    """Tools are allowed after being added to enabled_tools."""
    ctx = ToolVisibilityContext(enabled_tools={"retain"}, all_known_tools={"retain", "sync_application"})
    filter_fn = create_tool_filter()

    filter_context = MagicMock()
    filter_context.run_context.context = ctx

    tool = MagicMock()
    tool.name = "sync_application"
    assert filter_fn(filter_context, tool) is False

    # Enable the tool
    ctx.enabled_tools.add("sync_application")
    assert filter_fn(filter_context, tool) is True


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


def test_discover_tools_always_on_only():
    """Probing for an always-on native tool reports it as already enabled."""
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"list_applications"},
        always_on_tools={"read_file", "write_file", "execute_command"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["read_file"])

    assert result == "Already enabled (always-on): read_file"
    # enabled_tools is unchanged — always-on tools are not added there.
    assert ctx.enabled_tools == set()


def test_discover_tools_mixed_outcomes():
    """Mixed probe of catalog, always-on, and unknown names produces three clauses in order."""
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"list_applications"},
        always_on_tools={"read_file"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["list_applications", "read_file", "made_up_tool"])

    assert result == (
        "Enabled: list_applications. "
        "Already enabled (always-on): read_file. "
        "Not found: made_up_tool"
    )
    assert "list_applications" in ctx.enabled_tools
    assert "read_file" not in ctx.enabled_tools


def test_discover_tools_always_on_precedence_over_catalog():
    """A name in both always_on_tools and all_known_tools is reported as always-on, not enabled."""
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"foo"},
        always_on_tools={"foo"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["foo"])

    assert result == "Already enabled (always-on): foo"
    assert "foo" not in ctx.enabled_tools


def test_discover_tools_always_on_does_not_mutate_state():
    """Probing for always-on tools never mutates enabled_tools."""
    ctx = ToolVisibilityContext(
        enabled_tools={"retain"},
        all_known_tools={"retain"},
        always_on_tools={"read_file", "submit_result"},
    )
    wrapper = _MockRunContextWrapper(ctx)

    discover_tools(wrapper, ["read_file", "submit_result"])

    assert ctx.enabled_tools == {"retain"}


# --- connect_mcp_servers passes tool_filter ---
# These tests import main.py which requires additional mocking (agents.run, openai, etc.)
# They are tested in test_main.py which has the full mock setup.


# --- Integration test: lazy loading flow ---


@pytest.mark.asyncio
async def test_lazy_loading_integration():
    """Integration: agent with lazy loading can discover and then use a deferred MCP tool."""
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

    # Initially, deferred tools are blocked
    deferred_tool = MagicMock()
    deferred_tool.name = "list_applications"
    assert filter_fn(filter_context, deferred_tool) is False

    # Hot-listed tools pass through
    hot_tool = MagicMock()
    hot_tool.name = "retain"
    assert filter_fn(filter_context, hot_tool) is True

    # Agent calls discover_tools
    wrapper = _MockRunContextWrapper(ctx)
    result = discover_tools(wrapper, ["list_applications", "sync_application"])
    assert "Enabled: list_applications, sync_application" in result

    # Now deferred tools pass through the filter
    assert filter_fn(filter_context, deferred_tool) is True
    sync_tool = MagicMock()
    sync_tool.name = "sync_application"
    assert filter_fn(filter_context, sync_tool) is True


# --- submit_result ---


def test_submit_result_stores_in_context():
    """submit_result stores result in context and returns confirmation."""
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set())
    wrapper = _MockRunContextWrapper(ctx)

    result = submit_result(wrapper, result="# Report\n\nFindings here...", status="completed")

    assert result == "Result submitted successfully. You may now stop."
    assert ctx.submitted_result == {
        "status": "completed",
        "result": "# Report\n\nFindings here...",
        "questions": [],
    }


def test_submit_result_needs_input():
    """submit_result stores needs_input status with questions."""
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set())
    wrapper = _MockRunContextWrapper(ctx)

    result = submit_result(
        wrapper,
        result="Partial findings so far...",
        status="needs_input",
        questions=["What date range?", "Which department?"],
    )

    assert result == "Result submitted successfully. You may now stop."
    assert ctx.submitted_result["status"] == "needs_input"
    assert ctx.submitted_result["questions"] == ["What date range?", "Which department?"]


def test_submit_result_defaults():
    """submit_result uses default status and empty questions."""
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set())
    wrapper = _MockRunContextWrapper(ctx)

    submit_result(wrapper, result="Done")

    assert ctx.submitted_result["status"] == "completed"
    assert ctx.submitted_result["questions"] == []


def test_submit_result_last_call_wins():
    """Multiple submit_result calls — last call wins."""
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set())
    wrapper = _MockRunContextWrapper(ctx)

    submit_result(wrapper, result="Draft 1")
    submit_result(wrapper, result="Final version")

    assert ctx.submitted_result["result"] == "Final version"


# --- scan_installed_skills() ---


def test_scan_installed_skills_missing_root(tmp_path):
    """Returns empty dict when skills_root does not exist."""
    missing = tmp_path / "does-not-exist"
    assert scan_installed_skills(str(missing)) == {}


def test_scan_installed_skills_unreadable_directory(tmp_path):
    """Permission errors on the skills root return an empty dict instead of crashing startup."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    # Patch os.listdir to simulate a permission error on the iteration step.
    with patch("tool_registry.os.listdir", side_effect=PermissionError("no read perms")):
        result = scan_installed_skills(str(skills_root))
    assert result == {}


def test_scan_installed_skills_populated(tmp_path):
    """Returns name → absolute SKILL.md path for each skill directory found."""
    (tmp_path / "tweet-publisher").mkdir()
    (tmp_path / "tweet-publisher" / "SKILL.md").write_text("publisher contents")
    (tmp_path / "gws-drive").mkdir()
    (tmp_path / "gws-drive" / "SKILL.md").write_text("drive contents")
    # A directory without a SKILL.md should be ignored.
    (tmp_path / "no-skill-md").mkdir()
    # A loose file at the root should be ignored.
    (tmp_path / "stray.md").write_text("ignore me")

    result = scan_installed_skills(str(tmp_path))

    assert set(result.keys()) == {"tweet-publisher", "gws-drive"}
    assert result["tweet-publisher"] == os.path.abspath(str(tmp_path / "tweet-publisher" / "SKILL.md"))
    assert result["gws-drive"] == os.path.abspath(str(tmp_path / "gws-drive" / "SKILL.md"))


# --- discover_tools skill-awareness ---


def test_discover_tools_loads_skill_when_name_matches(tmp_path):
    """A name matching only an installed skill returns the SKILL.md contents inline."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: tweet-publisher\ndescription: Post approved tweets\n---\n\n## Steps\n1. Read approved tweets...")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"list_applications"},
        installed_skills={"tweet-publisher": str(skill_md)},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["tweet-publisher"])

    assert result.startswith("Loaded skill: tweet-publisher\n\n")
    assert f"--- {skill_md} ---" in result
    assert "Post approved tweets" in result
    assert "## Steps" in result
    assert result.endswith("--- end skill ---")
    # enabled_tools must remain untouched on a skill match.
    assert ctx.enabled_tools == set()


def test_discover_tools_mixed_tool_skill_unknown(tmp_path):
    """Mixed probe produces clauses in order: Enabled → Loaded skill → Not found."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("tweet publisher body")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"list_applications"},
        installed_skills={"tweet-publisher": str(skill_md)},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["list_applications", "tweet-publisher", "made_up_name"])

    # All three clauses in the expected order.
    enabled_idx = result.index("Enabled: list_applications")
    loaded_idx = result.index("Loaded skill: tweet-publisher")
    not_found_idx = result.index("Not found: made_up_name")
    assert enabled_idx < loaded_idx < not_found_idx
    assert "list_applications" in ctx.enabled_tools


def test_discover_tools_tool_precedence_over_skill(tmp_path):
    """A name present in both the tool catalog and installed_skills classifies as Enabled."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("skill body")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools={"tweet-publisher"},
        installed_skills={"tweet-publisher": str(skill_md)},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["tweet-publisher"])

    assert result == "Enabled: tweet-publisher"
    assert "tweet-publisher" in ctx.enabled_tools
    assert "Loaded skill" not in result


def test_discover_tools_always_on_precedence_over_skill(tmp_path):
    """A name present in always_on_tools and installed_skills classifies as Already enabled (always-on)."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("skill body")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools=set(),
        always_on_tools={"read_file"},
        installed_skills={"read_file": str(skill_md)},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["read_file"])

    assert result == "Already enabled (always-on): read_file"
    assert "Loaded skill" not in result
    assert ctx.enabled_tools == set()


def test_discover_tools_skill_md_invalid_utf8_falls_back_to_not_found(tmp_path):
    """A SKILL.md containing invalid UTF-8 falls back to Not found without raising."""
    skill_md = tmp_path / "SKILL.md"
    # Bytes that are not valid UTF-8 (lone continuation byte 0x80).
    skill_md.write_bytes(b"\x80\x80\x80 not utf-8")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools=set(),
        installed_skills={"tweet-publisher": str(skill_md)},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["tweet-publisher"])

    assert result == "Not found: tweet-publisher"
    assert ctx.enabled_tools == set()


def test_discover_tools_skill_md_unreadable_falls_back_to_not_found(tmp_path):
    """If SKILL.md was deleted after startup, the probe falls back to Not found without raising."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("body")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools=set(),
        installed_skills={"tweet-publisher": str(skill_md)},
    )
    wrapper = _MockRunContextWrapper(ctx)
    # Simulate the file disappearing between startup and the call.
    skill_md.unlink()

    result = discover_tools(wrapper, ["tweet-publisher"])

    assert result == "Not found: tweet-publisher"
    assert ctx.enabled_tools == set()


def test_discover_tools_multiple_skill_matches(tmp_path):
    """Multiple skill matches produce one Loaded skill clause with concatenated delimited blocks in input order."""
    pub_md = tmp_path / "pub.md"
    pub_md.write_text("publisher body")
    drv_md = tmp_path / "drv.md"
    drv_md.write_text("drive body")
    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools=set(),
        installed_skills={
            "tweet-publisher": str(pub_md),
            "gws-drive": str(drv_md),
        },
    )
    wrapper = _MockRunContextWrapper(ctx)

    # Pass in a specific order; the response must preserve it.
    result = discover_tools(wrapper, ["tweet-publisher", "gws-drive"])

    assert result.startswith("Loaded skill: tweet-publisher, gws-drive\n\n")
    pub_idx = result.index(f"--- {pub_md} ---")
    drv_idx = result.index(f"--- {drv_md} ---")
    assert pub_idx < drv_idx
    # Each block ends with the closing delimiter.
    assert result.count("--- end skill ---") == 2
    assert "publisher body" in result
    assert "drive body" in result


def test_submit_result_rejects_invalid_status():
    """submit_result returns error message for invalid status values."""
    ctx = ToolVisibilityContext(enabled_tools=set(), all_known_tools=set())
    wrapper = _MockRunContextWrapper(ctx)

    result = submit_result(wrapper, result="Some output", status="invalid")

    assert "Invalid status" in result
    assert ctx.submitted_result is None  # not stored
