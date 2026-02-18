## MODIFIED Requirements

### Requirement: /task new command — automatic slack tag
The `/task new` slash command SHALL automatically add a `slack` tag to every task it creates. The tag SHALL be added after the task is committed to the database, using the existing tag find-or-create logic.

#### Scenario: Slash command task gets slack tag
- **WHEN** a Slack user issues `/task new Write documentation`
- **THEN** the created task has a `slack` tag associated with it

#### Scenario: Slack tag created if not exists
- **WHEN** no `slack` tag exists in the database and a task is created via `/task new`
- **THEN** a new `slack` tag is created and associated with the task
