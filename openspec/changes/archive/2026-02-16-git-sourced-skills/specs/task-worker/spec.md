## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle with `network_mode="host"` (so the task runner shares DinD's network namespace). The worker SHALL: (1) pull the task runner image, (2) retrieve the `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, and `skills_git_repo` settings from the database, and query the `skills` and `skill_files` tables for all skills and their attached files, (3) if `skills_git_repo` is configured with a non-empty `url`, refresh the local git clone and parse Agent Skills directories from the configured base path, then merge with DB skills (DB wins on name conflicts), (4) create the container from the task runner image with environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from the worker's own environment), `OPENAI_MODEL` (from the `task_processing_model` setting, defaulting to `claude-sonnet-4-5-20250929`), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, and `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, (5) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/system_prompt.txt` containing the system prompt from settings, `/workspace/mcp.json` containing the MCP server configuration from settings **after environment variable substitution**) into the stopped container via `put_archive()`, (6) if merged skills exist (from DB and/or git), write Agent Skills directories to `/workspace/skills/<name>/` containing `SKILL.md` files and any attached files, (7) if `ssh_private_key` is present in settings, copy SSH credentials into the container: the private key at `/home/nonroot/.ssh/id_rsa.agent` with file permissions 600, and an SSH config file at `/home/nonroot/.ssh/config` with file permissions 644, (8) start the container, (9) wait for the container to exit, (10) capture stdout/stderr via `container.logs()`, (11) parse the structured output from stdout using robust JSON extraction (try direct JSON parse, then code fence extraction anywhere in stdout, then first-`{`-to-last-`}` extraction — the first strategy that produces a valid `TaskRunnerOutput` is used; if none succeed, schedule retry), (12) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (13) remove the container, (14) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

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

When skills exist (from DB and/or git), the worker SHALL append a skill manifest section to the system prompt after any Perplexity block. The worker SHALL NOT inject the backend MCP server into the MCP configuration for skill purposes. The worker SHALL NOT append the legacy "call list_skills" directive.

Before writing the `mcp_servers` configuration as `/workspace/mcp.json`, the worker SHALL perform environment variable substitution on all string values within the JSON structure. The substitution SHALL support two syntaxes: `$VARIABLE_NAME` and `${VARIABLE_NAME}`, where `VARIABLE_NAME` matches the pattern `[A-Za-z_][A-Za-z0-9_]*`. The worker SHALL resolve variable references against its own process environment (`os.environ`). If a referenced variable does not exist in the worker's environment, the placeholder SHALL be left unchanged in the output. Substitution SHALL only operate on string values within the JSON structure — keys, numbers, booleans, and nulls SHALL NOT be modified.

The worker SHALL store the captured stderr in the task's `runner_logs` field for all execution outcomes: successful completion, needs_input, retry on failure, and retry on parse error. The `runner_logs` field SHALL be written in every UPDATE statement that modifies the task after container execution.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `runner_logs`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship and the `runner_logs` field.

#### Scenario: Worker reads settings including skills_git_repo
- **WHEN** the worker picks up a new pending task
- **THEN** the worker queries the database for `task_processing_model`, `system_prompt`, `mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, and `skills_git_repo` settings, and queries the `skills` and `skill_files` tables for all skills

#### Scenario: Git skills merged with DB skills in container
- **WHEN** the worker processes a task and DB has skill "code-review" and git repo has skills "research" and "tweet"
- **THEN** the container contains `/workspace/skills/code-review/SKILL.md`, `/workspace/skills/research/SKILL.md`, and `/workspace/skills/tweet/SKILL.md`

#### Scenario: Skill manifest includes both DB and git skills
- **WHEN** the worker processes a task with DB skill "code-review" and git skill "research"
- **THEN** the system prompt skill manifest table lists both "code-review" and "research"

#### Scenario: Git clone failure triggers retry
- **WHEN** the worker processes a task and the git clone/pull fails
- **THEN** the task is moved to `scheduled` status via `_schedule_retry()` with the git error in `output`

#### Scenario: No git repo configured proceeds with DB-only skills
- **WHEN** the worker processes a task and no `skills_git_repo` setting exists
- **THEN** the worker uses only DB-managed skills without any git operations
