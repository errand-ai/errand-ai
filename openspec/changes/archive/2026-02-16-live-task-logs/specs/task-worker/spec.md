## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle with `network_mode="host"` (so the task runner shares DinD's network namespace). The worker SHALL: (1) pull the task runner image, (2) retrieve the `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, and `git_ssh_hosts` settings from the database, and query the `skills` and `skill_files` tables for all skills and their attached files, (3) create the container from the task runner image with environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from the worker's own environment), `OPENAI_MODEL` (from the `task_processing_model` setting, defaulting to `claude-sonnet-4-5-20250929`), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, and `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, (4) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/system_prompt.txt` containing the system prompt from settings, `/workspace/mcp.json` containing the MCP server configuration from settings **after environment variable substitution**) into the stopped container via `put_archive()`, (5) if skills exist, write Agent Skills directories to `/workspace/skills/<name>/` containing `SKILL.md` files and any attached files from the `skill_files` table, (6) if `ssh_private_key` is present in settings, copy SSH credentials into the container: the private key at `/home/nonroot/.ssh/id_rsa.agent` with file permissions 600, and an SSH config file at `/home/nonroot/.ssh/config` with file permissions 644, (7) start the container, (8) **stream stderr in real-time** by iterating `container.logs(stream=True, follow=True, stderr=True, stdout=False)` and publishing each chunk to the per-task Valkey channel `task_logs:{task_id}` using a synchronous Redis client, followed by a `task_log_end` sentinel when the stream completes, (9) retrieve the container exit code via `container.wait()`, (10) capture full stdout and stderr via `container.logs()`, (11) parse the structured output from stdout using robust JSON extraction (try direct JSON parse, then code fence extraction anywhere in stdout, then first-`{`-to-last-`}` extraction — the first strategy that produces a valid `TaskRunnerOutput` is used; if none succeed, schedule retry), (12) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (13) remove the container, (14) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

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

When skills exist in the database, the worker SHALL append a skill manifest section to the system prompt after any Perplexity block. The worker SHALL NOT inject the backend MCP server into the MCP configuration for skill purposes. The worker SHALL NOT append the legacy "call list_skills" directive.

Before writing the `mcp_servers` configuration as `/workspace/mcp.json`, the worker SHALL perform environment variable substitution on all string values within the JSON structure. The substitution SHALL support two syntaxes: `$VARIABLE_NAME` and `${VARIABLE_NAME}`, where `VARIABLE_NAME` matches the pattern `[A-Za-z_][A-Za-z0-9_]*`. The worker SHALL resolve variable references against its own process environment (`os.environ`). If a referenced variable does not exist in the worker's environment, the placeholder SHALL be left unchanged in the output. Substitution SHALL only operate on string values within the JSON structure — keys, numbers, booleans, and nulls SHALL NOT be modified.

The worker SHALL store the captured stderr in the task's `runner_logs` field for all execution outcomes: successful completion, needs_input, retry on failure, and retry on parse error. The `runner_logs` field SHALL be written in every UPDATE statement that modifies the task after container execution.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `runner_logs`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship and the `runner_logs` field.

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
