## MODIFIED Requirements

### Requirement: Cloud storage system prompt instructions
When at least one cloud storage MCP server is injected, the worker SHALL include the `cloud-storage` system skill in the skills archive instead of appending the `CLOUD_STORAGE_INSTRUCTIONS` constant to the system prompt.

#### Scenario: OneDrive injected
- **WHEN** worker injects the OneDrive MCP server
- **THEN** the `cloud-storage` system skill is included in the skills archive
- **AND** the system prompt does NOT contain inline cloud storage instructions

#### Scenario: No cloud storage injected
- **WHEN** no cloud storage MCP servers are injected
- **THEN** the `cloud-storage` system skill is NOT included in the skills archive

## REMOVED Requirements

### Requirement: Inline cloud storage instructions in system prompt
**Reason**: Cloud storage instructions are now delivered as a system skill (`cloud-storage/SKILL.md`) that the agent reads on demand, reducing baseline system prompt size.
**Migration**: The `CLOUD_STORAGE_INSTRUCTIONS` constant is removed from `task_manager.py`. Instructions are now at `/app/system-skills/cloud-storage/cloud-storage/SKILL.md`.
