## Purpose

MCP tools for creating tasks with a profile or explicit title and for listing available task profiles.
## Requirements
### Requirement: Create task with profile via MCP
The `new_task` MCP tool SHALL accept an optional `profile` parameter to assign a task profile by name.

#### Scenario: Task created with valid profile
- **WHEN** `new_task` is called with `profile="Research Agent"`
- **THEN** the tool SHALL resolve the profile name to its ID
- **THEN** the task SHALL be created with the resolved `profile_id`
- **THEN** the task SHALL go to `pending` status for immediate execution

#### Scenario: Task created without profile
- **WHEN** `new_task` is called without the `profile` parameter
- **THEN** the tool SHALL behave as it does today (LLM-based profile auto-assignment for descriptions over 5 words)

#### Scenario: Invalid profile name
- **WHEN** `new_task` is called with a `profile` that does not exist
- **THEN** the tool SHALL return an error message: `"Error: Task profile '<name>' not found."`

### Requirement: Create task with explicit title via MCP
The `new_task` MCP tool SHALL accept an optional `title` parameter to set the task title directly, bypassing the LLM summariser.

#### Scenario: Task created with explicit title
- **WHEN** `new_task` is called with `title="My Task"` and `description="Do the thing"`
- **THEN** the task SHALL be created with title `"My Task"` and description `"Do the thing"`
- **THEN** the LLM summariser SHALL NOT be called
- **THEN** the category SHALL default to `"immediate"`

#### Scenario: Task created without title
- **WHEN** `new_task` is called without the `title` parameter
- **THEN** the tool SHALL behave as it does today (LLM generates title for descriptions over 5 words, short descriptions used as title directly)

### Requirement: List task profiles via MCP
The MCP server SHALL provide a `list_task_profiles` tool that returns available task profiles.

#### Scenario: Profiles listed successfully
- **WHEN** `list_task_profiles` is called
- **THEN** the tool SHALL return a JSON array of objects with `name`, `description`, and `model` fields for each profile

#### Scenario: No profiles configured
- **WHEN** `list_task_profiles` is called and no profiles exist
- **THEN** the tool SHALL return an empty JSON array

### Requirement: Clone task profile via MCP
The MCP server SHALL provide `clone_task_profile(source_profile, new_name, model?, llm_timeout?, max_turns?)` which creates a new profile copying all fields from `source_profile` and applying the provided overrides. `new_name` MUST start with `eval--`; other names SHALL be rejected. Cloning from a nonexistent source SHALL return an error. If a profile named `new_name` already exists, the tool SHALL return success with the existing profile's details (idempotent reuse) without modifying it.

#### Scenario: Eval profile cloned with model override
- **WHEN** `clone_task_profile(source_profile="job-research", new_name="eval--job-research--gemma4", model="gemma4-27b")` is called
- **THEN** a profile `eval--job-research--gemma4` exists with job-research's system prompt, skills, and MCP servers, and the overridden model

#### Scenario: Non-eval name rejected
- **WHEN** `clone_task_profile(source_profile="job-research", new_name="job-research-v2")` is called
- **THEN** the tool returns an error stating clone names must start with `eval--` and no profile is created

#### Scenario: Existing eval profile reused
- **WHEN** `clone_task_profile` is called with a `new_name` that already exists
- **THEN** the tool returns the existing profile without error or modification

### Requirement: Delete task profile via MCP
The MCP server SHALL provide `delete_task_profile(name)` which deletes the named profile. Names not starting with `eval--` SHALL be rejected without deletion. Deleting a nonexistent `eval--*` profile SHALL succeed idempotently.

#### Scenario: Eval profile deleted
- **WHEN** `delete_task_profile(name="eval--job-research--gemma4")` is called
- **THEN** the profile is removed (tasks that referenced it keep running history via `ON DELETE SET NULL`)

#### Scenario: Production profile protected
- **WHEN** `delete_task_profile(name="email-triage")` is called
- **THEN** the tool returns an error and the profile is not deleted

#### Scenario: Idempotent delete
- **WHEN** `delete_task_profile` is called for an `eval--*` name that does not exist
- **THEN** the tool returns success

