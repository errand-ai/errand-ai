## Why

The task runner currently just echoes the prompt back — it has no LLM processing capability. We need to implement an agentic architecture where the task runner uses a ReAct (Reason and Act) pattern to process user prompts with LLM and MCP tool access, producing structured output that the worker can parse to determine next steps (completed, needs user input, etc.). Additionally, environment variable naming is inconsistent (`LITELLM_` prefix) and needs standardising to `OPENAI_`, and the settings page needs a second model selector for the task processing model (separate from the existing title-generation model).

## What Changes

- Add a "Task Processing Model" setting (dropdown) on the settings page, defaulting to `claude-sonnet-4-5-20250929`, stored separately from the existing LLM model setting (which remains for title generation)
- **BREAKING**: Rename all `LITELLM_BASE_URL` references to `OPENAI_BASE_URL` and `LITELLM_API_KEY` to `OPENAI_API_KEY` across backend, docker-compose, Helm templates, and `.env`
- Update the worker to read system prompt, MCP server config, and the task processing model from settings, then pass them to the task runner container via environment variables (`OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `SYSTEM_PROMPT_PATH`, `MCP_CONFIGURATION_PATH`, `USER_PROMPT_PATH`)
- Rebuild the task runner image using the Python distroless base image instead of static distroless
- Create a Python application inside the task runner that implements a ReAct agentic loop using the OpenAI Agents SDK: reads environment variables, loads prompts and MCP config, runs the agent, and outputs structured results
- Add an overarching system prompt layer that enforces structured output format so the worker can parse results
- When the agent determines user clarification is needed, the worker parses this from the structured output, moves the task to `review` status, and adds an "Input Needed" tag

### Framework Choice: OpenAI Agents SDK

The OpenAI Agents SDK is recommended over LangGraph, Claude Agent SDK, and raw OpenAI SDK for these reasons:

1. **Native MCP support** — built-in integration with both stdio and SSE transports, handles MCP server lifecycle automatically
2. **LiteLLM proxy compatible** — works directly with OpenAI-compatible API endpoints, zero configuration friction
3. **Lightweight** — minimal dependency footprint keeps the container small; no Node.js runtime required (unlike Claude Agent SDK)
4. **Built-in ReAct loop** — handles the reason-act-observe cycle, tool invocation, and multi-turn conversation automatically
5. **Structured output** — native Pydantic model support through OpenAI's structured outputs API
6. **Right-sized** — LangGraph's graph-based orchestration is overkill for a linear task runner; raw SDK requires too much boilerplate

## Capabilities

### New Capabilities
- `task-runner-agent`: Python application implementing the ReAct agentic loop using OpenAI Agents SDK — reads environment variables for prompts, model, and MCP config, processes the user prompt, produces structured output

### Modified Capabilities
- `admin-settings-ui`: Add "Task Processing Model" dropdown setting separate from the existing title-generation model
- `admin-settings-api`: Add `task_processing_model` setting key with default value, API endpoints to get/set it
- `task-worker`: Rename `LITELLM_*` env vars to `OPENAI_*`, read task processing model and settings from DB, pass `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `SYSTEM_PROMPT_PATH`, `MCP_CONFIGURATION_PATH`, `USER_PROMPT_PATH` to task runner container, parse structured output to handle "needs input" responses by moving task to review with "Input Needed" tag
- `task-runner-image`: Change base image from static distroless to Python distroless, add Python application as entrypoint
- `llm-integration`: Rename `LITELLM_BASE_URL`/`LITELLM_API_KEY` to `OPENAI_BASE_URL`/`OPENAI_API_KEY` in backend code
- `helm-deployment`: Update Helm templates and values for renamed env vars (`OPENAI_BASE_URL`, `OPENAI_API_KEY`)
- `local-dev-environment`: Update docker-compose.yml and .env for renamed env vars

## Impact

- **Backend**: `worker.py` (container env vars, structured output parsing, settings retrieval), `llm.py` (env var rename), `main.py` (new settings endpoint)
- **Frontend**: `SettingsPage.vue` (new dropdown), `useApi.ts` (new API calls)
- **Task Runner**: Complete rewrite — new Python app with OpenAI Agents SDK, new Dockerfile with Python distroless base
- **Infrastructure**: `docker-compose.yml`, `helm/content-manager/values.yaml`, Helm deployment templates (env var renames), `.env`
- **Dependencies**: New Python dependencies in task runner: `openai-agents`, `mcp`, `pydantic`
- **Breaking**: All `LITELLM_*` env vars renamed to `OPENAI_*` — requires updating `.env` files, Helm values overrides, and any deployment configs
