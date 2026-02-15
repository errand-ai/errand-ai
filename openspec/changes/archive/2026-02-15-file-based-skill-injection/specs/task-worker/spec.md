## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle with `network_mode="host"` (so the task runner shares DinD's network namespace). The worker SHALL: (1) pull the task runner image, (2) retrieve the `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, and `git_ssh_hosts` settings from the database, and query the `skills` and `skill_files` tables for all skills and their attached files, (3) create the container from the task runner image with environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from the worker's own environment), `OPENAI_MODEL` (from the `task_processing_model` setting, defaulting to `claude-sonnet-4-5-20250929`), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, and `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, (4) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/system_prompt.txt` containing the system prompt from settings, `/workspace/mcp.json` containing the MCP server configuration from settings **after environment variable substitution**) into the stopped container via `put_archive()`, (5) if skills exist, write Agent Skills directories to `/workspace/skills/<name>/` containing `SKILL.md` files and any attached files from the `skill_files` table, (6) if `ssh_private_key` is present in settings, copy SSH credentials into the container: the private key at `/home/nonroot/.ssh/id_rsa.agent` with file permissions 600, and an SSH config file at `/home/nonroot/.ssh/config` with file permissions 644, (7) start the container, (8) wait for the container to exit, (9) capture stdout/stderr via `container.logs()`, (10) parse the structured output from stdout using robust JSON extraction (try direct JSON parse, then code fence extraction anywhere in stdout, then first-`{`-to-last-`}` extraction — the first strategy that produces a valid `TaskRunnerOutput` is used; if none succeed, schedule retry), (11) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (12) remove the container, (13) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

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

#### Scenario: Skills written to container as Agent Skills directories
- **WHEN** the worker processes a task and 2 skills exist in the database: "research" (with file `scripts/search.py`) and "tweet" (no files)
- **THEN** the container contains `/workspace/skills/research/SKILL.md`, `/workspace/skills/research/scripts/search.py`, and `/workspace/skills/tweet/SKILL.md`

#### Scenario: System prompt includes skill manifest instead of MCP directive
- **WHEN** the worker processes a task and skills exist
- **THEN** the system prompt contains a "## Skills" section with a table of skill names and descriptions and a directive to read SKILL.md files, and does NOT contain "call list_skills" or "call get_skill"

#### Scenario: No backend MCP server injected for skills
- **WHEN** the worker processes a task and skills exist but no user-configured MCP servers reference the backend
- **THEN** the mcp.json does NOT contain a "content-manager" MCP server entry that was auto-injected for skill discovery

#### Scenario: Worker reads settings for task processing
- **WHEN** the worker picks up a new pending task
- **THEN** the worker queries the database for `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, and `git_ssh_hosts` settings, and queries the `skills` and `skill_files` tables for all skills

#### Scenario: Successful task execution stores logs separately
- **WHEN** the worker processes a pending task and the task runner exits with code 0 and stdout contains `{"status": "completed", "result": "Task done", "questions": []}` and stderr contains "2026-02-10 INFO Starting agent"
- **THEN** the worker stores "Task done" in the task's `output` field and "2026-02-10 INFO Starting agent" in the task's `runner_logs` field

#### Scenario: Perplexity and skills both augment system prompt
- **WHEN** the worker processes a task with `USE_PERPLEXITY` set to `"true"` and skills exist
- **THEN** the system prompt contains the admin prompt, followed by the Perplexity block, followed by the skill manifest section
