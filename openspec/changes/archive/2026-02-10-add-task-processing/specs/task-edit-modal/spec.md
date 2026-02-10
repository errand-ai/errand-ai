## MODIFIED Requirements

### Requirement: Task edit modal displays editable fields
The task edit modal SHALL be implemented as a `<dialog>` element. It SHALL display editable fields for the task title, description, status, and tags, along with Save and Cancel buttons.

#### Scenario: Modal shows current task data
- **WHEN** the edit modal opens for a task with title "Process report", description "Generate the quarterly report from the data warehouse", status "running", and tags "urgent"
- **THEN** the title input contains "Process report", the description textarea contains the description text, the status selector shows "Running", and the tag "urgent" is displayed

#### Scenario: Status selector shows all valid statuses
- **WHEN** the edit modal is open
- **THEN** the status field SHALL present six statuses as selectable options: New, Scheduled, Pending, Running, Review, Completed

### Requirement: Description field in edit modal
The edit modal SHALL display a textarea for the task description below the title field. The description is optional — the textarea MAY be empty. Changes to the description SHALL be included in the PATCH request when saving.

#### Scenario: Edit description
- **WHEN** the user modifies the description text and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with the updated description

#### Scenario: Empty description
- **WHEN** the user clears the description and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"description": ""}` (or null)

### Requirement: Tag input with autocomplete
The edit modal SHALL display a tag input area below the description. Existing tags for the task SHALL be shown as removable pills/badges. A text input SHALL allow adding new tags. As the user types, a dropdown SHALL appear showing matching existing tags from `GET /api/tags?q=<prefix>` (debounced at 200ms). The user MAY select a tag from the dropdown or press Enter to create a new tag with the typed text.

#### Scenario: Autocomplete shows matching tags
- **WHEN** the user types "urg" in the tag input
- **THEN** a dropdown appears showing tags that start with "urg" (e.g., "urgent")

#### Scenario: Select tag from dropdown
- **WHEN** the user clicks a tag in the autocomplete dropdown
- **THEN** the tag is added to the task's tag list as a pill and the input is cleared

#### Scenario: Create new tag by pressing Enter
- **WHEN** the user types "new-tag" and presses Enter (and no dropdown selection is active)
- **THEN** "new-tag" is added to the task's tag list as a pill and the input is cleared

#### Scenario: Remove a tag
- **WHEN** the user clicks the remove button on a tag pill
- **THEN** the tag is removed from the task's tag list

#### Scenario: Save includes tags
- **WHEN** the user modifies tags and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"tags": ["tag1", "tag2"]}` containing the full current tag list

## REMOVED Requirements

### Requirement: Need Input status option
**Reason**: The "Need Input" status is removed. Tasks needing additional information are now indicated via the "Needs Info" tag instead of a dedicated status.
**Migration**: The status selector in the edit modal no longer includes "Need Input" as an option.
