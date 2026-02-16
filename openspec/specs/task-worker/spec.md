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

#### Scenario: Skills written to container as Agent Skills directories
- **WHEN** the worker processes a task and 2 skills exist in the database: "research" (with file `scripts/search.py`) and "tweet" (no files)
- **THEN** the container contains `/workspace/skills/research/SKILL.md`, `/workspace/skills/research/scripts/search.py`, and `/workspace/skills/tweet/SKILL.md`

#### Scenario: System prompt includes skill manifest instead of MCP directive
- **WHEN** the worker processes a task and skills exist
- **THEN** the system prompt contains a "## Skills" section with a table of skill names and descriptions and a directive to read SKILL.md files, and does NOT contain "call list_skills" or "call get_skill"

#### Scenario: No backend MCP server injected for skills
- **WHEN** the worker processes a task and skills exist but no user-configured MCP servers reference the backend
- **THEN** the mcp.json does NOT contain a "content-manager" MCP server entry that was auto-injected for skill discovery

#### Scenario: SSH credentials injected into container

- **WHEN** the worker processes a task and `ssh_private_key` and `git_ssh_hosts` settings exist with `git_ssh_hosts` set to `["github.com", "bitbucket.org"]`
- **THEN** the worker copies `/home/nonroot/.ssh/id_rsa.agent` (private key, permissions 600) and `/home/nonroot/.ssh/config` (SSH config) into the container before starting it

#### Scenario: SSH config generated for each host

- **WHEN** the worker processes a task and `git_ssh_hosts` is set to `["github.com", "gitlab.com"]`
- **THEN** the SSH config file contains entries for both `github.com` and `gitlab.com`, each with `IdentityFile ~/.ssh/id_rsa.agent`, `User git`, and `StrictHostKeyChecking accept-new`

#### Scenario: No SSH key skips credential injection

- **WHEN** the worker processes a task and no `ssh_private_key` setting exists
- **THEN** the worker skips SSH credential injection and starts the container without SSH configuration

#### Scenario: Empty SSH hosts list skips config

- **WHEN** the worker processes a task and `ssh_private_key` exists but `git_ssh_hosts` is `[]`
- **THEN** the worker copies the private key but generates an empty SSH config file

#### Scenario: Successful task execution stores logs separately

- **WHEN** the worker processes a pending task and the task runner exits with code 0 and stdout contains `{"status": "completed", "result": "Task done", "questions": []}` and stderr contains "2026-02-10 INFO Starting agent"
- **THEN** the worker stores "Task done" in the task's `output` field and "2026-02-10 INFO Starting agent" in the task's `runner_logs` field

#### Scenario: Task runner stdout has preamble before JSON

- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `Here is the report:\n\n{"status": "completed", "result": "All healthy", "questions": []}`
- **THEN** the worker extracts the JSON from stdout, stores "All healthy" in the task's `output` field, and stores stderr in `runner_logs`

#### Scenario: Task runner stdout has preamble before JSON code fence

- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `Based on analysis...\n\n` followed by `` ```json\n{"status": "completed", "result": "Report text", "questions": []}\n``` ``
- **THEN** the worker extracts the JSON from the code fence, stores "Report text" in the task's `output` field, and stores stderr in `runner_logs`

#### Scenario: Task runner returns needs_input status with logs

- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `{"status": "needs_input", "result": "Need more details", "questions": ["What format?"]}` and stderr contains agent log output
- **THEN** the worker stores the output in the task's `output` field, stores stderr in `runner_logs`, moves the task to `review` status, and adds an "Input Needed" tag

#### Scenario: Task runner exits with non-zero code stores logs

- **WHEN** the worker processes a task and the task runner exits with a non-zero exit code with stderr containing error logs
- **THEN** the worker captures stderr in `runner_logs`, stores combined stdout/stderr in `output`, and schedules the task for retry

#### Scenario: Task runner stdout is not valid JSON stores logs

- **WHEN** the worker processes a task and the task runner exits with code 0 but stdout contains no extractable valid JSON and stderr contains log output
- **THEN** the worker stores stderr in `runner_logs`, stores combined output in `output`, and schedules the task for retry

#### Scenario: Container creation fails

- **WHEN** the worker attempts to create a container and the Docker API returns an error (e.g. image not found)
- **THEN** the worker schedules the task for retry with exponential backoff, logs the error, and continues polling

#### Scenario: Missing settings use defaults

- **WHEN** the worker picks up a task but `task_processing_model` is not set in settings
- **THEN** the worker uses `claude-sonnet-4-5-20250929` as the model and passes an empty string for system prompt and empty JSON object for MCP config

