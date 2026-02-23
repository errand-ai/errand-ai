## MODIFIED Requirements

### Requirement: Worker executes tasks via ContainerRuntime

The worker SHALL execute each task by delegating container operations to the configured `ContainerRuntime` implementation (see `container-runtime` spec). The worker SHALL: (1) retrieve the `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, `hindsight_url`, and `hindsight_bank_id` settings from the database, and query the `skills` and `skill_files` tables for all skills and their attached files, (2) if Playwright is configured, start the Playwright sidecar via the runtime-appropriate mechanism (Docker: create container in DinD with `network_mode="host"`; K8s: Playwright is a pre-deployed sidecar on the worker pod — the worker health-checks it but does not start it), (3) build the environment variables (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, `MCP_CONFIGURATION_PATH=/workspace/mcp.json`) and input files, (4) inject a `playwright` entry into the MCP server configuration — this injection SHALL NOT overwrite a database-configured `playwright` entry, (5) if skills exist, write Agent Skills directories to `/workspace/skills/<name>/` containing `SKILL.md` files and any attached files from the `skill_files` table, (6) if `ssh_private_key` is present in settings, inject SSH credentials (the private key and an SSH config file), (7) if Hindsight is configured, recall relevant memories via the Hindsight REST API and inject the results into the system prompt, and inject a `hindsight` MCP server entry into the MCP configuration, (8) if the GitHub platform integration is connected, load the GitHub credentials from the `platform_credentials` table and inject `GH_TOKEN` into the container environment, (9) call `runtime.prepare(image, env, files, output_dir)` to create the container/Job with injected files, (10) call `runtime.run(handle)` and publish each yielded log line to the Valkey channel `task_logs:{task_id}` using a synchronous Redis client, followed by a `task_log_end` sentinel when the stream completes, **(10b) periodically update `heartbeat_at` on the task row during the log-streaming loop**, (11) call `runtime.result(handle)` to get `(exit_code, stdout, stderr)`, (12) parse the structured output from stdout using robust JSON extraction (try direct JSON parse, then code fence extraction anywhere in stdout, then first-`{`-to-last-`}` extraction — the first strategy that produces a valid `TaskRunnerOutput` is used; if none succeed, schedule retry), (13) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (14) call `runtime.cleanup(handle)`, (15) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

**Heartbeat updates:** During the log-streaming loop (step 10), the worker SHALL update `heartbeat_at = NOW()` on the task row at a regular interval (every 60 seconds). The update SHALL use a direct `UPDATE tasks SET heartbeat_at = NOW() WHERE id = :task_id` statement via a fresh async session wrapped in `asyncio.run()` from the executor thread, or alternatively via the synchronous Redis client publishing a heartbeat message that the async caller processes. The heartbeat update SHALL NOT block log streaming — if the DB update fails, the worker SHALL log a warning and continue.

The worker SHALL also set `heartbeat_at = NOW()` when initially setting the task to `status = "running"`, so the zombie cleanup has a baseline timestamp from the start of execution.

All other behaviour (Playwright container cleanup, image pre-pull, callback tokens, callback TTL refresh, callback result override, settings retrieval, system prompt construction, MCP configuration injection, Perplexity injection, Hindsight recall, skills injection, SSH credential injection, env var substitution, log publishing to Valkey, output parsing, retry logic, repeating task rescheduling, WebSocket event publishing) SHALL remain unchanged.

#### Scenario: Heartbeat set when task starts running

- **WHEN** the worker sets a task to `status="running"`
- **THEN** `heartbeat_at` is set to the current timestamp

#### Scenario: Heartbeat updated during log streaming

- **WHEN** the worker is streaming logs from a running task-runner container
- **THEN** `heartbeat_at` is updated every 60 seconds

#### Scenario: Heartbeat update failure does not block execution

- **WHEN** the heartbeat DB update fails (e.g., transient connection error)
- **THEN** the worker logs a warning and continues streaming logs and processing the task
