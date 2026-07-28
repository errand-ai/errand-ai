## Purpose

Worker-side resolution of task profiles at execution time, applying field-level overrides to global settings.
## Requirements

### Requirement: Worker resolves enabled_plugins for plugin content gating
When the worker resolves a task profile, it SHALL read the profile's `enabled_plugins` column. Plugin-sourced skills and plugin-sourced MCP servers SHALL be included in the task's tarball and `/workspace/mcp.json` ONLY for plugins whose IDs appear in `enabled_plugins`. A null or empty `enabled_plugins` SHALL cause the worker to omit all plugin-sourced content for that task.

#### Scenario: Profile with two enabled plugins
- **WHEN** a profile has `enabled_plugins = ["abc-123", "def-456"]` and both plugin rows have `enabled=true`
- **THEN** the worker includes skills and MCP servers from those two plugins in the task tarball and `/workspace/mcp.json`

#### Scenario: Plugin in enabled_plugins but globally disabled
- **WHEN** a profile has `enabled_plugins = ["abc-123"]` and the plugin row has `enabled=false`
- **THEN** the worker omits that plugin's contents and logs an info-level message

#### Scenario: Empty enabled_plugins
- **WHEN** a profile has `enabled_plugins = []` (or null) and one or more plugins are globally enabled
- **THEN** the worker omits all plugin-sourced skills and MCP servers from the task tarball and `mcp.json`

#### Scenario: enabled_plugins references missing plugin
- **WHEN** a profile has `enabled_plugins = ["deleted-id"]` and no plugin row matches that ID
- **THEN** the worker silently skips that ID, logs an info-level message, and proceeds with the remaining valid plugins

#### Scenario: Default profile (no profile attached)
- **WHEN** a task has `profile_id=null`
- **THEN** the worker omits all plugin-sourced content (default profile has no `enabled_plugins`)

### Requirement: Plugin contents always apply at bundle granularity
The worker SHALL NOT filter plugin-sourced skills or MCP servers by individual name. Inclusion is determined entirely by membership in `profile.enabled_plugins` AND the plugin row's global `enabled` flag.

#### Scenario: Plugin skill not in profile skill_ids
- **WHEN** a plugin contributes skills `post-message` and `react-to-thread`, and the profile's `skill_ids` is `["unrelated-db-skill-uuid"]`
- **THEN** both plugin skills are still included because plugin gating uses `enabled_plugins` not `skill_ids`

#### Scenario: Plugin MCP not in profile mcp_servers
- **WHEN** a plugin contributes a namespaced MCP server `slack-toolkit__slack`, and the profile's `mcp_servers` is `["gmail"]`
- **THEN** the plugin's namespaced MCP server is included alongside `gmail` because plugin gating is bundle-level

### Requirement: Worker resolves task profile at execution time
When the worker dequeues a task with a non-null `profile_id`, it SHALL read the corresponding `TaskProfile` row from the database. The worker SHALL then resolve the agent configuration by applying the profile's overrides to the global settings using the inheritance rules.

#### Scenario: Task with profile
- **WHEN** the worker dequeues a task with `profile_id` referencing the "email-triage" profile that has `model: "claude-haiku-4-5-20251001"`
- **THEN** the worker uses "claude-haiku-4-5-20251001" as the model instead of the global `task_processing_model`

#### Scenario: Task with null profile_id
- **WHEN** the worker dequeues a task with `profile_id = null`
- **THEN** the worker uses global settings as today (no change in behavior)

#### Scenario: Task references deleted profile
- **WHEN** the worker dequeues a task whose `profile_id` references a non-existent profile (deleted after assignment)
- **THEN** the worker logs a warning and uses global settings (default profile behavior)

### Requirement: Scalar field inheritance
For scalar profile fields (`model`, `system_prompt`, `max_turns`, `reasoning_effort`, `llm_timeout`), a non-null value SHALL override the corresponding global setting. A null value SHALL inherit the global setting. The `llm_timeout` field inherits from the global `task_processing_timeout` setting (default `30` seconds when no global value is set).

#### Scenario: Model overridden
- **WHEN** the profile has `model: "claude-haiku-4-5-20251001"` and the global `task_processing_model` is "claude-sonnet-4-5-20250929"
- **THEN** the resolved model is "claude-haiku-4-5-20251001"

#### Scenario: Model inherited
- **WHEN** the profile has `model: null`
- **THEN** the resolved model is the global `task_processing_model`

#### Scenario: System prompt overridden
- **WHEN** the profile has `system_prompt: "You are an email assistant"`
- **THEN** the resolved system prompt is "You are an email assistant" (replaces the global system prompt)

#### Scenario: Max turns overridden
- **WHEN** the profile has `max_turns: 10`
- **THEN** the MAX_TURNS environment variable is set to "10" for the container

#### Scenario: Reasoning effort overridden
- **WHEN** the profile has `reasoning_effort: "low"`
- **THEN** the REASONING_EFFORT environment variable is set to "low" for the container

#### Scenario: LLM timeout overridden by profile
- **WHEN** the profile has `llm_timeout: 300` and the global `task_processing_timeout` is `60`
- **THEN** the `LLM_REQUEST_TIMEOUT` environment variable is set to "300" for the container

#### Scenario: LLM timeout inherited from global setting
- **WHEN** the profile has `llm_timeout: null` and the global `task_processing_timeout` is `120`
- **THEN** the `LLM_REQUEST_TIMEOUT` environment variable is set to "120" for the container

#### Scenario: LLM timeout inherited and global setting absent
- **WHEN** the profile has `llm_timeout: null` and no `task_processing_timeout` setting exists in the database
- **THEN** the `LLM_REQUEST_TIMEOUT` environment variable is set to "30" for the container (built-in default)

