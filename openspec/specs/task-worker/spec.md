## Requirements

### Requirement: Worker executes tasks via ContainerRuntime

The worker SHALL execute each task by delegating container operations to the configured `ContainerRuntime` implementation (see `container-runtime` spec). The worker SHALL: (1) retrieve the `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, `hindsight_url`, and `hindsight_bank_id` settings from the database, and query the `skills` and `skill_files` tables for all skills and their attached files, (2) if Playwright is configured, start the Playwright sidecar via the runtime-appropriate mechanism (Docker: create container in DinD with `network_mode="host"`; K8s: Playwright is a pre-deployed sidecar on the worker pod — the worker health-checks it but does not start it), (3) build the environment variables (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, `MCP_CONFIGURATION_PATH=/workspace/mcp.json`) and input files, (4) inject a `playwright` entry into the MCP server configuration — this injection SHALL NOT overwrite a database-configured `playwright` entry, (5) if skills exist, write Agent Skills directories to `/workspace/skills/<name>/` containing `SKILL.md` files and any attached files from the `skill_files` table, (6) if `ssh_private_key` is present in settings, inject SSH credentials (the private key and an SSH config file), (7) if Hindsight is configured, recall relevant memories via the Hindsight REST API and inject the results into the system prompt, and inject a `hindsight` MCP server entry into the MCP configuration, (8) call `runtime.prepare(image, env, files, output_dir)` to create the container/Job with injected files, (9) call `runtime.run(handle)` and publish each yielded log line to the Valkey channel `task_logs:{task_id}` using a synchronous Redis client, followed by a `task_log_end` sentinel when the stream completes, (10) call `runtime.result(handle)` to get `(exit_code, stdout, stderr)`, (11) parse the structured output from stdout using robust JSON extraction (try direct JSON parse, then code fence extraction anywhere in stdout, then first-`{`-to-last-`}` extraction — the first strategy that produces a valid `TaskRunnerOutput` is used; if none succeed, schedule retry), (12) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (13) call `runtime.cleanup(handle)`, (14) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

The Playwright container cleanup in Docker mode SHALL occur in a `finally` block to ensure the sidecar is removed even if the task-runner fails, times out, or the worker encounters an error. If the Playwright container has already been removed (e.g. OOM-killed and auto-removed), the cleanup SHALL log a warning and continue without raising an error. In K8s mode, Playwright is managed by the pod spec and does not need explicit cleanup by the worker.

The worker SHALL pre-pull required Docker images on startup only when using `DockerRuntime`. The images to pre-pull are the task-runner image (`TASK_RUNNER_IMAGE`) and, if configured, the Playwright MCP image (`PLAYWRIGHT_MCP_IMAGE`). For each image, the worker SHALL check if it is already available locally via `images.get()` and only pull if not found. When using `KubernetesRuntime`, the K8s node's container runtime handles image pulling and no pre-pull occurs.

The worker SHALL generate a one-time callback token using `secrets.token_hex(32)` and store it in Valkey at key `task_result_token:{task_id}` with a TTL of 30 minutes. The worker SHALL derive the callback URL by stripping the `/mcp` suffix from the existing `BACKEND_MCP_URL` environment variable and appending `/api/internal/task-result/{task_id}`. The worker SHALL pass `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` as environment variables to the task-runner container alongside the existing env vars. If Valkey is unavailable when storing the token, the worker SHALL log a warning and omit both callback env vars (graceful degradation — the task-runner will skip the callback POST).

During the log-streaming loop, the worker SHALL refresh the token TTL by calling `EXPIRE` on the `task_result_token:{task_id}` key every 15 minutes, resetting the TTL to 30 minutes. This ensures long-running tasks retain a valid callback token for the duration of execution.

After `runtime.result()` returns, the worker SHALL check Valkey for a callback result at key `task_result:{task_id}`. If found, the worker SHALL use the callback result as stdout (overriding the value from `runtime.result()`). The worker SHALL then delete both `task_result:{task_id}` and `task_result_token:{task_id}` from Valkey to clean up. If the callback result is not found in Valkey, the worker SHALL proceed with the stdout from `runtime.result()` as before (existing fallback). All Valkey operations in this flow SHALL use the synchronous Redis client and SHALL swallow exceptions to avoid interrupting task processing.

All other behaviour (settings retrieval, system prompt construction, MCP configuration injection, Perplexity injection, Hindsight recall, skills injection, SSH credential injection, env var substitution, log publishing to Valkey, output parsing, retry logic, repeating task rescheduling, WebSocket event publishing) SHALL remain unchanged.

The worker SHALL read Playwright configuration from environment variables:
- `PLAYWRIGHT_MCP_IMAGE`: The Playwright MCP container image (if not set, Playwright is skipped)
- `PLAYWRIGHT_MEMORY_LIMIT`: Docker memory limit for the Playwright container (default: `512m`)
- `PLAYWRIGHT_PORT`: Port the Playwright MCP server listens on (default: `8931`)
- `PLAYWRIGHT_STARTUP_TIMEOUT`: Seconds to wait for the health check (default: `30`)

The health check SHALL derive the target hostname from the `DOCKER_HOST` environment variable using URL parsing (e.g. `tcp://dind:2375` yields hostname `dind`, `tcp://localhost:2375` yields `localhost`). If `DOCKER_HOST` is not set, the health check SHALL default to `localhost`. The health check SHALL poll `http://{host}:{port}/mcp` until a successful HTTP response is received or the timeout is reached. If the health check times out, the worker SHALL log an error, remove the Playwright container, and proceed with the task-runner without Playwright (degraded mode — the `playwright` MCP entry SHALL NOT be injected into the config).

