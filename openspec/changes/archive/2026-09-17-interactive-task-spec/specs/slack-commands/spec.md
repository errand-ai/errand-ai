## MODIFIED Requirements

### Requirement: /task new command
The `/task new <description>` slash command SHALL start a clarification draft (see `task-spec-intake`) instead of creating a task immediately. The draft's owner SHALL be the Slack user's resolved email address (falling back to `slack:<user_id>`). The response SHALL be the Block Kit draft message: the spec preview or the clarifying questions, with Submit / Just run it / Cancel actions. The task is created, with `created_by` set to the owner, only when the user confirms the draft.

#### Scenario: Create task from Slack
- **WHEN** a Slack user issues `/task new Write blog post about Kubernetes` and then clicks Run on the returned draft message
- **THEN** a task is created from the resolved spec with `created_by` set to the user's email, and the draft message is replaced by the Block Kit task confirmation

#### Scenario: Missing title
- **WHEN** a Slack user issues `/task new` with no title text
- **THEN** an error response is returned: "Usage: `/task new <description>`"

#### Scenario: No task before confirmation
- **WHEN** a Slack user issues `/task new send me the quarterly numbers`
- **THEN** the response contains the draft's clarifying questions and no task exists yet