### Requirement: List field inheritance with three states
For list profile fields (`mcp_servers`, `litellm_mcp_servers`, `skill_ids`), SQL NULL SHALL inherit all values from global settings, an empty JSON array SHALL result in no values (explicitly empty), and a non-empty JSON array SHALL use only those specific values. When `skill_ids` is not null, the `include_git_skills` Boolean flag SHALL control whether git-sourced skills are included alongside the selected managed skills.

#### Scenario: MCP servers inherited (null)
- **WHEN** the profile has `mcp_servers: null` (SQL NULL) and the global MCP config has servers "errand" and "hindsight"
- **THEN** the resolved MCP configuration includes "errand" and "hindsight"

#### Scenario: MCP servers explicitly empty
- **WHEN** the profile has `mcp_servers: []` (empty JSON array)
- **THEN** the resolved MCP configuration has no user-configured MCP servers (auto-injected servers like errand and hindsight still apply based on their respective conditions)

#### Scenario: MCP servers explicit subset
- **WHEN** the profile has `mcp_servers: ["gmail"]` and the global MCP config has servers "gmail", "errand", and "hindsight"
- **THEN** the resolved user-configured MCP servers contain only "gmail" (auto-injected servers still apply)

#### Scenario: LiteLLM MCP servers inherited (null)
- **WHEN** the profile has `litellm_mcp_servers: null` and the global setting has `["argocd", "perplexity"]`
- **THEN** the resolved LiteLLM MCP servers are `["argocd", "perplexity"]`

#### Scenario: LiteLLM MCP servers explicitly empty
- **WHEN** the profile has `litellm_mcp_servers: []`
- **THEN** no LiteLLM MCP gateway entry is injected

#### Scenario: Skills inherited (null)
- **WHEN** the profile has `skill_ids: null`
- **THEN** all skills from the database and git repo are included (include_git_skills is ignored)

#### Scenario: Skills explicit subset with git skills included
- **WHEN** the profile has `skill_ids: ["uuid-1", "uuid-2"]` and `include_git_skills: true` and the database has 5 skills and the git repo has 3 skills
- **THEN** the 2 matching DB skills plus all 3 git-sourced skills are included

#### Scenario: Skills explicit subset with git skills excluded
- **WHEN** the profile has `skill_ids: ["uuid-1", "uuid-2"]` and `include_git_skills: false`
- **THEN** only the 2 matching DB skills are included and git-sourced skills are excluded

#### Scenario: Skills explicitly empty with git skills included
- **WHEN** the profile has `skill_ids: []` and `include_git_skills: true` and the git repo has 3 skills
- **THEN** no DB skills are included but all 3 git-sourced skills are included

#### Scenario: Skills explicitly empty with git skills excluded
- **WHEN** the profile has `skill_ids: []` and `include_git_skills: false`
- **THEN** no skills are included in the system prompt or archive

### Requirement: Worker reads profile_id in task query
The worker's task dequeue and processing logic SHALL eagerly load the task's `profile_id` field. If `profile_id` is non-null, the worker SHALL query the `task_profiles` table for the profile row before building the container configuration.

#### Scenario: Profile loaded during task processing
- **WHEN** the worker processes a task with `profile_id = "abc-123"`
- **THEN** the worker queries `SELECT * FROM task_profiles WHERE id = 'abc-123'` and uses the result for configuration resolution

### Requirement: Worker propagates resolved LLM timeout to runner
For every task — whether a profile is attached or not — the worker SHALL set the `LLM_REQUEST_TIMEOUT` environment variable on the runner container. The value SHALL be the integer-second resolution of `profile.llm_timeout → task_processing_timeout setting → 30`.

#### Scenario: Task with no profile uses global default
- **WHEN** the worker dequeues a task with `profile_id = null` and `task_processing_timeout = 90`
- **THEN** the runner container is started with `LLM_REQUEST_TIMEOUT=90`

#### Scenario: Task with no profile and no global setting uses 30
- **WHEN** the worker dequeues a task with `profile_id = null` and no `task_processing_timeout` setting
- **THEN** the runner container is started with `LLM_REQUEST_TIMEOUT=30`

#### Scenario: Task with profile override
- **WHEN** the worker dequeues a task whose profile has `llm_timeout = 600`
- **THEN** the runner container is started with `LLM_REQUEST_TIMEOUT=600` regardless of the global setting

### Requirement: Resolved model name accepts either `model` or `model_id`

When the resolved model setting is an object, the task manager SHALL take the model name from `model` when present and non-empty, and otherwise from `model_id`. `OPENAI_MODEL` SHALL be set to that name.

Profiles saved before the write-side mirror hold only `model_id`. Reading `model` alone yields an empty string there, and the task runner treats an empty `OPENAI_MODEL` as missing and exits with `Missing required environment variables: OPENAI_MODEL`. Accepting either key repairs those stored rows without a data migration.

#### Scenario: Object carrying only model_id

- **WHEN** the resolved model setting is `{"provider_id": null, "model_id": "claude-haiku-4-5-20251001"}`
- **THEN** `OPENAI_MODEL` is `claude-haiku-4-5-20251001`

#### Scenario: Canonical key wins when both are present and differ

- **WHEN** the resolved model setting is `{"model": "canonical", "model_id": "mirror"}`
- **THEN** `OPENAI_MODEL` is `canonical`

#### Scenario: Plain string is unaffected

- **WHEN** the resolved model setting is the string `gpt-4o`
- **THEN** `OPENAI_MODEL` is `gpt-4o`

#### Scenario: Neither key present is still an error

- **WHEN** the resolved model setting is an object carrying neither `model` nor `model_id`, and no provider is configured
- **THEN** the task fails with `LLM provider not configured` rather than launching a runner with an empty model
