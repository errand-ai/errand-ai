"""Task runner agent — reads environment variables and files, runs a ReAct agent, outputs structured JSON."""

import asyncio
import copy
import difflib
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from openai import AsyncOpenAI, OpenAI, APIConnectionError, APITimeoutError, RateLimitError, BadRequestError, AuthenticationError, APIStatusError
from openai.types.shared import Reasoning
from pydantic import BaseModel

from agents import Agent, ItemHelpers, ModelSettings, RunConfig, Runner, RunHooks, function_tool, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from agents.exceptions import ModelBehaviorError
from agents.mcp import MCPServerStreamableHttp
from agents.models.openai_provider import OpenAIProvider
from agents.run import CallModelData, ModelInputData

from tool_registry import ToolVisibilityContext, build_tool_catalog, create_tool_filter, discover_tools, get_hot_list, submit_result

# All logging to stderr; LOG_LEVEL env var controls verbosity (default: INFO)
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Disable tracing (no OpenAI tracing endpoint in sandboxed container)
set_tracing_disabled(True)

TOOL_RESULT_MAX_LENGTH = 500

# Pattern-based lookup for max output tokens by model.
# Patterns are checked in order — first substring match wins.
# Covers Claude (Anthropic/Bedrock/Vertex), OpenAI, and Google model families.
_MAX_OUTPUT_TOKENS_PATTERNS = [
    ("opus-4-6",      128000),
    ("opus-4-5",       64000),
    ("opus-4-1",       32000),
    ("opus-4",         32000),
    ("sonnet-4",       64000),
    ("haiku-4",        64000),
    ("claude-3",        4096),
    ("gpt-4.1",        32768),
    ("gpt-4o",         16384),
    ("gpt-5",         100000),
    ("gemini-2.5",     65535),
    ("gemini-2",       65535),
]
DEFAULT_MAX_OUTPUT_TOKENS = 16384


def resolve_max_output_tokens(model: str) -> int:
    """Resolve max output tokens for a model using pattern matching.

    Checks MAX_OUTPUT_TOKENS env var first (overrides lookup).
    Then matches model name substrings in priority order.
    Falls back to DEFAULT_MAX_OUTPUT_TOKENS if no pattern matches.
    """
    env_override = os.environ.get("MAX_OUTPUT_TOKENS", "")
    if env_override:
        try:
            value = int(env_override)
            if value > 0:
                return value
            logger.warning("Invalid MAX_OUTPUT_TOKENS value '%s' (must be positive), using lookup", env_override)
        except ValueError:
            logger.warning("Invalid MAX_OUTPUT_TOKENS value '%s' (not an integer), using lookup", env_override)

    model_lower = model.lower()
    for pattern, max_tokens in _MAX_OUTPUT_TOKENS_PATTERNS:
        if pattern in model_lower:
            return max_tokens
    return DEFAULT_MAX_OUTPUT_TOKENS


def _truncate(text: str, max_length: int = TOOL_RESULT_MAX_LENGTH) -> str:
    """Truncate text to max_length, appending '...' if truncated."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def extract_json(text: str) -> dict | None:
    """Extract a valid TaskRunnerOutput JSON object from LLM output.

    Tries three strategies in order:
    1. Direct parse of the full text
    2. Extract content from a markdown code fence
    3. Extract substring from first '{' to last '}'

    Returns the parsed dict if valid TaskRunnerOutput, otherwise None.
    """
    stripped = text.strip()

    # Strategy 1: direct parse
    try:
        parsed = json.loads(stripped)
        TaskRunnerOutput(**parsed)
        return parsed
    except (json.JSONDecodeError, TypeError, Exception):
        pass

    # Strategy 2: code fence extraction
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", stripped, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            TaskRunnerOutput(**parsed)
            return parsed
        except (json.JSONDecodeError, TypeError, Exception):
            pass

    # Strategy 3: first '{' to last '}'
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            parsed = json.loads(stripped[first_brace:last_brace + 1])
            TaskRunnerOutput(**parsed)
            return parsed
        except (json.JSONDecodeError, TypeError, Exception):
            pass

    return None


def emit_event(event_type: str, data: dict) -> None:
    """Write a single-line JSON event to stderr."""
    print(json.dumps({"type": event_type, "data": data}), file=sys.stderr, flush=True)


class StreamEventEmitter(RunHooks):
    """Emits structured JSON events to stderr for agent lifecycle callbacks."""

    def __init__(self):
        self._current_turn_id: str | None = None
        self._tool_start_times: dict[str, float] = {}

    async def on_agent_start(self, context, agent) -> None:
        emit_event("agent_start", {"agent": agent.name})

    async def on_tool_start(self, context, agent, tool) -> None:
        self._tool_start_times[tool.name] = time.monotonic()

    async def on_tool_end(self, context, agent, tool, result) -> None:
        start = self._tool_start_times.pop(tool.name, None)
        duration_ms = int((time.monotonic() - start) * 1000) if start is not None else None
        result_str = str(result)
        original_length = len(result_str)
        data: dict = {
            "tool": tool.name,
            "output": _truncate(result_str),
            "length": original_length,
        }
        if duration_ms is not None:
            data["duration_ms"] = duration_ms
        if self._current_turn_id:
            data["turn_id"] = self._current_turn_id
        emit_event("tool_result", data)

    async def on_agent_end(self, context, agent, output) -> None:
        try:
            output_data = output.model_dump() if hasattr(output, "model_dump") else {"raw": str(output)}
        except Exception:
            output_data = {"raw": str(output)}
        emit_event("agent_end", {"output": output_data})

    async def on_llm_start(self, context, agent, *args, **kwargs) -> None:
        self._current_turn_id = str(uuid4())[:8]
        emit_event("llm_turn_start", {
            "turn_id": self._current_turn_id,
            "model": os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL", "unknown"),
        })

    async def on_llm_end(self, context, agent, *args, **kwargs) -> None:
        pass


class TaskRunnerOutput(BaseModel):
    status: str
    result: str
    questions: list[str] = []


FILE_TOOL_GUIDANCE = """

