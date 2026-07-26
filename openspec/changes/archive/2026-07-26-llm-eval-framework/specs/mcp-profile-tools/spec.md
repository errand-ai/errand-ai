## ADDED Requirements

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
