## Purpose

Worker-side resolution of task profiles at execution time, applying field-level overrides to global settings.

## Requirements

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
For scalar profile fields (`model`, `system_prompt`, `max_turns`, `reasoning_effort`), a non-null value SHALL override the corresponding global setting. A null value SHALL inherit the global setting.

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
