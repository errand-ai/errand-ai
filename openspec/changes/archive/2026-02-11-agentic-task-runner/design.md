## Context

The task runner currently echoes back the prompt text — it has no LLM processing. The worker copies `prompt.txt` and `mcp.json` into the container and captures stdout. Environment variables use the `LITELLM_` prefix inconsistently across backend, docker-compose, and Helm. The settings page has a single LLM model dropdown used for title generation; there is no setting for the model used during task processing.

## Goals / Non-Goals

**Goals:**
- Add a task processing model setting (separate from the title-generation model) with a UI dropdown
- Standardise environment variable naming from `LITELLM_*` to `OPENAI_*`
- Pass LLM credentials, model, prompts, and MCP config from worker to task runner via environment variables and file paths
- Replace the stub task runner with a Python ReAct agent using OpenAI Agents SDK
- Define a structured output schema so the worker can parse results and handle "needs input" responses
- Rebuild the task runner image with a Python distroless base

**Non-Goals:**
- Multi-agent orchestration or agent-to-agent handoff — single agent with ReAct loop
- MCP server discovery or dynamic registration — config comes from settings
- Streaming output back to the UI during execution — output captured after completion
- Changing the title-generation model default or logic

## Decisions

### Decision 1: OpenAI Agents SDK for the ReAct agent
**Choice:** Use the OpenAI Agents SDK (`openai-agents`) to implement the ReAct agentic loop in the task runner.
**Alternatives considered:**
- **LangGraph**: More powerful graph-based orchestration but overkill for a linear task runner. Heavy dependency footprint (entire LangChain ecosystem). Steep learning curve.
- **Claude Agent SDK**: Requires Node.js runtime alongside Python, adding significant container bloat. Not natively OpenAI-compatible.
- **Raw OpenAI SDK**: Minimal dependencies but requires building the entire ReAct loop, tool execution, and retry logic from scratch.

**Rationale:** The OpenAI Agents SDK has native MCP support (both stdio and SSE), works directly with LiteLLM's OpenAI-compatible endpoint, has a minimal dependency footprint, and handles the ReAct loop automatically. It's right-sized for a container that processes a single prompt per run.

### Decision 2: Environment variables for credentials, file paths for content
**Choice:** Pass `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` as environment variables. Pass prompts and MCP config as files copied into the container, with paths in `USER_PROMPT_PATH`, `SYSTEM_PROMPT_PATH`, and `MCP_CONFIGURATION_PATH` environment variables.
**Alternative:** Pass everything as environment variables (base64-encoded for large content). Rejected because prompts and MCP configs can be large and environment variables have size limits on some systems.

### Decision 3: Structured output schema with Pydantic
**Choice:** Define a Pydantic model for the agent's output with fields: `status` (completed | needs_input), `result` (string, the main output), and `questions` (list of strings, populated when status is needs_input). The agent's overarching system prompt instructs it to produce JSON matching this schema. The task runner prints the JSON to stdout.
**Alternative:** Use exit codes to signal different states. Rejected because exit codes can't carry structured data and limit extensibility.

### Decision 4: Worker parses structured output to determine next action
**Choice:** After the container exits, the worker parses stdout as JSON matching the output schema. If `status` is `completed`, the worker moves the task to `completed` with the result stored in `output`. If `status` is `needs_input`, the worker moves the task to `review` and adds an "Input Needed" tag. If parsing fails, the worker treats it as a failure and schedules a retry.
**Alternative:** Have the task runner call back to the API directly. Rejected because the task runner should be stateless and not need API credentials or network access to the backend.

### Decision 5: Python distroless base image
**Choice:** Use `gcr.io/distroless/python3-debian12:nonroot` as the task runner base image, with a multi-stage build that installs dependencies via pip in the build stage and copies the installed packages to the final image.
**Alternative:** Use a full Python slim image. Rejected because distroless has a smaller attack surface and is consistent with the existing task runner image approach.

### Decision 6: Separate `task_processing_model` setting key
**Choice:** Store the task processing model in a new settings key `task_processing_model` (default: `claude-sonnet-4-5-20250929`), separate from `llm_model` (used for title generation).
**Alternative:** Reuse the `llm_model` key for both. Rejected because title generation uses a cheap fast model while task processing may use a more capable (expensive) model — users need independent control.

### Decision 7: HTTP Streaming only for MCP servers (no STDIO)
**Choice:** The task runner SHALL only support HTTP Streaming MCP servers. STDIO-based MCP servers are explicitly disallowed. The MCP configuration format uses `{"mcpServers": {"<name>": {"url": "<endpoint>", "headers": {…}}}}` — each server entry has a `url` (required) and optional `headers` map. The settings page SHALL validate any configuration entry and reject entries that match the STDIO pattern (containing `command` or `args` fields instead of `url`).
**Alternative:** Support both STDIO and HTTP Streaming. Rejected because the task runner executes in a securely locked-down distroless sandbox container that cannot download or execute arbitrary binaries required by STDIO MCP servers.

## Risks / Trade-offs

- **Risk:** OpenAI Agents SDK is pre-1.0 and may have breaking changes. → Mitigation: Pin the dependency version. The SDK is actively maintained and production-used.
- **Risk:** MCP server config from settings may reference servers the task runner can't reach (network isolation in DinD). → Mitigation: Document that MCP servers must be network-accessible from the DinD container.
- **Risk:** Large structured output may exceed the 1MB truncation limit in the worker. → Mitigation: The overarching system prompt instructs the agent to keep output concise. The truncation logic already exists.
- **Risk:** Environment variable rename is breaking. → Mitigation: Single coordinated change across `.env`, docker-compose, Helm, and backend code. Version bump signals the breaking change.