## File Operations
For reading, writing, and editing files, use the dedicated file tools
(read_file, write_file, edit_file) instead of shell commands. These tools
provide safer concurrent access and structured output. Do not use shell
commands such as cat, echo, or sed for ordinary file operations. Use
execute_command for non-file operations (installing packages, running tests,
git commands, etc.).
"""

OUTPUT_INSTRUCTIONS = """

## Delivering Your Result

When you have completed your work, you MUST deliver the result using the `submit_result` tool:

1. **First**, call `retain()` to save key findings to persistent memory for future tasks.
2. **Then**, call `submit_result(result="<your detailed result>", status="completed")` to deliver the output to the user.

The `result` field is the ONLY output the user will see. Include the full content you produced (text, code, analysis, creative writing, etc.) directly in the result. Use markdown formatting for readability. Do NOT just describe what you did — include the actual content.

If you need more information from the user:
  submit_result(result="<what you've done so far>", status="needs_input", questions=["<question 1>", "<question 2>"])

IMPORTANT — `retain` vs `submit_result`:
- `retain()` saves information to persistent memory for FUTURE tasks. It does NOT deliver output to the user.
- `submit_result()` delivers the result to the user and completes the current task. This is your primary output mechanism.

Calling `retain` without `submit_result` means the user gets nothing. Always call `submit_result` when you are done.

Fallback: If `submit_result` is unavailable, respond with a JSON object: {"status": "completed", "result": "...", "questions": []}
"""


def read_env_vars() -> dict[str, str]:
    """Read and validate required environment variables."""
    required = [
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "USER_PROMPT_PATH",
        "SYSTEM_PROMPT_PATH",
        "MCP_CONFIGURATION_PATH",
    ]
    env = {}
    missing = []
    for key in required:
        value = os.environ.get(key)
        if not value:
            missing.append(key)
        else:
            env[key] = value

    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return env


def _read_startup_file(path: str, name: str) -> str:
    """Read a file and return its contents. Exit with error if file is missing."""
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Required file not found: {name} at {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Error reading {name} at {path}: {e}", file=sys.stderr)
        sys.exit(1)


def parse_mcp_config(raw: str) -> dict:
    """Parse MCP configuration JSON. Returns empty dict on parse failure."""
    if not raw.strip():
        return {}
    try:
        config = json.loads(raw)
        if not isinstance(config, dict):
            return {}
        return config
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse MCP configuration: %s", e)
        return {}


async def connect_mcp_servers(config: dict, stack: AsyncExitStack) -> list:
    """Connect to HTTP Streaming MCP servers from configuration. Returns list of connected servers."""
    servers = []
    mcp_servers = config.get("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        return servers

    for name, entry in mcp_servers.items():
        if not isinstance(entry, dict):
            logger.warning("Skipping MCP server '%s': invalid entry", name)
            continue

        # Skip STDIO servers
        if "command" in entry or "args" in entry:
            logger.warning("Skipping MCP server '%s': STDIO servers are not supported", name)
            continue

        url = entry.get("url")
        if not url or not isinstance(url, str):
            logger.warning("Skipping MCP server '%s': missing or invalid 'url'", name)
            continue

        headers = entry.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}

        try:
            params = {"url": url, "timeout": 300, "sse_read_timeout": 600}
            if headers:
                params["headers"] = headers

            kwargs = {
                "name": name,
                "params": params,
                "cache_tools_list": True,
                "client_session_timeout_seconds": 300,
            }

            server = MCPServerStreamableHttp(**kwargs)
            connected = await stack.enter_async_context(server)
            servers.append(connected)
            logger.info("Connected to MCP server '%s' at %s", name, url)
        except Exception as e:
            logger.warning("Failed to connect to MCP server '%s': %s", name, e)

    return servers


COMMAND_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "120"))
MAX_RETAINED_SCREENSHOTS = int(os.environ.get("MAX_RETAINED_SCREENSHOTS", "2"))
MAX_CONTEXT_TOKENS = int(os.environ.get("MAX_CONTEXT_TOKENS", "150000"))
CHARS_PER_TOKEN = 3  # conservative: base64 images tokenize at ~2-3 chars/token
MAX_TOOL_OUTPUT_CHARS = int(MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25)
KEEP_RECENT_TOKENS = 20_000  # tokens of recent messages to retain during compaction

# Marker that identifies a compaction summary message (task 4.2)
COMPACTION_SUMMARY_PREFIX = "The conversation history before this point was compacted into the following summary:"

# Summarization prompts (tasks 1.1–1.3)
SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a context summarization assistant. Your sole job is to produce a structured "
    "checkpoint summary of a conversation. Do NOT continue the conversation, answer questions, "
    "or take any action. Output ONLY the summary in the requested format."
)

FIRST_COMPACTION_PROMPT = """\
Summarize the following conversation into a structured checkpoint. Use exactly these sections:

## Goal
What the agent is trying to accomplish in this task.

## Progress
### Done
Completed steps and outcomes.

### In Progress
What is currently being worked on.

### Blocked
Any blockers or unresolved issues.

## Key Decisions
Important choices made and their rationale.

## Next Steps
Concrete actions remaining to complete the goal.

## Critical Context
Important facts, constraints, or context the agent must remember.

---
{conversation}"""

MERGE_COMPACTION_PROMPT = """\
You have an existing summary of earlier conversation history, and new conversation content that \
occurred after that summary. Merge the new content into the existing summary: update progress, \
add new decisions and context, and remove only clearly irrelevant items. Preserve all existing \
information that is still relevant.

The merged summary must have exactly these sections:

## Goal
## Progress (### Done / ### In Progress / ### Blocked)
## Key Decisions
## Next Steps
## Critical Context

---
Existing summary:

{existing_summary}

---
New conversation content to merge:

