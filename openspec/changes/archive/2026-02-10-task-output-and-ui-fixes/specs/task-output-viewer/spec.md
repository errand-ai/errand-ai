## ADDED Requirements

### Requirement: Task output viewer popup
The system SHALL provide a `TaskOutputModal` component that displays the captured execution output from a task in a read-only popup. The modal SHALL be implemented as a `<dialog>` element styled consistently with the existing `TaskEditModal`. The modal SHALL display the task title as the header, the output in a scrollable monospace `<pre>` block, and a "Close" button. The modal SHALL be dismissible by clicking the Close button, pressing Escape, or clicking the backdrop.

#### Scenario: View output of completed task
- **WHEN** the user clicks the "View Output" button on a task card in the Review column
- **THEN** a modal opens showing the task title as the header and the task's output field rendered in a scrollable monospace pre block

#### Scenario: View output of failed retry task
- **WHEN** the user clicks the "View Output" button on a task card in the Scheduled column that has output from a failed execution
- **THEN** a modal opens showing the task title as the header and the error output rendered in the monospace pre block

#### Scenario: Close output modal via button
- **WHEN** the output viewer modal is open and the user clicks "Close"
- **THEN** the modal closes

#### Scenario: Close output modal via Escape
- **WHEN** the output viewer modal is open and the user presses Escape
- **THEN** the modal closes

#### Scenario: Close output modal via backdrop click
- **WHEN** the output viewer modal is open and the user clicks the backdrop
- **THEN** the modal closes

#### Scenario: Large output is scrollable
- **WHEN** a task has output that exceeds the visible area of the modal
- **THEN** the output area is scrollable and the modal does not grow beyond a maximum height

#### Scenario: Empty output shows message
- **WHEN** the output viewer opens for a task with null or empty output
- **THEN** the modal displays a message "No output available"
