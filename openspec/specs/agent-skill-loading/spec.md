## Requirements

### Requirement: list_skills MCP tool
The backend MCP server SHALL expose a `list_skills` tool that returns a JSON array of all defined skills, each containing only `name` and `description` fields (not the full instructions). If no skills are defined, it SHALL return an empty array. The tool SHALL require valid MCP API key authentication.

#### Scenario: List skills with skills defined
- **WHEN** the agent calls `list_skills` and two skills are defined ("researcher" and "code-reviewer")
- **THEN** the tool returns `[{"name": "researcher", "description": "Conducts web research"}, {"name": "code-reviewer", "description": "Reviews code for quality"}]`

#### Scenario: List skills with no skills defined
- **WHEN** the agent calls `list_skills` and no skills are defined
- **THEN** the tool returns `[]`

### Requirement: get_skill MCP tool
The backend MCP server SHALL expose a `get_skill` tool that accepts a `name` parameter and returns the full `instructions` text of the matching skill. If no skill matches the given name, the tool SHALL return an error message indicating the skill was not found.

#### Scenario: Get existing skill
- **WHEN** the agent calls `get_skill` with name "researcher" and that skill exists
- **THEN** the tool returns the full instructions text of the "researcher" skill

#### Scenario: Get non-existent skill
- **WHEN** the agent calls `get_skill` with name "nonexistent" and no skill has that name
- **THEN** the tool returns an error message: "Skill 'nonexistent' not found"

### Requirement: Skill-awareness directive in system prompt
When the worker prepares the system prompt for a task, it SHALL check if any skills are defined in settings. If at least one skill exists, the worker SHALL append a skill-awareness directive to the system prompt instructing the agent to: (1) call `list_skills` at the start of execution to discover available skills, (2) call `get_skill` to load a skill if one is relevant to the task, and (3) follow the loaded skill's instructions. If no skills are defined, the worker SHALL NOT append the directive.

#### Scenario: Skills exist — directive appended
- **WHEN** the worker prepares the system prompt and 2 skills are defined in settings
- **THEN** the system prompt written to the container includes the original admin prompt followed by a skill-awareness directive

#### Scenario: No skills defined — no directive
- **WHEN** the worker prepares the system prompt and no skills are defined in settings
- **THEN** the system prompt written to the container contains only the original admin prompt (and any other existing augmentations like Perplexity)

#### Scenario: Directive placement after Perplexity
- **WHEN** the worker prepares the system prompt and both Perplexity and skills are enabled
- **THEN** the skill-awareness directive appears after the Perplexity instruction block