The synchronous Redis client used for log publishing SHALL be created at the start of `process_task_in_container` using the same `VALKEY_URL` environment variable as the async client. The client SHALL be closed in a `finally` block to ensure cleanup. If the sync Redis connection fails, the worker SHALL log a warning and continue execution without interrupting task processing.

The SSH config file SHALL contain one entry per host in the `git_ssh_hosts` setting, following this pattern:

```
Host <hostname>
    IdentityFile ~/.ssh/id_rsa.agent
    User git
    StrictHostKeyChecking accept-new
```

If `ssh_private_key` is not present in settings or is empty, the worker SHALL skip the SSH credential injection step and proceed without SSH configuration. This allows the task runner to still use git over HTTPS for public repositories.

Before writing `mcp.json`, the worker SHALL check whether the `USE_PERPLEXITY` environment variable is set to `"true"`. If so, the worker SHALL inject a `"perplexity-ask"` entry into the `mcpServers` object of the MCP configuration with the value `{"url": "$PERPLEXITY_URL"}`. This injection SHALL occur before the existing `substitute_env_vars()` call, so that `$PERPLEXITY_URL` is resolved to the actual service URL. If the MCP configuration from the database already contains a `"perplexity-ask"` key, the database value SHALL take precedence (the injected entry SHALL NOT overwrite it).

When `USE_PERPLEXITY` is `"true"`, the worker SHALL also append a Perplexity usage instruction block to the system prompt before writing `system_prompt.txt` into the container. The instruction block SHALL be appended after the admin-configured system prompt content (separated by two newlines) and SHALL instruct the LLM that it has access to the `perplexity-ask` MCP tool for looking up current information online, conducting web research, or reasoning about topics that require context beyond its training data.

When Hindsight is configured (via `HINDSIGHT_URL` environment variable or `hindsight_url` admin setting), the worker SHALL: (a) call `POST {hindsight_url}/v1/default/banks/{bank_id}/memories/recall` with a JSON body `{"query": "<task title>. <task description>", "max_tokens": 2048}` to retrieve relevant memories, (b) if the recall returns content, append a `## Relevant Context from Memory` section to the system prompt containing the recalled text, (c) inject a `"hindsight"` entry into the `mcpServers` object with `{"url": "{hindsight_url}/mcp/{bank_id}/"}`, and (d) append a memory usage instruction block to the system prompt instructing the agent to use `retain`, `recall`, and `reflect` tools for persistent memory. If the recall API call fails, the worker SHALL log a warning and continue without memory context. The Hindsight MCP injection SHALL NOT overwrite a database-configured `"hindsight"` entry.