#### Scenario: Perplexity injected into mcp.json when enabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is set to `"true"` and `PERPLEXITY_URL` is set to `"http://cm-perplexity-mcp:8080/mcp"` and the database `mcp_servers` setting is `{"mcpServers": {"other": {"url": "http://other/mcp"}}}`
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"perplexity-ask": {"url": "http://cm-perplexity-mcp:8080/mcp"}, "other": {"url": "http://other/mcp"}}}`

#### Scenario: System prompt augmented when Perplexity enabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is set to `"true"` and the admin system prompt is `"You are a helpful assistant."`
- **THEN** the `system_prompt.txt` written to the container contains the original prompt followed by an instruction block explaining the `perplexity-ask` tool is available for web search and current information lookups

#### Scenario: System prompt unchanged when Perplexity disabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is not set or is not `"true"` and the admin system prompt is `"You are a helpful assistant."`
- **THEN** the `system_prompt.txt` written to the container contains exactly `"You are a helpful assistant."` with no additions

#### Scenario: Perplexity not injected when disabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is not set or is not `"true"`
- **THEN** the `mcp.json` written to the container contains only the MCP servers from the database setting, unchanged

#### Scenario: Database perplexity entry takes precedence

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is set to `"true"` and the database `mcp_servers` setting already contains a `"perplexity-ask"` key with `{"url": "http://custom-perplexity/mcp"}`
- **THEN** the `mcp.json` written to the container uses the database value `{"url": "http://custom-perplexity/mcp"}` for the `"perplexity-ask"` key, not the injected one

#### Scenario: Perplexity and skills both augment system prompt
- **WHEN** the worker processes a task with `USE_PERPLEXITY` set to `"true"` and skills exist
- **THEN** the system prompt contains the admin prompt, followed by the Perplexity block, followed by the skill manifest section

#### Scenario: Environment variable substitution in MCP config with $VAR syntax

- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains `{"mcpServers": {"argocd": {"url": "http://mcp-proxy:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer $LITELLM_API_KEY"}}}}` and the worker environment has `LITELLM_API_KEY=sk-secret-123`
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"argocd": {"url": "http://mcp-proxy:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-secret-123"}}}}`

#### Scenario: Environment variable substitution in MCP config with ${VAR} syntax

- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"Authorization": "${AUTH_TOKEN}"}}}}` and the worker environment has `AUTH_TOKEN=Bearer abc-456`
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"Authorization": "Bearer abc-456"}}}}`

#### Scenario: Missing environment variable leaves placeholder unchanged

- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"x-api-key": "$MISSING_KEY"}}}}` and `MISSING_KEY` is not set in the worker environment
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"x-api-key": "$MISSING_KEY"}}}}`

#### Scenario: Substitution in nested JSON values

- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains nested objects with string values containing `$DB_PASSWORD` at various depths and the worker environment has `DB_PASSWORD=s3cret`
- **THEN** all string values containing `$DB_PASSWORD` at any nesting level are substituted with `s3cret`

#### Scenario: Non-string values are not modified during substitution

- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains numeric, boolean, or null values
- **THEN** those values are passed through unchanged regardless of environment variables

#### Scenario: Multiple variables in a single string value

- **WHEN** the worker writes `mcp.json` and a string value contains `"$SCHEME://$HOST:$PORT/mcp"` and the worker environment has `SCHEME=https`, `HOST=api.example.com`, and `PORT=8443`
- **THEN** the substituted value is `"https://api.example.com:8443/mcp"`

#### Scenario: WebSocket event includes all task fields

- **WHEN** the worker publishes a `task_updated` event after changing task status
- **THEN** the event payload includes all fields: id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, runner_logs, retry_count, tags, created_at, and updated_at

#### Scenario: Completed repeating task triggers rescheduling

- **WHEN** the worker moves a task with `category = 'repeating'` and `repeat_interval = '1h'` to `completed`
- **THEN** the worker calls the rescheduling logic which creates a new cloned task with `status = 'scheduled'` and `execute_at` approximately 1 hour from now

When the worker schedules a task for retry via `_schedule_retry`, it SHALL add a "Retry" tag to the task. If the "Retry" tag does not exist in the `tags` table, the worker SHALL create it. If the task already has the "Retry" tag, no duplicate association SHALL be created.

When the worker successfully processes a task (moves to `completed` or `review` status), it SHALL remove the "Retry" tag from the task if present. This ensures the tag does not persist on tasks that eventually succeed.

#### Scenario: Retry adds "Retry" tag

- **WHEN** the worker processes a task and the container exits with a non-zero exit code
- **THEN** the worker moves the task to `scheduled` status with exponential backoff and adds a "Retry" tag to the task

#### Scenario: Retry on unparseable output adds "Retry" tag

- **WHEN** the worker processes a task and the container exits with code 0 but stdout contains no extractable valid JSON
- **THEN** the worker moves the task to `scheduled` status and adds a "Retry" tag to the task

#### Scenario: Successful completion removes "Retry" tag

- **WHEN** the worker processes a task that has a "Retry" tag and the container exits with code 0 and valid structured output with status "completed"
- **THEN** the worker moves the task to `completed` status and removes the "Retry" tag

#### Scenario: Review status removes "Retry" tag

- **WHEN** the worker processes a task that has a "Retry" tag and the container exits with code 0 and valid structured output with status "needs_input"
- **THEN** the worker moves the task to `review` status, adds the "Input Needed" tag, and removes the "Retry" tag

#### Scenario: Retry tag created if not exists

- **WHEN** the worker schedules a task for retry and no "Retry" tag exists in the tags table
- **THEN** the worker creates the "Retry" tag and associates it with the task

#### Scenario: No duplicate retry tag

- **WHEN** the worker schedules a task for retry and the task already has a "Retry" tag from a previous retry
- **THEN** no duplicate tag association is created
