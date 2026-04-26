## MODIFIED Requirements

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