When skills exist in the database, the worker SHALL append a skill manifest section to the system prompt after any Perplexity block. The worker SHALL NOT inject the backend MCP server into the MCP configuration for skill purposes. The worker SHALL NOT append the legacy "call list_skills" directive.

Before writing the `mcp_servers` configuration as `/workspace/mcp.json`, the worker SHALL perform environment variable substitution on all string values within the JSON structure. The substitution SHALL support two syntaxes: `$VARIABLE_NAME` and `${VARIABLE_NAME}`, where `VARIABLE_NAME` matches the pattern `[A-Za-z_][A-Za-z0-9_]*`. The worker SHALL resolve variable references against its own process environment (`os.environ`). If a referenced variable does not exist in the worker's environment, the placeholder SHALL be left unchanged in the output. Substitution SHALL only operate on string values within the JSON structure — keys, numbers, booleans, and nulls SHALL NOT be modified.

The worker SHALL store the captured stderr in the task's `runner_logs` field for all execution outcomes: successful completion, needs_input, retry on failure, and retry on parse error. The `runner_logs` field SHALL be written in every UPDATE statement that modifies the task after container execution.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `runner_logs`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship and the `runner_logs` field.

#### Scenario: Callback token generated and passed to container

- **WHEN** the worker prepares a task-runner container and Valkey is available
- **THEN** the worker generates a 64-character hex token, stores it at `task_result_token:{task_id}` with 30-min TTL, and passes `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` to the container

#### Scenario: Callback URL derived from BACKEND_MCP_URL

- **WHEN** `BACKEND_MCP_URL` is `http://errand-backend:8000/mcp` and the task ID is `abc-123`
- **THEN** `RESULT_CALLBACK_URL` is `http://errand-backend:8000/api/internal/task-result/abc-123`

#### Scenario: Token TTL refreshed during long-running tasks

- **WHEN** a task runs for more than 15 minutes and the worker is streaming logs
- **THEN** the worker calls `EXPIRE task_result_token:{task_id} 1800` every 15 minutes to keep the token valid

#### Scenario: Callback result overrides runtime stdout

- **WHEN** the task-runner POSTs its result to the callback and the worker reads it from Valkey after `runtime.result()`
- **THEN** the worker uses the Valkey callback result as stdout instead of the value from `runtime.result()`

#### Scenario: Fallback to runtime stdout when callback absent

- **WHEN** the task-runner does not POST a callback result (env vars absent, network failure, or timeout)
- **THEN** the worker uses stdout from `runtime.result()` as before

#### Scenario: Token and result cleaned up after reading

- **WHEN** the worker reads (or attempts to read) the callback result from Valkey
- **THEN** the worker deletes both `task_result:{task_id}` and `task_result_token:{task_id}` regardless of whether the callback arrived

#### Scenario: Valkey unavailable during token storage

- **WHEN** Valkey is not reachable when the worker tries to store the callback token
- **THEN** the worker logs a warning, omits `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` from container env vars, and proceeds with task execution (task-runner will skip callback)

#### Scenario: Docker runtime processes task (unchanged behaviour)

- **WHEN** `CONTAINER_RUNTIME` is `docker` (or unset) and the worker processes a task
- **THEN** the worker creates a Docker container in DinD, streams stderr to Valkey, captures stdout for parsing, and cleans up the container — identical to current behaviour

#### Scenario: Kubernetes runtime processes task

- **WHEN** `CONTAINER_RUNTIME` is `kubernetes` and the worker processes a task
- **THEN** the worker creates a K8s Job with a ConfigMap for input files, streams pod logs to Valkey, reads structured output from `/output/result.json`, and cleans up the Job and ConfigMap

#### Scenario: Images pre-pulled only in Docker mode

- **WHEN** the worker starts with `CONTAINER_RUNTIME=docker`
- **THEN** it pre-pulls the task-runner and Playwright images via Docker SDK, skipping images already available locally

#### Scenario: No image pre-pull in K8s mode

- **WHEN** the worker starts with `CONTAINER_RUNTIME=kubernetes`
- **THEN** no image pre-pull occurs (K8s handles image pulling)

