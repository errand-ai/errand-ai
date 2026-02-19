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

from openai import AsyncOpenAI
from openai.types.shared import Reasoning
from pydantic import BaseModel

from agents import Agent, ItemHelpers, ModelSettings, RunConfig, Runner, RunHooks, function_tool, set_default_openai_client, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp
from agents.run import CallModelData, ModelInputData

# All logging to stderr; LOG_LEVEL env var controls verbosity (default: INFO)
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

# Disable tracing (no OpenAI tracing endpoint in sandboxed container)
set_tracing_disabled(True)

TOOL_RESULT_MAX_LENGTH = 500


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

IMPORTANT: The "result" field is the ONLY output the user will see. You MUST include the full content you produced (text, song lyrics, code, analysis, etc.) directly in the "result" field. Do NOT just describe what you did — include the actual content. Use markdown formatting for readability.

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

            server = MCPServerStreamableHttp(
                name=name,
                params=params,
                cache_tools_list=True,
                client_session_timeout_seconds=300,
            )
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
    """Pre-model filter: strip old screenshots and trim context window."""
    messages = list(data.model_data.input)
    messages = _strip_screenshots(messages)
    messages = _trim_context_window(messages)
    return ModelInputData(input=messages, instructions=data.model_data.instructions)


def write_output_file(output: str, output_dir: str = "/output") -> None:
    """Write output to result.json in output_dir if the directory exists."""
    if not os.path.isdir(output_dir):
        return
    try:
        with open(os.path.join(output_dir, "result.json"), "w") as f:
            f.write(output)
        logger.info("Wrote output to %s/result.json", output_dir)
    except OSError:
        logger.warning("Failed to write output to %s/result.json", output_dir, exc_info=True)


async def main():
    # 1. Read and validate environment variables
    env = read_env_vars()

    # 2. Read input files
    user_prompt = read_file(env["USER_PROMPT_PATH"], "user prompt")
    system_prompt = read_file(env["SYSTEM_PROMPT_PATH"], "system prompt")
    mcp_config_raw = read_file(env["MCP_CONFIGURATION_PATH"], "MCP configuration")

    # 3. Configure OpenAI client for LiteLLM
    client = AsyncOpenAI(base_url=env["OPENAI_BASE_URL"], api_key=env["OPENAI_API_KEY"])
    set_default_openai_client(client)

    # 4. Parse MCP config and connect to servers
    mcp_config = parse_mcp_config(mcp_config_raw)

    async with AsyncExitStack() as stack:
        mcp_servers = await connect_mcp_servers(mcp_config, stack)

        # 5. Create agent with reasoning settings
        reasoning_effort = get_reasoning_effort()
        agent = Agent(
            name="TaskRunner",
            instructions=system_prompt + OUTPUT_INSTRUCTIONS,
            model=env["OPENAI_MODEL"],
            tools=[execute_command],
            mcp_servers=mcp_servers if mcp_servers else [],
            model_settings=ModelSettings(
                reasoning=Reasoning(effort=reasoning_effort, generate_summary="auto"),
            ),
        )

        try:
            max_turns = int(os.environ.get("MAX_TURNS", "30"))
            run_config = RunConfig(call_model_input_filter=filter_model_input)
            result = Runner.run_streamed(agent, user_prompt, max_turns=max_turns, hooks=StreamEventEmitter(), run_config=run_config)

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

            # Write output to /output/result.json if the directory exists
            write_output_file(output)

            sys.exit(0)

        except Exception as e:
            emit_event("error", {"message": str(e)})
            logger.error("Agent execution failed: %s", e)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
