## MODIFIED Requirements

### Requirement: Auto-routing after task creation
After a task is created and categorised, the backend SHALL automatically set the task's status based on its category and tags. If the task has a "Needs Info" tag, the task SHALL be set to status `review`. Otherwise: `immediate` tasks SHALL be moved to `pending`, and `scheduled` or `repeating` tasks SHALL be moved to `scheduled`. The task's `profile_id` SHALL be set based on the LLM classification result: if the LLM selected a valid profile name, `profile_id` is set to that profile's UUID; otherwise `profile_id` is null.

When the LLM succeeds but returns an empty or null `description` field, the task SHALL be created with any extracted scheduling information (category, execute_at, repeat_interval, repeat_until) but SHALL receive the "Needs Info" tag and route to `review` status, so the user can provide a proper task description.

The task creation endpoint SHALL use the LLM-cleaned description (`llm_result.description`) as the task's description. If the LLM did not return a description, the task description SHALL be set to null.

"Needs Info" SHALL mean that the classifier produced an answer and that answer did not carry what was needed. Where the classifier could not produce an answer at all — no model is configured, the configured provider no longer exists, or the request could not be completed — the task SHALL NOT receive the "Needs Info" tag and SHALL route by its category as an unclassified task would: the fallback title is used, the raw input is retained as the description, and an `immediate` task reaches `pending`.

The distinction is what the tag asserts to the user. "Needs Info" says *you did not tell us enough*, which is false when nobody was asked; a task parked on that basis is one the user cannot repair by editing, because nothing was missing from it. A newly installed system has no model configured, so every task created on it would otherwise be parked under a tag describing a fault that is not the user's.

A task created while no model is configured SHALL carry a machine-readable indication of that state, so a caller can explain the degraded classification rather than leaving the user to infer it from a task that behaved oddly.

#### Scenario: Immediate task without Needs Info moves to pending
- **WHEN** a task is created with category `immediate` and no "Needs Info" tag
- **THEN** the task's status is set to `pending`

#### Scenario: Scheduled task without Needs Info moves to scheduled
- **WHEN** a task is created with category `scheduled` and no "Needs Info" tag
- **THEN** the task's status is set to `scheduled`

#### Scenario: Repeating task without Needs Info moves to scheduled
- **WHEN** a task is created with category `repeating` and no "Needs Info" tag
- **THEN** the task's status is set to `scheduled`

#### Scenario: Task with Needs Info goes to review
- **WHEN** a task is created with category `immediate` but has the "Needs Info" tag
- **THEN** the task's status is set to `review`

#### Scenario: Short input goes to review
- **WHEN** a task is created with a short input (5 words or fewer)
- **THEN** the task gets the "Needs Info" tag, `profile_id` is null, and status is set to `review`

#### Scenario: LLM failure goes to review
- **WHEN** a task is created with a long input, the classifier runs, and it returns a response carrying no usable description
- **THEN** the task gets the "Needs Info" tag, `profile_id` is null, and status is set to `review`

#### Scenario: No model configured does not go to review
- **WHEN** a task is created with a long input on an installation where no model is configured
- **THEN** the task does not get the "Needs Info" tag
- **AND** an `immediate` task is set to status `pending`
- **AND** the task's description is the input the user supplied

#### Scenario: An unreachable classifier does not go to review
- **WHEN** a task is created with a long input and the classification request cannot be completed
- **THEN** the task does not get the "Needs Info" tag
- **AND** an `immediate` task is set to status `pending`

#### Scenario: The unconfigured state is reported, not implied
- **WHEN** a task is created while no model is configured
- **THEN** the response indicates that classification was skipped because no model is configured
- **AND** the indication is distinguishable from a classification that ran

#### Scenario: LLM selects profile during creation
- **WHEN** a task is created and the LLM returns `profile: "email-triage"` which matches an existing profile
- **THEN** the task's `profile_id` is set to the email-triage profile's UUID

#### Scenario: LLM returns empty description for scheduling-only input
- **WHEN** a task is created with input "Remind me in 2 hours" and the LLM returns category `scheduled`, execute_at set to 2 hours from now, but description is null or empty
- **THEN** the task is created with category `scheduled`, execute_at populated, description set to null, "Needs Info" tag applied, and status set to `review`

#### Scenario: Scheduled task uses cleaned description
- **WHEN** a task is created with input "In two hours, publish one of the approved tweets" and the LLM returns description "Publish one of the approved tweets"
- **THEN** the task's description is "Publish one of the approved tweets" (not the raw input)