{conversation}"""


@function_tool
def execute_command(command: str, working_directory: str = "/workspace") -> str:
    """Execute a shell command and return the combined stdout and stderr output.

    Use this tool to run commands like git clone, ls, grep, pip install, etc.
    For reading, writing, and editing files, prefer the dedicated file tools
    (read_file, write_file, edit_file) instead.

    Args:
        command: The shell command to execute.
        working_directory: The directory to run the command in. Defaults to /workspace.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=working_directory,
        )
        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(result.stderr)
        output = "\n".join(output_parts) if output_parts else "(no output)"
        if result.returncode != 0:
            output = f"Command exited with code {result.returncode}\n{output}"
        if len(output) > MAX_TOOL_OUTPUT_CHARS:
            original_len = len(output)
            output = output[:MAX_TOOL_OUTPUT_CHARS] + (
                f"\n\n[OUTPUT TRUNCATED — was {original_len} characters, limit is {MAX_TOOL_OUTPUT_CHARS} characters]\n"
                "This output exceeds the context window budget. For binary files (images, archives, etc.), "
                "do not read contents into the conversation. Use file-path-based tools to upload or process "
                "them directly (e.g., Google Drive upload_file with the file path)."
            )
            logger.warning(
                "execute_command output truncated: %d -> %d characters (limit %d)",
                original_len, len(output), MAX_TOOL_OUTPUT_CHARS,
            )
        return output
    except subprocess.TimeoutExpired:
        return f"Command timed out after {COMMAND_TIMEOUT} seconds"
    except Exception as e:
        return f"Error executing command: {e}"


# --- File Mutation Queue and File Tools ---

class _FileLockState:
    """Tracks a per-path lock and the number of coroutines using or waiting on it."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.users = 0


class FileMutationQueue:
    """Per-file asyncio.Lock map that serializes writes to the same path."""

    def __init__(self):
        self._locks: dict[str, _FileLockState] = {}

    @asynccontextmanager
    async def acquire(self, path: str):
        """Acquire a lock for the resolved absolute path."""
        resolved = str(Path(path).resolve())
        state = self._locks.get(resolved)
        if state is None:
            state = _FileLockState()
            self._locks[resolved] = state

        state.users += 1
        try:
            async with state.lock:
                yield
        finally:
            state.users -= 1
            if state.users == 0:
                self._locks.pop(resolved, None)


_file_mutation_queue = FileMutationQueue()


def _write_file_sync(path: str, content: str) -> str:
    """Synchronous write implementation run via asyncio.to_thread."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    byte_count = p.stat().st_size
    return f"Wrote {byte_count} bytes to {path}"


@function_tool
async def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with the given content.

    Use this tool for writing files instead of shell commands like echo or cat.
    It provides safe concurrent access via per-file locking.

    Args:
        path: The file path to write to.
        content: The content to write to the file.
    """
    async with _file_mutation_queue.acquire(path):
        try:
            return await asyncio.to_thread(_write_file_sync, path, content)
        except (OSError, UnicodeError) as exc:
            return f"Error: unable to write file {path}: {exc}"


def _edit_file_sync(path: str, old_text: str, new_text: str) -> str:
    """Synchronous edit implementation run via asyncio.to_thread."""
    p = Path(path)
    if not p.is_file():
        return f"Error: file not found: {path}"

    original = p.read_text(encoding="utf-8")
    count = original.count(old_text)
    if count == 0:
        return f"Error: no match found for the provided old_text in {path}"
    if count > 1:
        return f"Error: found {count} matches for old_text in {path}. Provide more context for a unique match."

    updated = original.replace(old_text, new_text, 1)
    p.write_text(updated, encoding="utf-8")

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff) or "No visible diff (whitespace-only change)"


@function_tool
async def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Edit a file by replacing an exact text match with new text.

    Use this tool for editing files instead of shell commands like sed.
    The old_text must match exactly once in the file. Provide enough
    surrounding context for a unique match.

    Args:
        path: The file path to edit.
        old_text: The exact text to find (must match exactly once).
        new_text: The replacement text.
    """
    async with _file_mutation_queue.acquire(path):
        try:
            return await asyncio.to_thread(_edit_file_sync, path, old_text, new_text)
        except (OSError, UnicodeError) as exc:
            return f"Error: unable to edit file {path}: {exc}"


