"""Task runner agent — reads environment variables and files, runs a ReAct agent, outputs structured JSON."""

import asyncio
import copy
import json
import logging
import os
import re
import subprocess
import sys
from contextlib import AsyncExitStack

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError, BadRequestError, AuthenticationError, APIStatusError
from openai.types.shared import Reasoning
from pydantic import BaseModel

from agents import Agent, ItemHelpers, ModelSettings, RunConfig, Runner, RunHooks, function_tool, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp
from agents.run import CallModelData, ModelInputData

from tool_registry import ToolVisibilityContext, build_tool_catalog, create_tool_filter, discover_tools, get_hot_list

# All logging to stderr; LOG_LEVEL env var controls verbosity (default: INFO)
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

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

    async def on_agent_start(self, context, agent) -> None:
        emit_event("agent_start", {"agent": agent.name})

    async def on_tool_start(self, context, agent, tool) -> None:
        # tool_call event is emitted from the streaming loop (tool_called) with full arguments
        pass

    async def on_tool_end(self, context, agent, tool, result) -> None:
        result_str = str(result)
        original_length = len(result_str)
        emit_event("tool_result", {
            "tool": tool.name,
            "output": _truncate(result_str),
            "length": original_length,
        })

    async def on_agent_end(self, context, agent, output) -> None:
        try:
            output_data = output.model_dump() if hasattr(output, "model_dump") else {"raw": str(output)}
        except Exception:
            output_data = {"raw": str(output)}
        emit_event("agent_end", {"output": output_data})

    async def on_llm_start(self, context, agent, *args, **kwargs) -> None:
        logger.debug("LLM call starting for agent %s", agent.name)

    async def on_llm_end(self, context, agent, *args, **kwargs) -> None:
        logger.debug("LLM call completed for agent %s", agent.name)


class TaskRunnerOutput(BaseModel):
    status: str
    result: str
    questions: list[str] = []


OUTPUT_INSTRUCTIONS = """

When you have completed the task, respond with ONLY a JSON object (no markdown, no extra text):
{"status": "completed", "result": "<your detailed result>", "questions": []}

IMPORTANT: The "result" field is the ONLY output the user will see. You MUST include the full content you produced (text, code, analysis, creative writing, etc.) directly in the "result" field. Do NOT just describe what you did — include the actual content. Use markdown formatting for readability.

If you need more information, respond with:
{"status": "needs_input", "result": "<what you've done so far>", "questions": ["<question 1>", "<question 2>"]}
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


def read_file(path: str, name: str) -> str:
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


@function_tool
def execute_command(command: str, working_directory: str = "/workspace") -> str:
    """Execute a shell command and return the combined stdout and stderr output.

    Use this tool to run commands like git clone, ls, cat, grep, etc.

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
        return output
    except subprocess.TimeoutExpired:
        return f"Command timed out after {COMMAND_TIMEOUT} seconds"
    except Exception as e:
        return f"Error executing command: {e}"


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
        else:
            fragment = args_str[:200]
            placeholder = json.dumps({"error": "malformed_arguments", "original_fragment": fragment})
            result[idx]["arguments"] = placeholder
            logger.warning("Sanitized malformed tool call '%s': replaced with error placeholder", tool_name)

        if call_id:
            sanitized_call_ids[call_id] = tool_name

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


def filter_model_input(data: CallModelData) -> ModelInputData:
    """Pre-model filter: sanitize tool calls, strip old screenshots, and trim context window."""
    messages = list(data.model_data.input)
    messages = _sanitize_tool_calls(messages)
    messages = _strip_screenshots(messages)
    messages = _trim_context_window(messages)
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


async def main():
    # 1. Read and validate environment variables
    env = read_env_vars()

    # 2. Read input files
    user_prompt = read_file(env["USER_PROMPT_PATH"], "user prompt")
    system_prompt = read_file(env["SYSTEM_PROMPT_PATH"], "system prompt")
    mcp_config_raw = read_file(env["MCP_CONFIGURATION_PATH"], "MCP configuration")

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

        # Build system prompt with catalog injected before output instructions
        full_instructions = system_prompt
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
            tools=[execute_command, discover_tools],
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
        run_config = RunConfig(call_model_input_filter=filter_model_input)

        for attempt in range(1, MAX_AGENT_RETRIES + 1):
            try:
                result = Runner.run_streamed(agent, user_prompt, context=visibility_ctx, max_turns=max_turns, hooks=StreamEventEmitter(), run_config=run_config)

                # Iterate streaming events, emitting thinking/reasoning to stderr
                async for event in result.stream_events():
                    if event.type == "raw_response_event":
                        continue
                    elif event.type == "run_item_stream_event":
                        if event.item.type == "message_output_item":
                            text = ItemHelpers.text_message_output(event.item)
                            if text:
                                emit_event("thinking", {"text": text})
                        elif event.item.type == "reasoning_item":
                            summary = getattr(event.item, "summary", None)
                            if summary:
                                texts = []
                                for part in summary:
                                    t = getattr(part, "text", None)
                                    if t:
                                        texts.append(t)
                                if texts:
                                    emit_event("reasoning", {"text": "\n".join(texts)})
                        elif event.name == "tool_called" and event.item.type == "tool_call_item":
                            raw = event.item.raw_item
                            tool_name = getattr(raw, "name", "unknown")
                            args_str = getattr(raw, "arguments", "{}")
                            try:
                                args = json.loads(args_str)
                            except (json.JSONDecodeError, TypeError):
                                args = {"raw": args_str}
                            emit_event("tool_call", {"tool": tool_name, "args": args})

                # Log summary of tool calls from run items
                tool_call_count = sum(
                    1 for item in result.new_items
                    if getattr(item, "type", None) == "tool_call_output_item"
                )
                if tool_call_count:
                    logger.info("TOOL_SUMMARY total_tool_calls=%d", tool_call_count)

                # Parse structured output from agent's final text response
                final_output = result.final_output
                raw_text = str(final_output) if final_output else ""
                parsed = extract_json(raw_text)
                if parsed:
                    output = TaskRunnerOutput(**parsed).model_dump_json()
                else:
                    # Fallback: wrap raw output as completed
                    output = json.dumps({
                        "status": "completed",
                        "result": raw_text,
                        "questions": [],
                    })

                # Output to stdout
                print(output)

                # Push result to backend via callback if configured
                post_result_callback(output)

                # Write output to /output/result.json if the directory exists
                write_output_file(output)

                sys.exit(0)

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
