## ADDED Requirements

### Requirement: Hindsight memory system skill
A system skill SHALL exist at `/app/system-skills/hindsight/hindsight-memory/SKILL.md` containing instructions for using the Hindsight persistent memory system. The skill SHALL instruct the agent to: (1) recall relevant context at the start of the task using Hindsight MCP tools, (2) use its own judgment about what queries to make, and (3) retain important learnings, decisions, and patterns at the end of the task.

#### Scenario: Skill included when Hindsight configured
- **WHEN** the task manager prepares a task and a Hindsight MCP server URL is configured
- **THEN** the `hindsight` skill set is included in the skills archive

#### Scenario: Skill excluded when Hindsight not configured
- **WHEN** the task manager prepares a task and no Hindsight URL is configured
- **THEN** the `hindsight` skill set is not included

#### Scenario: Skill directs agent to recall at task start
- **WHEN** an agent reads `/workspace/skills/hindsight-memory/SKILL.md`
- **THEN** the instructions direct the agent to use `recall` to load relevant context before beginning work

#### Scenario: Skill directs agent to retain at task end
- **WHEN** an agent reads `/workspace/skills/hindsight-memory/SKILL.md`
- **THEN** the instructions direct the agent to use `retain` to save important findings before completing the task

### Requirement: Server-side Hindsight prefetch removed
The task manager SHALL NOT pre-fetch Hindsight memories server-side. The `recall_from_hindsight()` function and the "Relevant Context from Memory" system prompt section SHALL be removed. The agent is responsible for recalling context using the Hindsight MCP tools as directed by the skill.

#### Scenario: No server-side recall
- **WHEN** the task manager prepares a task with Hindsight configured
- **THEN** no HTTP call is made to the Hindsight REST API for pre-fetching memories
- **AND** the system prompt does not contain a "Relevant Context from Memory" section

#### Scenario: Agent recalls context itself
- **WHEN** the agent starts a task and the hindsight-memory skill is available
- **THEN** the agent uses the Hindsight MCP `recall` tool to load relevant context
