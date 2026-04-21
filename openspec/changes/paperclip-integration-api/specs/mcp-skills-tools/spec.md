## ADDED Requirements

### Requirement: List skills via MCP
The MCP server SHALL provide a `list_skills` tool that returns available skills.

#### Scenario: Skills listed successfully
- **WHEN** `list_skills` is called
- **THEN** the tool SHALL return a JSON array of objects with `name` and `description` fields for each skill

#### Scenario: No skills configured
- **WHEN** `list_skills` is called and no skills exist
- **THEN** the tool SHALL return an empty JSON array

### Requirement: Upsert skill via MCP
The MCP server SHALL provide an `upsert_skill` tool that creates or updates a skill by name. The `files` parameter SHALL be typed as `list | None` for correct MCP JSON schema generation.

#### Scenario: Create new skill
- **WHEN** `upsert_skill` is called with `name="code-review"`, `description="..."`, `instructions="..."`
- **AND** no skill named `"code-review"` exists
- **THEN** a new skill SHALL be created with the provided fields
- **AND** the tool SHALL return a success message with the skill ID

#### Scenario: Update existing skill
- **WHEN** `upsert_skill` is called with `name="code-review"`, `description="..."`, `instructions="..."`
- **AND** a skill named `"code-review"` already exists
- **THEN** the existing skill SHALL be updated with the new description and instructions
- **AND** existing skill files SHALL be replaced with the provided files (if any)

#### Scenario: Upsert with files
- **WHEN** `upsert_skill` is called with `files=[{"path": "references/guide.md", "content": "..."}]`
- **THEN** the skill files SHALL be stored as SkillFile records
- **AND** on update, all previous files SHALL be removed and replaced with the new set

#### Scenario: Invalid skill name
- **WHEN** `upsert_skill` is called with a name that doesn't match the validation pattern (lowercase, no leading/trailing hyphens, max 64 chars)
- **THEN** the tool SHALL return an error message

#### Scenario: Skill name with consecutive hyphens
- **WHEN** `upsert_skill` is called with a name containing consecutive hyphens (e.g. `"code-review--522856552c"`)
- **THEN** the tool SHALL accept the name (consecutive hyphens are permitted to support external naming conventions)

### Requirement: Delete skill via MCP
The MCP server SHALL provide a `delete_skill` tool that removes a skill by name.

#### Scenario: Delete existing skill
- **WHEN** `delete_skill` is called with `name="code-review"`
- **AND** a skill named `"code-review"` exists
- **THEN** the skill and all its files SHALL be deleted
- **AND** the tool SHALL return a success message

#### Scenario: Delete non-existent skill
- **WHEN** `delete_skill` is called with a name that doesn't exist
- **THEN** the tool SHALL return an error: `"Error: Skill '<name>' not found."`
