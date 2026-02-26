## MODIFIED Requirements

### Requirement: Worker executes tasks via ContainerRuntime
The worker SHALL execute each task by delegating container operations to the configured `ContainerRuntime` implementation (see `container-runtime` spec). The worker SHALL: (1) retrieve the `task_processing_model`, `system_prompt`, `mcp_servers`, `litellm_mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, `hindsight_url`, and `hindsight_bank_id` settings from the database, and query the `skills` and `skill_files` tables for all skills and their attached files, (1b) if the task has a non-null `profile_id`, read the corresponding `TaskProfile` row and apply profile overrides to the resolved settings using the inheritance rules: non-null scalar fields override globals, `null` list fields inherit all defaults, `[]` list fields clear to empty, non-empty list fields use only the specified subset, (2) if Playwright is configured, start the Playwright sidecar via the runtime-appropriate mechanism (Docker: create container in DinD with `network_mode="host"`; K8s: Playwright is a pre-deployed sidecar on the worker pod — the worker health-checks it but does not start it), (3) build the environment variables (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, `MCP_CONFIGURATION_PATH=/workspace/mcp.json`) and input files, (4) inject a `playwright` entry into the MCP server configuration — this injection SHALL NOT overwrite a database-configured `playwright` entry, (5) if skills exist (after profile filtering), write Agent Skills directories to `/workspace/skills/<name>/` containing `SKILL.md` files and any attached files from the `skill_files` table, (6) if `ssh_private_key` is present in settings, inject SSH credentials (the private key and an SSH config file), (7) if Hindsight is configured, recall relevant memories via the Hindsight REST API and inject the results into the system prompt, and inject a `hindsight` MCP server entry into the MCP configuration, (8) if the GitHub platform integration is connected, load the GitHub credentials from the `platform_credentials` table and inject `GH_TOKEN` into the container environment, (9) call `runtime.prepare(image, env, files, output_dir)` to create the container/Job with injected files, (10) call `runtime.run(handle)` and publish each yielded log line to the Valkey channel `task_logs:{task_id}` using a synchronous Redis client, followed by a `task_log_end` sentinel when the stream completes, (10b) periodically update `heartbeat_at` on the task row during the log-streaming loop, (11) call `runtime.result(handle)` to get `(exit_code, stdout, stderr)`, (12) parse the structured output from stdout using robust JSON extraction, (13) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (14) call `runtime.cleanup(handle)`, (15) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task that preserves the `profile_id` (see `repeating-task-rescheduling` spec).

If the task references a `profile_id` that no longer exists in the database (profile was deleted), the worker SHALL log a warning and proceed with default settings (as if `profile_id` were null).

All other behaviour (heartbeat updates, Playwright management, Hindsight recall, SSH injection, env var substitution, log publishing, output parsing, retry logic, callback tokens, WebSocket events) SHALL remain unchanged.

#### Scenario: Task with profile resolved at execution time
- **WHEN** the worker dequeues a task with `profile_id` referencing "email-triage" (model: "claude-haiku-4-5-20251001", mcp_servers: ["gmail"])
- **THEN** the worker uses "claude-haiku-4-5-20251001" as the model and only "gmail" as user-configured MCP server

#### Scenario: Task with null profile uses global settings
- **WHEN** the worker dequeues a task with `profile_id = null`
- **THEN** the worker uses global settings identically to current behavior

#### Scenario: Task references deleted profile
- **WHEN** the worker dequeues a task whose `profile_id` references a non-existent profile
- **THEN** the worker logs a warning and uses global settings

#### Scenario: Repeating task rescheduled with profile
- **WHEN** a repeating task with `profile_id = "abc-123"` completes and is rescheduled
- **THEN** the newly created task has `profile_id = "abc-123"`

#### Scenario: Profile with system_prompt override
- **WHEN** the task's profile has `system_prompt: "You are an email assistant"`
- **THEN** the base system prompt passed to the task runner is "You are an email assistant" instead of the global system prompt (Hindsight, skills, and repo context blocks are still appended)

#### Scenario: Profile with max_turns override
- **WHEN** the task's profile has `max_turns: 10`
- **THEN** the container receives `MAX_TURNS=10` environment variable

#### Scenario: Profile with reasoning_effort override
- **WHEN** the task's profile has `reasoning_effort: "low"`
- **THEN** the container receives `REASONING_EFFORT=low` environment variable

#### Scenario: Profile with skill_ids subset
- **WHEN** the task's profile has `skill_ids: ["uuid-1"]` and the database has 5 skills
- **THEN** only the skill with id "uuid-1" is included in the skills archive and manifest

#### Scenario: Profile with skill_ids empty
- **WHEN** the task's profile has `skill_ids: []`
- **THEN** no skills are included (empty manifest, no archive)
