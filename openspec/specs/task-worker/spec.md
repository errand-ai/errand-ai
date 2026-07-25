## Purpose

Worker process that dequeues tasks, resolves profiles, prepares containers, streams logs, and handles output parsing and rescheduling.

## Requirements

### Requirement: Worker polls for pending tasks
The worker SHALL poll the database for tasks with status `pending` using `SELECT ... FOR UPDATE SKIP LOCKED` to safely dequeue a single task without contention with other workers. Tasks SHALL be dequeued in order of `position` ascending, with ties broken by `created_at` ascending, so that user-prioritised tasks are processed first.

#### Scenario: Task available
- **WHEN** the worker polls and a task with status `pending` exists
- **THEN** the worker acquires the task with the lowest position value, sets its status to `running`, and begins processing

#### Scenario: No tasks available
- **WHEN** the worker polls and no tasks have status `pending`
- **THEN** the worker waits for a configurable interval before polling again

#### Scenario: Multiple pending tasks with different positions
- **WHEN** the worker polls and tasks exist at positions 1, 3, and 5 in the Pending column
- **THEN** the worker acquires the task at position 1 (highest priority)

### Requirement: Worker processes one task at a time
Each worker instance SHALL process exactly one task at a time. The worker MUST complete or fail the current task before polling for the next one.

#### Scenario: Sequential processing
- **WHEN** the worker finishes processing a task
- **THEN** it sets the task status to `completed` and immediately polls for the next task

### Requirement: Worker marks failed tasks
If task processing raises an exception, the worker SHALL set the task status to `failed` and continue polling for the next task. The worker process MUST NOT crash on task failure.

#### Scenario: Task processing fails
- **WHEN** processing a task raises an unhandled exception
- **THEN** the worker sets the task status to `failed`, logs the error, and continues polling

### Requirement: Worker uses same database models as backend
The worker SHALL import database models and connection configuration from the shared backend Python package to prevent schema drift.

#### Scenario: Shared models
- **WHEN** the backend adds a new column to the tasks table
- **THEN** the worker sees the same column because it uses the same SQLAlchemy model

### Requirement: Worker graceful shutdown
The worker SHALL handle SIGTERM by finishing the current task (if any) before exiting. It MUST NOT abandon a task in `running` status on shutdown.

#### Scenario: SIGTERM during task processing
- **WHEN** the worker receives SIGTERM while processing a task
- **THEN** it finishes processing the current task, updates its status, and then exits

#### Scenario: SIGTERM while idle
- **WHEN** the worker receives SIGTERM while waiting to poll
- **THEN** it exits immediately

### Requirement: Worker executes tasks in DinD containers

Before writing `mcp.json`, the worker SHALL check whether Perplexity platform credentials exist in the database by calling `load_credentials("perplexity", session)`. If credentials exist, the worker SHALL inject a `"perplexity-ask"` entry into the `mcpServers` object of the MCP configuration with the value `{"url": "$PERPLEXITY_URL"}`. This injection SHALL occur before the existing `substitute_env_vars()` call, so that `$PERPLEXITY_URL` is resolved to the actual service URL. If the MCP configuration from the database already contains a `"perplexity-ask"` key, the database value SHALL take precedence (the injected entry SHALL NOT overwrite it). The worker SHALL NOT use the `USE_PERPLEXITY` environment variable for this check.

When Perplexity credentials exist in the database, the worker SHALL also append a Perplexity usage instruction block to the system prompt before writing `system_prompt.txt` into the container. The instruction block SHALL be appended after the admin-configured system prompt content (separated by two newlines) and SHALL instruct the LLM that it has access to the `perplexity-ask` MCP tool for looking up current information online, conducting web research, or reasoning about topics that require context beyond its training data.

#### Scenario: Perplexity injected when platform credentials exist
- **WHEN** the worker processes a task and Perplexity platform credentials exist in the database
- **THEN** the MCP configuration includes a `"perplexity-ask"` entry with the Perplexity MCP service URL, and the system prompt includes Perplexity usage instructions

