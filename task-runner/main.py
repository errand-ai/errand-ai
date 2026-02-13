"""Task runner agent — reads environment variables and files, runs a ReAct agent, outputs structured JSON."""

import asyncio
import json
import logging
import os
import re
import sys
from contextlib import AsyncExitStack

from openai import AsyncOpenAI
from pydantic import BaseModel

from agents import Agent, Runner, set_default_openai_client, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp

# All logging to stderr; LOG_LEVEL env var controls verbosity (default: INFO)
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

# Disable tracing (no OpenAI tracing endpoint in sandboxed container)
set_tracing_disabled(True)

OVERARCHING_PROMPT = """You MUST produce your final response as a JSON object with exactly this schema:
{"status": "completed" | "needs_input", "result": "<your response text>", "questions": ["<question>"]}

Rules:
- If you are asked to do something at timed intervals (like every 30 minutes), just perform the task now and do not be concerned with the next time the task needs to be completed. 
- If you have fully addressed the user's request, set status to "completed", put your answer in "result", and set "questions" to an empty list [].
- If you cannot proceed without user clarification, set status to "needs_input", explain what is unclear in "result", and list specific questions in "questions".
- Output ONLY the JSON object as your final response. No markdown fences, no extra text.
- Keep your result concise and focused."""


class TaskRunnerOutput(BaseModel):
    status: str
    result: str
    questions: list[str] = []


def extract_json(text: str) -> str | None:
    """Extract a valid TaskRunnerOutput JSON string from LLM output.

    Tries three strategies in order:
    1. Direct parse of the full text
    2. Extract content from a markdown code fence (```json...``` or ```...```) anywhere in text
    3. Extract substring from first '{' to last '}'

    Returns the JSON string if valid TaskRunnerOutput, otherwise None.
    """
    stripped = text.strip()

    # Strategy 1: direct parse
    try:
        TaskRunnerOutput.model_validate_json(stripped)
        return stripped
    except Exception:
        pass

    # Strategy 2: code fence extraction
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", stripped, re.DOTALL)
    if fence_match:
        fenced_content = fence_match.group(1).strip()
        try:
            TaskRunnerOutput.model_validate_json(fenced_content)
            return fenced_content
        except Exception:
            pass

    # Strategy 3: first '{' to last '}'
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        brace_content = stripped[first_brace:last_brace + 1]
        try:
            TaskRunnerOutput.model_validate_json(brace_content)
            return brace_content
        except Exception:
            pass

    return None


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
            params = {"url": url}
            if headers:
                params["headers"] = headers

            server = MCPServerStreamableHttp(
                name=name,
                params=params,
                cache_tools_list=True,
            )
            connected = await stack.enter_async_context(server)
            servers.append(connected)
            logger.info("Connected to MCP server '%s' at %s", name, url)
        except Exception as e:
            logger.warning("Failed to connect to MCP server '%s': %s", name, e)

    return servers


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

        # 5. Build combined system prompt
        combined_instructions = system_prompt + "\n\n" + OVERARCHING_PROMPT if system_prompt.strip() else OVERARCHING_PROMPT

        # 6. Create and run agent
        agent = Agent(
            name="TaskRunner",
            instructions=combined_instructions,
            model=env["OPENAI_MODEL"],
            mcp_servers=mcp_servers if mcp_servers else [],
        )

        try:
            result = await Runner.run(agent, user_prompt)
            raw_output = result.final_output

            # Extract structured JSON from LLM output (handles preamble text, code fences, etc.)
            extracted = extract_json(raw_output)
            if extracted is not None:
                parsed = TaskRunnerOutput.model_validate_json(extracted)
                output = parsed.model_dump_json()
            else:
                # If no valid structured JSON found, wrap as completed
                output = json.dumps({
                    "status": "completed",
                    "result": raw_output,
                    "questions": [],
                })

            # 7. Output to stdout
            print(output)
            sys.exit(0)

        except Exception as e:
            logger.error("Agent execution failed: %s", e)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
