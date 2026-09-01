"""Lazy MCP tool loading — catalog generation, hot list, tool visibility, discover_tools."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from agents import function_tool
from agents.run_context import RunContextWrapper
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema

logger = logging.getLogger(__name__)


DEFAULT_HOT_TOOLS = {"web_search", "fetch_url", "retain", "recall"}

# Administrative MCP tools the Errand server exposes for the eval framework
# (profile clone/delete, full-history search, eval run recording). They are never
# for task LLMs: they are omitted from the generated catalog, discover_tools
# refuses to enable them (responding as if they do not exist), and the
# auto-enable-on-error recovery skips them. See the llm-eval-framework change.
EXCLUDED_CATALOG_TOOLS = {
    "clone_task_profile",
    "delete_task_profile",
    "search_tasks",
    "start_eval_run",
    "record_eval_result",
    "finish_eval_run",
    "get_eval_run",
}


@dataclass
class ToolVisibilityContext:
    """Tracks which MCP tools are visible to the agent and submitted result state."""

    enabled_tools: set[str] = field(default_factory=set)
    all_known_tools: set[str] = field(default_factory=set)
    always_on_tools: set[str] = field(default_factory=set)
    installed_skills: dict[str, str] = field(default_factory=dict)
    submitted_result: dict | None = None


def scan_installed_skills(skills_root: str = "/workspace/skills") -> dict[str, str]:
    """Scan ``skills_root`` for ``*/SKILL.md`` files and return ``{name: absolute_path}``.

    Returns an empty dict if ``skills_root`` does not exist or contains no skill
    directories. Used to populate ``ToolVisibilityContext.installed_skills`` so
    that ``discover_tools`` can recover from skill-name probes by inlining the
    matched SKILL.md content.
    """
    if not os.path.isdir(skills_root):
        return {}

    skills: dict[str, str] = {}
    try:
        entries = os.listdir(skills_root)
    except OSError as e:
        logger.warning("Failed to list skills directory %s: %s", skills_root, e)
        return {}
    for entry in entries:
        skill_dir = os.path.join(skills_root, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if os.path.isfile(skill_md):
            skills[entry] = os.path.abspath(skill_md)
    return skills


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

        # Excluded admin/eval tools are treated as if the server never exposed
        # them: they don't enter all_known_tools (so discover_tools and the
        # error-recovery path can't enable them) and never appear in the catalog.
        visible = [t for t in tools if t.name not in EXCLUDED_CATALOG_TOOLS]
        all_known_tools.update(t.name for t in visible)

        # Collect deferred (non-hot) tools for catalog display
        for t in visible:
            if t.name not in hot_list:
                desc = xml_escape(_truncate_description(t.description or ""))
                name = xml_escape(t.name)
                deferred_lines.append(f"- {name}: {desc}")

    if not deferred_lines:
        return "", all_known_tools

    header = "IMPORTANT: The tools listed below are NOT yet enabled. You MUST call discover_tools with the tool name(s) BEFORE you can use them. Calling a tool without discovering it first will cause an error. Discover all tools you need in a single call."
    catalog = "<available_mcp_tools>\n" + header + "\n" + "\n".join(deferred_lines) + "\n</available_mcp_tools>"
    return catalog, all_known_tools


def _normalise_questions(value: Any) -> list[str]:
    """Coerce whatever arrived for ``questions`` into a list of strings.

    Some inference servers serialise an array argument as a JSON-encoded string
    (``"questions": "[]"``), so decode a string rather than rejecting the call.
    A string that fails to decode, or decodes to something other than an array,
    is preserved as a single question: a slightly malformed follow-up is better
    than a silently dropped one.
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return [value]
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