#### Scenario: Perplexity not injected when no credentials
- **WHEN** the worker processes a task and no Perplexity platform credentials exist in the database
- **THEN** the MCP configuration does not include a `"perplexity-ask"` entry and the system prompt does not include Perplexity instructions

#### Scenario: Database MCP config takes precedence
- **WHEN** the worker processes a task, Perplexity credentials exist, and the admin-configured MCP servers already contain a `"perplexity-ask"` entry
- **THEN** the admin-configured entry is preserved and the worker does not overwrite it

#### Scenario: USE_PERPLEXITY env var no longer used
- **WHEN** the worker processes a task
- **THEN** the worker does not check the `USE_PERPLEXITY` environment variable for Perplexity configuration

### Requirement: Worker connects to DinD on startup
The worker SHALL connect to the Docker daemon via the `DOCKER_HOST` environment variable using the Docker SDK for Python. On startup, the worker SHALL retry the connection with exponential backoff (starting at 1 second, up to 30 seconds) until the DinD daemon is ready. If the connection cannot be established after the retry period, the worker SHALL exit with an error.

#### Scenario: DinD ready on startup
- **WHEN** the worker starts and the DinD daemon is already running
- **THEN** the worker connects to Docker and begins polling for tasks

#### Scenario: DinD not yet ready
- **WHEN** the worker starts and the DinD daemon is still initialising
- **THEN** the worker retries the connection with exponential backoff until DinD responds

#### Scenario: DinD unreachable
- **WHEN** the worker starts and `DOCKER_HOST` is not set or the daemon cannot be reached after retries
- **THEN** the worker logs an error and exits with a non-zero exit code

### Requirement: Worker reads settings from database
The worker SHALL read the MCP server configuration and credentials from the `settings` table using the SQLAlchemy `Setting` model. The MCP configuration SHALL be read from the setting with key `mcp_servers`. The credentials SHALL be read from the setting with key `credentials` (a list of `{"key": "...", "value": "..."}` objects). If either setting does not exist, the worker SHALL use an empty default (empty JSON object for MCP, empty list for credentials).

#### Scenario: Settings exist
- **WHEN** the worker processes a task and `mcp_servers` and `credentials` settings exist in the database
- **THEN** the worker copies the MCP configuration as `/workspace/mcp.json` and passes the credentials as environment variables to the container

#### Scenario: No settings configured
- **WHEN** the worker processes a task and neither `mcp_servers` nor `credentials` settings exist
- **THEN** the worker copies an empty JSON object as `/workspace/mcp.json` and passes no extra environment variables to the container

### Requirement: Worker transitions completed tasks to review
After successful container execution (exit code 0), the worker SHALL set the task status to `review` and assign a new position at the bottom of the Review column. After failed execution (non-zero exit code), the worker SHALL set the task status to `failed`.

#### Scenario: Task succeeds
- **WHEN** a task container exits with code 0
- **THEN** the worker sets the task status to `review`, assigns the next position in the Review column, stores the captured output, and publishes a `task_updated` event

#### Scenario: Task fails
- **WHEN** a task container exits with a non-zero exit code
- **THEN** the worker sets the task status to `failed`, stores the captured output, and publishes a `task_updated` event

### Requirement: Worker truncates large output
The worker SHALL truncate captured container output to a configurable maximum size (default 1MB) before storing it in the database. If output is truncated, the worker SHALL append a marker indicating truncation.

#### Scenario: Output within limit
- **WHEN** a container produces 500KB of output and the limit is 1MB
- **THEN** the worker stores the full output without truncation

#### Scenario: Output exceeds limit
- **WHEN** a container produces 2MB of output and the limit is 1MB
- **THEN** the worker stores the first 1MB of output followed by a truncation marker

### Requirement: Worker executes tasks via ContainerRuntime