def _read_file_sync(path: str, offset: int, limit: int) -> str:
    """Synchronous read implementation run via asyncio.to_thread."""
    p = Path(path)
    if not p.is_file():
        return f"Error: file not found: {path}"

    offset = max(0, offset)
    limit = max(0, limit)

    all_lines = p.read_text(encoding="utf-8").splitlines()
    lines = all_lines
    if offset > 0:
        lines = lines[offset:]
    if limit > 0:
        lines = lines[:limit]

    if not all_lines:
        return "(empty file)"
    if not lines:
        return "(no lines in range)"

    numbered = [f"{i + offset + 1}\t{line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)


@function_tool
async def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """Read a file and return its content with line numbers.

    Use this tool for reading files instead of shell commands like cat.
    Supports optional pagination via offset and limit.

    Args:
        path: The file path to read.
        offset: Start reading from this line number (0-based). Defaults to 0.
        limit: Maximum number of lines to return. 0 means all lines. Defaults to 0.
    """
    try:
        return await asyncio.to_thread(_read_file_sync, path, offset, limit)
    except UnicodeDecodeError:
        return (
            f"Error: Binary file detected (not UTF-8 text): {path}. "
            "Do not attempt to read binary file contents into the conversation — this will exceed "
            "the context window. To work with this file, use execute_command for metadata "
            "(e.g., file size, type) or use file-path-based upload tools to transfer it directly."
        )
    except OSError as exc:
        return f"Error: unable to read file {path}: {exc}"


def get_reasoning_effort() -> str:
    """Read REASONING_EFFORT env var, defaulting to 'medium'."""
    effort = os.environ.get("REASONING_EFFORT", "medium").lower()
    if effort not in ("low", "medium", "high"):
        effort = "medium"
    return effort


def _estimate_tokens(messages: list) -> int:
    """Rough token estimate: total chars / CHARS_PER_TOKEN."""
    return len(json.dumps(messages, default=str)) // CHARS_PER_TOKEN


def _repair_truncated_json(s: str) -> str | None:
    """Attempt to repair truncated JSON by closing unclosed strings and delimiters.

    Returns the repaired string if valid JSON, or None if repair fails.
    """
    if not s or not s.strip():
        return None
    # Already valid?
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass

    repaired = s
    # Close unclosed string literal: track quote parity (ignoring escaped quotes)
    in_string = False
    i = 0
    while i < len(repaired):
        ch = repaired[i]
        if ch == '\\' and in_string:
            i += 2  # skip escaped character
            continue
        if ch == '"':
            in_string = not in_string
        i += 1
    if in_string:
        repaired += '"'

    # Close unclosed brackets/braces using a delimiter stack
    stack = []
    in_str = False
    i = 0
    while i < len(repaired):
        ch = repaired[i]
        if ch == '\\' and in_str:
            i += 2
            continue
        if ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
            elif ch in ('}', ']'):
                if stack and stack[-1] == ch:
                    stack.pop()
        i += 1

    # Append closing delimiters in reverse order
    repaired += ''.join(reversed(stack))

    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        return None


_TRUNCATION_RECOVERY_MESSAGE = (
    "OUTPUT TRUNCATED: Your previous tool call for '{tool_name}' was truncated because "
    "your response exceeded the output token limit. The arguments were cut off mid-generation, "
    "producing invalid JSON. The tool call failed.\n\n"
    "To avoid this, split large content into multiple smaller tool calls. For example, "
    "write files in sections or use append mode instead of writing everything at once.\n\n"
    "Original error: {original_output}"
)


def _sanitize_tool_calls(messages: list) -> list:
    """Sanitize malformed tool call arguments in Responses API input items.

    Scans for function_call items with invalid JSON arguments and either repairs
    them or replaces with an error placeholder so LiteLLM can serialize the history.
    When a malformed function_call is found, also searches for the matching
    function_call_output to inject a truncation recovery message.
    """
    result = messages
    mutated = False
    # Track call_ids that were sanitized so we can update their outputs
    sanitized_call_ids: dict[str, str] = {}  # call_id -> tool_name

    for idx, item in enumerate(messages):
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        args_str = item.get("arguments")
        if not isinstance(args_str, str) or not args_str:
            continue
        try:
            json.loads(args_str)
            continue  # valid JSON, no repair needed
        except (json.JSONDecodeError, TypeError):
            pass  # invalid JSON — proceed to repair/replace below

        if not mutated:
            result = copy.deepcopy(messages)
            mutated = True

        tool_name = item.get("name", "unknown")
        call_id = item.get("call_id", "")
        repaired = _repair_truncated_json(args_str)
        if repaired is not None:
            result[idx]["arguments"] = repaired
            logger.warning("Sanitized malformed tool call '%s': repaired truncated JSON", tool_name)
            # Only inject truncation recovery message when repair succeeded —
            # a successful repair indicates truncated output (valid JSON prefix),
            # not completely garbled arguments from a different failure mode.
            if call_id:
                sanitized_call_ids[call_id] = tool_name
        else:
            fragment = args_str[:200]
            placeholder = json.dumps({"error": "malformed_arguments", "original_fragment": fragment})
            result[idx]["arguments"] = placeholder
            logger.warning("Sanitized malformed tool call '%s': replaced with error placeholder", tool_name)

    # Inject truncation recovery messages into matching function_call_output items
    if sanitized_call_ids:
        for idx, item in enumerate(result):
            if not isinstance(item, dict) or item.get("type") != "function_call_output":
                continue
            call_id = item.get("call_id", "")
            if call_id not in sanitized_call_ids:
                continue
            tool_name = sanitized_call_ids[call_id]
            original_output = item.get("output", "")
            if isinstance(original_output, list):
                # Extract text from content parts
                original_output = " ".join(
                    p.get("text", "") for p in original_output
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            result[idx]["output"] = _TRUNCATION_RECOVERY_MESSAGE.format(
                tool_name=tool_name,
                original_output=str(original_output),
            )
            logger.warning("Injected truncation recovery message for tool call '%s' (call_id=%s)", tool_name, call_id)

    return result


def _strip_screenshots(messages: list) -> list:
    """Replace old screenshots beyond retention limit with placeholders."""
    image_locations = []
    for msg_idx, msg in enumerate(messages):
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for part_idx, part in enumerate(content):
            if (isinstance(part, dict)
                and part.get("type") == "image_url"
                and isinstance(part.get("image_url"), dict)
                and isinstance(part["image_url"].get("url"), str)
                and part["image_url"]["url"].startswith("data:image/")):
                image_locations.append((msg_idx, part_idx))

    if len(image_locations) <= MAX_RETAINED_SCREENSHOTS:
        return messages

    result = copy.deepcopy(messages)
    to_remove = len(image_locations) - MAX_RETAINED_SCREENSHOTS
    removed_bytes = 0
    for msg_idx, part_idx in image_locations[:to_remove]:
        removed_bytes += len(result[msg_idx]["content"][part_idx].get("image_url", {}).get("url", ""))
        result[msg_idx]["content"][part_idx] = {"type": "text", "text": "[screenshot removed]"}
    logger.info(
        "Screenshots stripped: %d total, %d removed (~%d KB base64), %d retained",
        len(image_locations), to_remove, removed_bytes // 1024, MAX_RETAINED_SCREENSHOTS,
    )
    return result


def _trim_context_window(messages: list) -> list:
    """Drop oldest messages (after the first) until under MAX_CONTEXT_TOKENS."""
    estimated_before = _estimate_tokens(messages)
    if len(messages) <= 2 or estimated_before <= MAX_CONTEXT_TOKENS:
        return messages

    # Keep first message (initial user prompt) and trim from the front of the rest
    first = messages[:1]
    rest = messages[1:]
    while len(rest) > 1 and _estimate_tokens(first + rest) > MAX_CONTEXT_TOKENS:
        rest = rest[1:]

    trimmed = first + rest
    estimated_after = _estimate_tokens(trimmed)
    logger.info(
        "Context window trimmed: %d -> %d messages, ~%d -> ~%d estimated tokens (limit %d)",
        len(messages), len(trimmed), estimated_before, estimated_after, MAX_CONTEXT_TOKENS,
    )
    return trimmed


# --- Context Compaction Helpers (tasks 2.1–2.4) ---

def _serialize_messages_for_summary(messages: list) -> str:
    """Convert a message list to a text representation for the summarization LLM.

    Role labels are added. Tool call arguments, tool results, and message
    content are all truncated to ~2k chars. The output is wrapped in
    <conversation> tags.
    """
    TOOL_RESULT_TRUNCATION = 2000
    parts = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        msg_type = msg.get("type", "")

        if msg_type == "function_call":
            name = msg.get("name", "unknown")
            args = msg.get("arguments", "{}")
            parts.append(f"[TOOL CALL: {name}]\n{str(args)[:TOOL_RESULT_TRUNCATION]}")
        elif msg_type == "function_call_output":
            output = msg.get("output", "")
            if isinstance(output, list):
                output = " ".join(
                    p.get("text", "") for p in output
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            output_str = str(output)
            if len(output_str) > TOOL_RESULT_TRUNCATION:
                output_str = output_str[:TOOL_RESULT_TRUNCATION] + "... [truncated]"
            parts.append(f"[TOOL RESULT]\n{output_str}")
        elif role:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            text_parts.append("[image]")
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = "\n".join(text_parts)
            content_str = str(content)
            if len(content_str) > TOOL_RESULT_TRUNCATION:
                content_str = content_str[:TOOL_RESULT_TRUNCATION] + "... [truncated]"
            parts.append(f"[{role.upper()}]\n{content_str}")

    return "<conversation>\n" + "\n\n".join(parts) + "\n</conversation>"


def _extract_file_operations(messages: list) -> tuple[set[str], set[str]]:
    """Scan tool calls for file read/write operations.

    Extracts paths from file tools (read_file, write_file, edit_file) and
    from execute_command calls using best-effort heuristics.

    Returns (read_files, modified_files) sets.
    """
    read_files: set[str] = set()
    modified_files: set[str] = set()

    for msg in messages:
        if not isinstance(msg, dict) or msg.get("type") != "function_call":
            continue

        tool_name = msg.get("name", "")

        # File tools: extract path directly from arguments
        if tool_name in ("read_file", "write_file", "edit_file"):
            try:
                args = json.loads(msg.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            path = args.get("path", "")
            if path:
                if tool_name == "read_file":
                    read_files.add(path)
                else:
                    modified_files.add(path)
            continue

        if tool_name != "execute_command":
            continue
        try:
            args = json.loads(msg.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue
        command = args.get("command", "")
        if not command:
            continue

        # Read commands: cat, head, tail, less, grep
        # Use shlex.split for correct handling of quoted/escaped paths,
        # then take the last non-flag, non-pure-digit token.
        m = re.search(r'\b(?:cat|head|tail|less|grep)\b', command)
        if m:
            try:
                all_tokens = shlex.split(command)
                verb_pos = next(i for i, t in enumerate(all_tokens) if t in ("cat", "head", "tail", "less", "grep"))
                for tok in reversed(all_tokens[verb_pos + 1:]):
                    if not tok.startswith('-') and not tok.isdigit():
                        read_files.add(tok)
                        break
            except (ValueError, StopIteration):
                pass

        # Write: output redirect (> or >>)
        for m in re.finditer(r'(?:>>?)\s*(\S+)', command):
            modified_files.add(m.group(1))

        # Write: sed -i — last argument
        m = re.search(r'\bsed\b.*\s-i\b.*\s+(\S+)\s*$', command)
        if m:
            modified_files.add(m.group(1))

        # Write: tee
        for m in re.finditer(r'\btee\s+(?:-a\s+)?(\S+)', command):
            modified_files.add(m.group(1))

        # Write: cp / mv — destination is the last non-flag token
        cp_mv_match = re.search(r'\b(cp|mv)\b', command)
        if cp_mv_match:
            try:
                tokens = shlex.split(command)
                # Find the cp/mv verb position, then take last non-flag token after it
                verb_pos = next(i for i, t in enumerate(tokens) if t in ("cp", "mv"))
                positional = [t for t in tokens[verb_pos + 1:] if not t.startswith('-')]
                if positional:
                    modified_files.add(positional[-1])
            except (ValueError, StopIteration):
                pass

    return read_files, modified_files


def _format_file_lists(read_files: set[str], modified_files: set[str], existing_summary: str = "") -> str:
    """Produce <read-files> and <modified-files> XML blocks.

    Merges with file lists already present in existing_summary (if any).
    """
    existing_read: set[str] = set()
    existing_modified: set[str] = set()
    if existing_summary:
        m = re.search(r'<read-files>(.*?)</read-files>', existing_summary, re.DOTALL)
        if m:
            existing_read = {f.strip() for f in m.group(1).splitlines() if f.strip()}
        m = re.search(r'<modified-files>(.*?)</modified-files>', existing_summary, re.DOTALL)
        if m:
            existing_modified = {f.strip() for f in m.group(1).splitlines() if f.strip()}

    all_read = sorted(existing_read | read_files)
    all_modified = sorted(existing_modified | modified_files)

    parts = []
    if all_read:
        parts.append("<read-files>\n" + "\n".join(all_read) + "\n</read-files>")
    if all_modified:
        parts.append("<modified-files>\n" + "\n".join(all_modified) + "\n</modified-files>")
    return "\n".join(parts)


def _is_compaction_summary(message: dict) -> bool:
    """Return True if message is a compaction summary (identified by prefix marker)."""
    if not isinstance(message, dict):
        return False
    content = message.get("content", "")
    if isinstance(content, list):
        content = " ".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return isinstance(content, str) and content.strip().startswith(COMPACTION_SUMMARY_PREFIX)


# --- Core Compaction (tasks 3.1–3.4) ---

def _compact_context(messages: list) -> list:
    """Replace oldest messages with an LLM-generated summary when context exceeds budget.

    On first compaction uses FIRST_COMPACTION_PROMPT; on subsequent compactions
    detects the existing summary and uses MERGE_COMPACTION_PROMPT instead.
    Falls back to _trim_context_window if the summarization call fails.
    """
    estimated_before = _estimate_tokens(messages)
    if len(messages) <= 2 or estimated_before <= MAX_CONTEXT_TOKENS:
        return messages

    logger.info(
        "Context compaction triggered: ~%d estimated tokens (limit %d), %d messages",
        estimated_before, MAX_CONTEXT_TOKENS, len(messages),
    )

    # Find split point: keep ~KEEP_RECENT_TOKENS of the most recent messages
    recent_tokens = 0
    for i in range(len(messages) - 1, -1, -1):
        msg_tokens = _estimate_tokens([messages[i]])
        if recent_tokens + msg_tokens > KEEP_RECENT_TOKENS:
            split_idx = i + 1
            break
        recent_tokens += msg_tokens
    else:
        split_idx = 1

    # Ensure at least one message is summarized and at least one is kept
    split_idx = max(1, min(split_idx, len(messages) - 1))

    to_summarize = messages[:split_idx]
    to_keep = messages[split_idx:]

    # Detect existing compaction summary (task 3.4)
    existing_msg_content: str = ""
    is_subsequent = bool(to_summarize) and _is_compaction_summary(to_summarize[0])
    if is_subsequent:
        raw = to_summarize[0].get("content", "")
        if isinstance(raw, list):
            raw = " ".join(
                p.get("text", "") for p in raw
                if isinstance(p, dict) and p.get("type") == "text"
            )
        existing_msg_content = str(raw)

    # For subsequent compactions exclude the existing summary message from the
    # "new conversation content" — it would otherwise appear twice in the merge
    # prompt (once as existing_summary, again inside conversation_text).
    new_to_summarize = to_summarize[1:] if is_subsequent else to_summarize

    # Extract file operations from messages being summarized
    read_files, modified_files = _extract_file_operations(new_to_summarize)

    # Serialize older messages for the summarization LLM
    conversation_text = _serialize_messages_for_summary(new_to_summarize)

    # Build prompt for the summarization call
    if is_subsequent and existing_msg_content:
        summary_match = re.search(r'<summary>(.*?)</summary>', existing_msg_content, re.DOTALL)
        inner = summary_match.group(1).strip() if summary_match else existing_msg_content
        # Strip file XML blocks before passing to merge prompt
        inner_no_files = re.sub(
            r'\n*<(?:read|modified)-files>.*?</(?:read|modified)-files>',
            '', inner, flags=re.DOTALL,
        ).strip()
        user_content = MERGE_COMPACTION_PROMPT.format(
            existing_summary=inner_no_files,
            conversation=conversation_text,
        )
    else:
        user_content = FIRST_COMPACTION_PROMPT.format(conversation=conversation_text)

    # Call summarization LLM synchronously (task 3.2 + 3.3)
    compaction_model = (
        os.environ.get("COMPACTION_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
    )
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not compaction_model or not api_key:
        logger.info(
            "Context compaction skipped (missing %s) — falling back to trim",
            "OPENAI_MODEL" if not compaction_model else "OPENAI_API_KEY",
        )
        return _trim_context_window(messages)

    compaction_timeout = 30.0
    timeout_raw = os.environ.get("COMPACTION_TIMEOUT_SECONDS", "").strip()
    if timeout_raw:
        try:
            parsed = float(timeout_raw)
            if parsed > 0:
                compaction_timeout = parsed
            else:
                logger.warning("Invalid COMPACTION_TIMEOUT_SECONDS '%s' (must be positive), using %.0fs", timeout_raw, compaction_timeout)
        except ValueError:
            logger.warning("Invalid COMPACTION_TIMEOUT_SECONDS '%s' (not a number), using %.0fs", timeout_raw, compaction_timeout)

    sync_client = OpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        api_key=api_key,
        timeout=compaction_timeout,
    )
    try:
        response = sync_client.chat.completions.create(
            model=compaction_model,
            messages=[
                {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2048,
        )
        summary_text = response.choices[0].message.content or ""
    except Exception:
        logger.warning(
            "Context compaction failed (LLM call error) — falling back to trim", exc_info=True,
        )
        return _trim_context_window(messages)

    if not summary_text.strip():
        logger.warning("Context compaction returned empty summary — falling back to trim")
        return _trim_context_window(messages)

    # Append file lists to summary (task 3.4 carry-forward)
    file_lists = _format_file_lists(read_files, modified_files, existing_msg_content)
    if file_lists:
        summary_text = summary_text.rstrip() + "\n\n" + file_lists

    summary_message = {
        "role": "user",
        "content": (
            COMPACTION_SUMMARY_PREFIX
            + "\n\n<summary>\n"
            + summary_text
            + "\n</summary>"
        ),
    }

    compacted = [summary_message] + list(to_keep)
    estimated_after = _estimate_tokens(compacted)
    logger.info(
        "Context compaction complete: %d -> %d messages, ~%d -> ~%d estimated tokens "
        "(%d messages summarized, model=%s)",
        len(messages), len(compacted), estimated_before, estimated_after,
        len(to_summarize), compaction_model,
    )
    return compacted


def filter_model_input(data: CallModelData) -> ModelInputData:
    """Pre-model filter: sanitize tool calls, strip old screenshots, and compact context."""
    messages = list(data.model_data.input)
    messages = _sanitize_tool_calls(messages)
    messages = _strip_screenshots(messages)
    messages = _compact_context(messages)
    return ModelInputData(input=messages, instructions=data.model_data.instructions)


def write_output_file(output: str, output_dir: str = "/output") -> None:
    """Write output to result.json in output_dir if the directory exists."""
    if not os.path.isdir(output_dir):
        return
    try:
        with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
            f.write(output)
        logger.info("Wrote output to %s/result.json", output_dir)
    except OSError:
        logger.warning("Failed to write output to %s/result.json", output_dir, exc_info=True)


def post_result_callback(output: str) -> None:
    """POST output to the callback URL if configured. Never raises."""
    callback_url = os.environ.get("RESULT_CALLBACK_URL", "")
    callback_token = os.environ.get("RESULT_CALLBACK_TOKEN", "")
    if not callback_url or not callback_token:
        return
    try:
        resp = httpx.post(
            callback_url,
            content=output,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {callback_token}",
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            logger.info("Callback POST succeeded to %s", callback_url)
        else:
            logger.warning("Callback POST returned %d from %s", resp.status_code, callback_url)
    except Exception:
        logger.warning("Callback POST failed to %s", callback_url, exc_info=True)


def _classify_error(exc: Exception) -> str:
    """Classify an exception as transient, non_retryable, or unknown."""
    # Transient: connection, timeout, rate limit
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return "transient"
    # APIStatusError covers HTTP status-based errors
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", 0)
        if status in (429, 502, 503, 504):
            return "transient"
        if isinstance(exc, (BadRequestError, AuthenticationError)):
            return "non_retryable"
        # HTTP 500 with tool conversion message — non-retryable (poisoned history)
        if status == 500:
            msg = str(exc)
            if "Unable to convert openai tool calls" in msg:
                return "non_retryable"
            return "transient"  # other 500s may be transient
        return "non_retryable"
    return "unknown"


MAX_AGENT_RETRIES = 3
AGENT_RETRY_BASE_DELAY = 2  # seconds

# Return type tags for extract_output
_OUTPUT = "output"        # got a result
_NUDGE = "nudge"          # should nudge and retry
_EMPTY_FAIL = "empty_fail"  # empty output, should fail


def extract_output(submitted_result: dict | None, raw_text: str, new_items: list, nudge_attempted: bool) -> tuple[str, str | None]:
    """Extract task output using priority: submit_result > text JSON > raw text > nudge > fail.

    Returns (tag, output_json) where tag is one of _OUTPUT, _NUDGE, _EMPTY_FAIL.
    For _OUTPUT, output_json is the JSON string to emit.
    For _NUDGE and _EMPTY_FAIL, output_json is None.
    """
    # Priority 1: submit_result tool call
    if submitted_result is not None:
        return _OUTPUT, json.dumps(submitted_result)

    # Priority 2: text-based JSON fallback (backward compat)
    if raw_text.strip():
        parsed = extract_json(raw_text)
        if parsed:
            return _OUTPUT, TaskRunnerOutput(**parsed).model_dump_json()

    # Priority 3: raw text fallback
    if raw_text.strip():
        return _OUTPUT, json.dumps({"status": "completed", "result": raw_text, "questions": []})

    # Priority 4: empty response — check for nudge opportunity
    tool_call_items = [
        item for item in new_items
        if getattr(item, "type", None) == "tool_call_output_item"
    ]
    if tool_call_items and not nudge_attempted:
        return _NUDGE, None

    return _EMPTY_FAIL, None


async def main():
    # 1. Read and validate environment variables
    env = read_env_vars()

    # 2. Read input files
    user_prompt = _read_startup_file(env["USER_PROMPT_PATH"], "user prompt")
    system_prompt = _read_startup_file(env["SYSTEM_PROMPT_PATH"], "system prompt")
    mcp_config_raw = _read_startup_file(env["MCP_CONFIGURATION_PATH"], "MCP configuration")

    # 3. Configure OpenAI client for LiteLLM
    # Use Chat Completions API instead of Responses API — LiteLLM's /responses
    # endpoint does not pass through function tools (github.com/BerriAI/litellm/issues/15371)
    set_default_openai_api("chat_completions")
    client = AsyncOpenAI(base_url=env["OPENAI_BASE_URL"], api_key=env["OPENAI_API_KEY"])
    set_default_openai_client(client)

    # 4. Parse MCP config and connect to servers with lazy tool loading
    mcp_config = parse_mcp_config(mcp_config_raw)
    hot_list = get_hot_list()
    tool_filter = create_tool_filter()

    async with AsyncExitStack() as stack:
        # Connect without tool_filter so list_tools() works for catalog building
        mcp_servers = await connect_mcp_servers(mcp_config, stack)
        if mcp_servers:
            server_names = [s.name for s in mcp_servers]
            emit_event("mcp_connected", {"servers": server_names, "count": len(server_names)})

        # Build compact tool catalog and collect all known tool names
        catalog, all_known_tools = await build_tool_catalog(mcp_servers, hot_list)
        logger.info("Tool catalog: %d known tools, catalog length=%d chars", len(all_known_tools), len(catalog))
        if all_known_tools:
            logger.debug("All known tools: %s", ", ".join(sorted(all_known_tools)))
        if catalog:
            logger.debug("Catalog content:\n%s", catalog)

        # Now attach the tool filter to each server for agent runtime filtering
        for server in mcp_servers:
            server.tool_filter = tool_filter

        # Build system prompt with file tool guidance, catalog, and output instructions
        full_instructions = system_prompt
        full_instructions += FILE_TOOL_GUIDANCE
        if catalog:
            full_instructions += "\n\n" + catalog
        full_instructions += OUTPUT_INSTRUCTIONS

        # Create tool visibility context initialized with hot list
        visibility_ctx = ToolVisibilityContext(
            enabled_tools=set(hot_list),
            all_known_tools=all_known_tools,
        )

        # 5. Create agent with reasoning settings and model-aware max output tokens
        reasoning_effort = get_reasoning_effort()
        max_output_tokens = resolve_max_output_tokens(env["OPENAI_MODEL"])
        logger.info("Max output tokens: %d (model=%s)", max_output_tokens, env["OPENAI_MODEL"])
        agent = Agent(
            name="TaskRunner",
            instructions=full_instructions,
            model=env["OPENAI_MODEL"],
            tools=[execute_command, write_file, edit_file, read_file, discover_tools, submit_result],
            mcp_servers=mcp_servers if mcp_servers else [],
            model_settings=ModelSettings(
                max_tokens=max_output_tokens,
                reasoning=Reasoning(effort=reasoning_effort, generate_summary="auto"),
            ),
        )

        try:
            max_turns = int(os.environ.get("MAX_TURNS", "30"))
        except ValueError:
            emit_event("error", {
                "message": f"Invalid MAX_TURNS value: {os.environ.get('MAX_TURNS')}",
                "error_type": "non_retryable",
                "error_class": "ValueError",
            })
            sys.exit(1)
        # Use OpenAIProvider directly to bypass MultiProvider's slash-based prefix
        # parsing. This ensures model names containing slashes (e.g. "bedrock/gpt-oss:20b")
        # are passed through to the configured OpenAI client (pointing at LiteLLM) as-is.
        run_config = RunConfig(
            model_provider=OpenAIProvider(),
            call_model_input_filter=filter_model_input,
        )

        attempt = 0
        nudge_attempted = False
        original_user_prompt = user_prompt
        while attempt < MAX_AGENT_RETRIES:
            attempt += 1
            try:
                hooks = StreamEventEmitter()
                result = Runner.run_streamed(agent, user_prompt, context=visibility_ctx, max_turns=max_turns, hooks=hooks, run_config=run_config)

                # Iterate streaming events, emitting thinking/reasoning to stderr
                async for event in result.stream_events():
                    if event.type == "raw_response_event":
                        continue
                    elif event.type == "run_item_stream_event":
                        turn_id = hooks._current_turn_id
                        if event.item.type == "message_output_item":
                            text = ItemHelpers.text_message_output(event.item)
                            if text:
                                data: dict = {"text": text}
                                if turn_id:
                                    data["turn_id"] = turn_id
                                emit_event("thinking", data)
                        elif event.item.type == "reasoning_item":
                            summary = getattr(event.item, "summary", None)
                            if summary:
                                texts = []
                                for part in summary:
                                    t = getattr(part, "text", None)
                                    if t:
                                        texts.append(t)
                                if texts:
                                    data = {"text": "\n".join(texts)}
                                    if turn_id:
                                        data["turn_id"] = turn_id
                                    emit_event("reasoning", data)
                        elif event.name == "tool_called" and event.item.type == "tool_call_item":
                            raw = event.item.raw_item
                            tool_name = getattr(raw, "name", "unknown")
                            args_str = getattr(raw, "arguments", "{}")
                            try:
                                args = json.loads(args_str)
                            except (json.JSONDecodeError, TypeError):
                                args = {"raw": args_str}
                            tc_data: dict = {"tool": tool_name, "args": args}
                            if turn_id:
                                tc_data["turn_id"] = turn_id
                            emit_event("tool_call", tc_data)

                # Log summary of tool calls from run items
                tool_call_count = sum(
                    1 for item in result.new_items
                    if getattr(item, "type", None) == "tool_call_output_item"
                )
                if tool_call_count:
                    logger.info("TOOL_SUMMARY total_tool_calls=%d", tool_call_count)

                # Extract output using priority: submit_result > text JSON > raw text > nudge > fail
                final_output = result.final_output
                raw_text = str(final_output) if final_output else ""

                tag, output = extract_output(
                    visibility_ctx.submitted_result, raw_text, result.new_items, nudge_attempted,
                )

                if tag == _NUDGE:
                    nudge_attempted = True
                    logger.info("Empty output after tool calls — nudging agent to call submit_result")
                    nudge_msg = (
                        "You completed your work but didn't deliver the result to the user. "
                        "Call submit_result now with a comprehensive summary of what you found or accomplished."
                    )
                    user_prompt = original_user_prompt + "\n\n" + nudge_msg
                    visibility_ctx.submitted_result = None
                    attempt -= 1  # nudge does not count toward retry limit
                    continue

                if tag == _EMPTY_FAIL:
                    emit_event("error", {
                        "message": "LLM returned empty response",
                        "error_type": "empty_response",
                        "error_class": "EmptyResponseError",
                    })
                    logger.error("Agent produced empty output — treating as failure")
                    failed_output = json.dumps({
                        "status": "failed",
                        "result": "",
                        "error": "LLM returned empty response",
                        "questions": [],
                    })
                    print(failed_output)
                    post_result_callback(failed_output)
                    write_output_file(failed_output)
                    sys.exit(1)

                # Output to stdout
                print(output)

                # Push result to backend via callback if configured
                post_result_callback(output)

                # Write output to /output/result.json if the directory exists
                write_output_file(output)

                sys.exit(0)

            except ModelBehaviorError as e:
                # Auto-enable undiscovered tools: if the model called a known MCP tool
                # without discover_tools first, enable it and retry instead of failing.
                # This does NOT count toward the retry limit since it's a recoverable
                # protocol issue, not a real error. The finite set of tools bounds retries.
                match = re.search(r"Tool (\S+) not found in agent", str(e))
                tool_name = match.group(1) if match else None
                if tool_name and tool_name in visibility_ctx.all_known_tools:
                    visibility_ctx.enabled_tools.add(tool_name)
                    logger.warning("Auto-enabled undiscovered tool '%s', retrying", tool_name)
                    attempt -= 1  # Don't count toward retry limit
                    continue
                # Unknown tool or unparseable error — fail
                emit_event("error", {
                    "message": str(e),
                    "error_type": "unknown",
                    "error_class": "ModelBehaviorError",
                })
                logger.error("Agent execution failed (attempt %d/%d, unknown, ModelBehaviorError): %s",
                             attempt, MAX_AGENT_RETRIES, e)
                sys.exit(1)

            except Exception as e:
                error_type = _classify_error(e)
                error_class = type(e).__name__

                if error_type == "transient" and attempt < MAX_AGENT_RETRIES:
                    delay = AGENT_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.info("Transient error (attempt %d/%d, %s), retrying in %ds: %s",
                                attempt, MAX_AGENT_RETRIES, error_class, delay, e)
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable, unknown, or final attempt — fail
                emit_event("error", {
                    "message": str(e),
                    "error_type": error_type,
                    "error_class": error_class,
                })
                logger.error("Agent execution failed (attempt %d/%d, %s, %s): %s",
                             attempt, MAX_AGENT_RETRIES, error_type, error_class, e)
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
