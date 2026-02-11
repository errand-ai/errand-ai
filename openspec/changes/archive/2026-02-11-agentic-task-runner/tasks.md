## 1. Environment variable rename (LITELLM_ → OPENAI_)

- [x] 1.1 Rename `LITELLM_BASE_URL` to `OPENAI_BASE_URL` and `LITELLM_API_KEY` to `OPENAI_API_KEY` in `backend/llm.py`
- [x] 1.2 Update `docker-compose.yml` to use `OPENAI_BASE_URL` and `OPENAI_API_KEY` for backend and worker services
- [x] 1.3 Update `.env` to rename `LITELLM_BASE_URL` and `LITELLM_API_KEY` to `OPENAI_BASE_URL` and `OPENAI_API_KEY`
- [x] 1.4 Update Helm templates (`backend-deployment.yaml`, `worker-deployment.yaml`) and `values.yaml` to use `OPENAI_BASE_URL` and `OPENAI_API_KEY`
- [x] 1.5 Add `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables to the worker service in `docker-compose.yml` and Helm `worker-deployment.yaml`
- [x] 1.6 Update backend tests that reference `LITELLM_BASE_URL` or `LITELLM_API_KEY`
- [x] 1.7 Update the `admin-settings-api` spec scenario text from "LITELLM" to "OPENAI" (already done in delta spec)

## 2. Task processing model setting and MCP config validation

- [x] 2.1 Add "Task Processing Model" dropdown to `SettingsPage.vue` — load from `task_processing_model` setting, default to `claude-sonnet-4-5-20250929`, save on change via `PUT /api/settings`
- [x] 2.2 Relabel existing LLM model dropdown to "Title Generation Model" in `SettingsPage.vue`
- [x] 2.3 Add MCP configuration validation to `SettingsPage.vue` — validate JSON structure matches `{"mcpServers": {"<name>": {"url": "...", "headers": {...}}}}`, reject entries with `command`/`args` (STDIO), reject entries missing `url`, reject malformed JSON; display specific error messages per server name
- [x] 2.4 Add frontend tests for the task processing model dropdown (load, default, save, error states)
- [x] 2.5 Add frontend tests for MCP configuration validation (valid HTTP Streaming, STDIO rejected, missing url rejected, mixed valid/invalid rejected, malformed JSON rejected)

## 3. Worker reads settings and passes to container

- [x] 3.1 Update `worker.py` to read `task_processing_model`, `system_prompt`, and `mcp_servers` settings from the database before creating the container
- [x] 3.2 Update `_run_in_container()` to set environment variables on the container: `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from worker env), `OPENAI_MODEL` (from `task_processing_model` setting), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, `MCP_CONFIGURATION_PATH=/workspace/mcp.json`
- [x] 3.3 Update `_run_in_container()` to copy three files into the container: `prompt.txt` (task description), `system_prompt.txt` (from settings), `mcp.json` (from settings)
- [x] 3.4 Add backend tests for worker settings retrieval and container environment variable setup

## 4. Worker parses structured output

- [x] 4.1 Define a Pydantic model `TaskRunnerOutput` with fields: `status` (Literal["completed", "needs_input"]), `result` (str), `questions` (list[str]) in the worker module
- [x] 4.2 Update the worker to parse stdout as JSON matching `TaskRunnerOutput` after container exit code 0 — on parse failure, treat as error and schedule retry
- [x] 4.3 When parsed status is `needs_input`, move task to `review` and add "Input Needed" tag
- [x] 4.4 When parsed status is `completed`, move task to `completed` with result stored in `output`
- [x] 4.5 Add backend tests for structured output parsing: valid completed, valid needs_input, invalid JSON, non-zero exit code

## 5. Task runner Dockerfile and Python app

- [x] 5.1 Create `task-runner/requirements.txt` with `openai-agents`, `mcp`, `pydantic` dependencies
- [x] 5.2 Rewrite `task-runner/Dockerfile` with multi-stage build: Python slim stage for pip install, `gcr.io/distroless/python3-debian12:nonroot` final stage, entrypoint `["python3", "/app/main.py"]`
- [x] 5.3 Create `task-runner/main.py` — read environment variables (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `USER_PROMPT_PATH`, `SYSTEM_PROMPT_PATH`, `MCP_CONFIGURATION_PATH`), validate all present, read file contents
- [x] 5.4 Implement the overarching structured output system prompt in `task-runner/main.py` — instructs the agent to produce JSON with `status`, `result`, `questions` fields
- [x] 5.5 Implement MCP server connection from `MCP_CONFIGURATION_PATH` JSON — parse `{"mcpServers": {name: {url, headers?}}}` format, connect to HTTP Streaming MCP servers, skip entries with `command`/`args` (STDIO) with a warning, and load tools
- [x] 5.6 Implement the ReAct agent using OpenAI Agents SDK — create agent with system prompt + overarching prompt, model, and MCP tools; run with user prompt; capture structured output
- [x] 5.7 Output structured JSON to stdout, all logging to stderr, exit code 0 on success, 1 on error
- [x] 5.8 Add task runner unit tests for input validation, structured output formatting, and error handling

## 6. Version bump and integration testing

- [x] 6.1 Bump VERSION file
- [x] 6.2 Run full backend test suite, fix any failures
- [x] 6.3 Run full frontend test suite, fix any failures
- [x] 6.4 Test with `docker compose up --build` — verify task runner builds, worker passes correct env vars, and end-to-end task processing works