The TaskManager SHALL execute each task by delegating container operations to the configured `ContainerRuntime` implementation (see `container-runtime` spec). The TaskManager SHALL: (1) retrieve the `task_processing_model` setting from the database as a `{"provider_id": "<uuid>", "model": "<model-id>"}` object, resolve the provider_id to a provider row in the `llm_provider` table, and read the decrypted `base_url` and `api_key` from that provider; also retrieve `system_prompt`, `mcp_servers`, `litellm_mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, `hindsight_url`, and `hindsight_bank_id` settings, and query the `skills` and `skill_files` tables for all skills and their attached files, (1b) if the task has a non-null `profile_id`, read the corresponding `TaskProfile` row and apply profile overrides to the resolved settings using the inheritance rules: non-null scalar fields override globals, `null` list fields inherit all defaults, `[]` list fields clear to empty, non-empty list fields use only the specified subset, (2) build the environment variables (`OPENAI_BASE_URL` set to the resolved provider's `base_url`, `OPENAI_API_KEY` set to the resolved provider's decrypted `api_key`, `OPENAI_MODEL` set to the resolved model ID, `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, `MCP_CONFIGURATION_PATH=/workspace/mcp.json`) and input files, (3) inject Playwright MCP entry using the standalone Playwright service URL (not `POD_IP`), (4-15) all remaining steps (MCP injection, skills, SSH, Hindsight, GitHub, runtime prepare/run/result/cleanup, rescheduling) SHALL remain unchanged.

The standalone `worker.py` entrypoint SHALL be removed. All task processing logic SHALL live in the `TaskManager` class (`errand/task_manager.py`).

Playwright sidecar management (start/stop/health-check of per-worker Playwright containers) SHALL be removed. Playwright connectivity SHALL use the standalone Playwright service URL.

If the `task_processing_model` setting is empty, has a null `provider_id`, or references a provider that no longer exists, the TaskManager SHALL log an error and mark the task as failed with output `{"error": "LLM provider not configured"}`.

If the task references a `profile_id` that no longer exists in the database (profile was deleted), the TaskManager SHALL log a warning and proceed with default settings (as if `profile_id` were null).

#### Scenario: TaskManager resolves provider for task processing

- **WHEN** the TaskManager dequeues a task and `task_processing_model` is `{"provider_id": "uuid-1", "model": "claude-sonnet-4-5-20250929"}`
- **THEN** the TaskManager reads provider "uuid-1" from the `llm_provider` table, decrypts its API key, and passes `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` to the container

#### Scenario: Task processing model not configured

- **WHEN** the TaskManager dequeues a task and `task_processing_model` is empty or has null provider_id
- **THEN** the TaskManager marks the task as failed with `{"error": "LLM provider not configured"}`

#### Scenario: Task with profile model override uses profile's provider

- **WHEN** the TaskManager dequeues a task with a profile that overrides `task_processing_model` to `{"provider_id": "uuid-2", "model": "gpt-4o"}`
- **THEN** the TaskManager uses provider "uuid-2" credentials and model "gpt-4o"

#### Scenario: Task with null profile uses global settings

- **WHEN** the TaskManager dequeues a task with `profile_id = null`
- **THEN** the TaskManager uses the global `task_processing_model` setting

#### Scenario: Playwright URL uses service DNS

- **WHEN** the TaskManager prepares a task's MCP config and Playwright is enabled
- **THEN** the Playwright MCP entry URL uses the service DNS (e.g. `http://errand-playwright:3000`) not `POD_IP`

### Requirement: Worker assembles system prompt for task execution
The worker SHALL construct a system prompt by starting with the base system prompt from settings, then appending augmentation blocks in the following order: (1) pre-loaded Hindsight memories, (2) Perplexity web search instructions (if enabled), (3) Hindsight memory tool instructions (if configured), (4) agent skill manifest (if skills exist), (5) **repo context discovery instructions**. The repo context discovery block SHALL always be appended and SHALL instruct the agent to check for `CLAUDE.md`, `.claude/commands/`, and `.claude/skills/` after any `git clone` operation.

#### Scenario: System prompt includes repo context instructions
- **WHEN** the worker assembles the system prompt for any task
- **THEN** the system prompt includes a "Repo Context Discovery" section instructing the agent to check cloned repos for CLAUDE.md, commands, and skills

#### Scenario: Repo context instructions placed after skill manifest
- **WHEN** the worker assembles the system prompt with both skills and repo context
- **THEN** the repo context instructions appear after the skill manifest section