class QuestionList(list):
    """Annotation for ``submit_result``'s ``questions`` parameter.

    Emits a plain ``{"type": "array", "items": {"type": "string"}}`` schema — no
    ``anyOf`` branch, no ``"null"`` type — while tolerating a JSON-encoded array
    string at validation time. The nullable union ``list[str] | None`` produces
    exactly the ``anyOf: [array, null]`` shape that at least one production
    inference server mis-serialises as a string, failing every call; the schema
    the model sees must therefore stay a bare array, with the tolerance living in
    the validator instead. This cannot be expressed with ``Annotated`` metadata:
    the agents SDK strips ``Annotated`` down to the bare type (keeping only a
    description or ``FieldInfo``) before building its pydantic model, so a
    ``BeforeValidator`` or ``WithJsonSchema`` placed there is discarded.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(_normalise_questions)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        return {"type": "array", "items": {"type": "string"}}


@function_tool
def submit_result(ctx: RunContextWrapper[ToolVisibilityContext], result: str, status: str = "completed", questions: QuestionList = []) -> str:
    """Submit the task result to the user. Call this when you have completed your work.

    This is the primary way to deliver your output. The result field is the ONLY output
    the user will see — include the full content (text, code, analysis, etc.) with markdown
    formatting. If called multiple times, only the last call is used.

    Args:
        result: The full task output with markdown formatting.
        status: Either "completed" or "needs_input". Defaults to "completed".
        questions: Follow-up questions when status is "needs_input". A list of strings, or a JSON-encoded array string. Defaults to [].
    """
    if status not in ("completed", "needs_input"):
        return f"Invalid status '{status}'. Must be 'completed' or 'needs_input'."
    ctx.context.submitted_result = {
        "status": status,
        "result": result,
        "questions": _normalise_questions(questions),
    }
    return "Result submitted successfully. You may now stop."


@function_tool
def discover_tools(ctx: RunContextWrapper[ToolVisibilityContext], tool_names: list[str]) -> str:
    """Enable MCP tools by name so they become available for use.

    Consult the <available_mcp_tools> catalog in the system prompt to find tool names.
    Only enable tools you need for the current task — do not speculatively enable tools.
    You can enable multiple tools in a single call.

    If a name matches an installed Agent Skill rather than a tool, the skill's
    SKILL.md content is returned inline under a ``Loaded skill:`` clause so the
    instructions are available immediately (no follow-up ``read_file`` needed).

    Args:
        tool_names: List of tool names to enable.
    """
    visibility: ToolVisibilityContext = ctx.context
    enabled: list[str] = []
    already_on: list[str] = []
    loaded_skills: list[tuple[str, str, str]] = []  # (name, path, content)
    not_found: list[str] = []

    for name in tool_names:
        # Excluded admin/eval tools are never enableable — respond as if they
        # don't exist, regardless of what the server exposes.
        if name in EXCLUDED_CATALOG_TOOLS:
            not_found.append(name)
            continue
        # Precedence: always_on > catalog > installed skill > not found.
        if name in visibility.always_on_tools:
            already_on.append(name)
        elif name in visibility.all_known_tools:
            visibility.enabled_tools.add(name)
            enabled.append(name)
        elif name in visibility.installed_skills:
            path = visibility.installed_skills[name]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read SKILL.md for '%s' at %s: %s", name, path, e)
                not_found.append(name)
                continue
            loaded_skills.append((name, path, content))
        else:
            not_found.append(name)

    parts: list[str] = []
    if enabled:
        parts.append(f"Enabled: {', '.join(enabled)}")
    if already_on:
        parts.append(f"Already enabled (always-on): {', '.join(already_on)}")
    if loaded_skills:
        names = ", ".join(n for n, _, _ in loaded_skills)
        blocks = "\n\n".join(
            f"--- {path} ---\n{content}\n--- end skill ---"
            for _, path, content in loaded_skills
        )
        parts.append(f"Loaded skill: {names}\n\n{blocks}")
    if not_found:
        parts.append(f"Not found: {', '.join(not_found)}")
    return ". ".join(parts) if parts else "No tools specified."
