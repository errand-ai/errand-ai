## MODIFIED Requirements

### Requirement: Skill manifest in system prompt
When the worker prepares the system prompt for a task, the worker SHALL append a skill discovery directive and manifest as the sole augmentation block (after the base prompt). The manifest SHALL list all skills (from DB, git, and system sources) with their name and description. The directive SHALL instruct the agent to read the SKILL.md of any relevant skill before using associated tools or capabilities.

The system prompt SHALL NOT contain any other integration-specific instruction blocks. All integration instructions (cloud storage, Hindsight, repo context) are delivered via system skills listed in the manifest.

#### Scenario: Skills exist — lean prompt with manifest
- **WHEN** the worker prepares the system prompt and skills exist from any source
- **THEN** the system prompt contains: base prompt + skill manifest with discovery directive
- **AND** the system prompt does NOT contain inline cloud storage instructions, Hindsight instructions, or repo context instructions

#### Scenario: No skills — base prompt only
- **WHEN** the worker prepares the system prompt and no skills exist from any source
- **THEN** the system prompt contains only the base prompt and output format instructions

#### Scenario: Manifest includes system skills
- **WHEN** the worker prepares the system prompt with system skills (e.g., cloud-storage, hindsight-memory, repo-context, gws-*)
- **THEN** the manifest table includes entries for all system skills alongside DB and git skills
