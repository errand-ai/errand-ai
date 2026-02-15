## MODIFIED Requirements

### Requirement: Skill deletion requires confirmation
The frontend Skills section SHALL require user confirmation before deleting a skill. Clicking the Delete button SHALL open a confirmation dialog (reusing the `<dialog>` pattern from task deletion) showing the skill name and asking "Delete this skill?". The skill SHALL only be removed from the skills array and saved after the user confirms. This requirement applies to the UI behavior only; the backend API for saving skills is unchanged.

#### Scenario: Delete button opens confirmation
- **WHEN** an admin clicks the Delete button next to a skill
- **THEN** a confirmation dialog appears instead of immediately deleting the skill

#### Scenario: Confirmed deletion proceeds
- **WHEN** the user confirms the skill deletion
- **THEN** the skill is removed from the list, the updated skills array is saved via PUT /api/settings, and a success toast is shown

#### Scenario: Cancelled deletion preserves skill
- **WHEN** the user cancels the skill deletion confirmation
- **THEN** the skill remains in the list unchanged
