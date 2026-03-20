## MODIFIED Requirements

### Requirement: Agent discovers capabilities via skills
The task-runner agent SHALL discover integration-specific instructions by reading SKILL.md files from `/workspace/skills/` rather than receiving them inline in the system prompt. The agent SHALL read the skill manifest in the system prompt to identify relevant skills, then read their SKILL.md files before using the associated tools or capabilities.

#### Scenario: Agent reads cloud storage skill before using cloud tools
- **WHEN** the agent needs to interact with cloud storage (OneDrive)
- **AND** the skills manifest lists a `cloud-storage` skill
- **THEN** the agent reads `/workspace/skills/cloud-storage/SKILL.md` before making cloud storage tool calls

#### Scenario: Agent initiates Hindsight recall
- **WHEN** a task starts and the skills manifest lists a `hindsight-memory` skill
- **THEN** the agent reads the skill and uses Hindsight MCP tools to recall relevant context
- **AND** the agent retains important learnings before completing the task

#### Scenario: Agent discovers repo context conventions
- **WHEN** the agent clones a repository and the skills manifest lists a `repo-context` skill
- **THEN** the agent reads the skill and follows the instructions to discover CLAUDE.md, commands, and repo-level skills

#### Scenario: Agent works without skills
- **WHEN** no skills are available (manifest absent)
- **THEN** the agent proceeds using MCP tool schemas and its base instructions without reading any skill files