#### Scenario: Playwright MCP sidecar created for each task (Docker mode)

- **WHEN** the worker processes a task in Docker mode
- **THEN** a Playwright MCP container is created in DinD with `network_mode="host"`, the configured memory limit, and the command `--port <port> --host 0.0.0.0 --allowed-hosts *`

#### Scenario: Playwright health check uses pod IP in K8s mode

- **WHEN** the worker uses `KubernetesRuntime` and Playwright is configured as a sidecar
- **THEN** the worker health-checks Playwright at `http://localhost:<port>/mcp` (same pod) and passes `http://<pod-ip>:<port>/mcp` to the task-runner Job

#### Scenario: Playwright health check succeeds

- **WHEN** the Playwright container starts and responds to the health check within the timeout
- **THEN** the worker injects a `playwright` MCP entry into the task-runner's `mcp.json` and proceeds with task execution

#### Scenario: Playwright health check times out

- **WHEN** the Playwright container does not respond within the configured timeout
- **THEN** the worker logs an error, removes the Playwright container (Docker mode), and runs the task-runner without the `playwright` MCP entry (degraded mode)

#### Scenario: Playwright container OOM-killed during task execution

- **WHEN** the Playwright container exceeds its memory limit and is OOM-killed while the task-runner is running
- **THEN** the task-runner receives MCP connection errors for Playwright tools, and the worker's cleanup step logs a warning and continues

#### Scenario: Playwright container cleaned up after task completion (Docker mode)

- **WHEN** the task-runner container exits (success or failure) in Docker mode
- **THEN** the worker stops and removes the Playwright container in a `finally` block

#### Scenario: Database-configured playwright entry takes precedence

- **WHEN** the admin has configured a `playwright` key in the MCP servers setting
- **THEN** the worker does not overwrite it with the auto-injected Playwright MCP URL

#### Scenario: Hindsight memories pre-loaded into system prompt

- **WHEN** the worker processes a task with Hindsight configured and the recall API returns relevant memories
- **THEN** the system prompt includes a `## Relevant Context from Memory` section before any MCP tool instructions

#### Scenario: Hindsight MCP server injected into configuration

- **WHEN** the worker processes a task with `HINDSIGHT_URL=http://hindsight-api:8888` and bank ID `errand-tasks`
- **THEN** the MCP configuration includes `{"hindsight": {"url": "http://hindsight-api:8888/mcp/errand-tasks/"}}`

#### Scenario: Hindsight recall failure does not block task

- **WHEN** the worker attempts to recall from Hindsight and the API returns an error or times out
- **THEN** the worker logs a warning and proceeds with task execution without memory context

#### Scenario: Hindsight not configured

- **WHEN** `HINDSIGHT_URL` is not set and `hindsight_url` admin setting does not exist
- **THEN** the worker skips Hindsight recall and MCP injection entirely

#### Scenario: Stderr streamed in real-time during execution

- **WHEN** the worker processes a task with id `abc-123` and the container emits stderr lines during execution
- **THEN** each stderr chunk is published to Valkey channel `task_logs:abc-123` as `{"event": "task_log", "line": "<chunk>"}` as it arrives, before the container exits

#### Scenario: End sentinel published after streaming

- **WHEN** the worker finishes streaming stderr for a task (container has exited)
- **THEN** the worker publishes `{"event": "task_log_end"}` to the per-task Valkey channel

#### Scenario: Sync Redis client created and cleaned up per task

- **WHEN** the worker calls `process_task_in_container`
- **THEN** a synchronous `redis.Redis` client is created from `VALKEY_URL` at the start and closed in a `finally` block

#### Scenario: Sync Redis failure does not interrupt task

- **WHEN** the worker is streaming stderr and the sync Redis publish fails
- **THEN** the worker logs a warning and continues processing the task normally

#### Scenario: Full logs still captured after streaming

- **WHEN** the worker finishes streaming stderr and the container has exited
- **THEN** the worker captures full stdout and stderr via `container.logs()` for JSON parsing and `runner_logs` storage, exactly as before
