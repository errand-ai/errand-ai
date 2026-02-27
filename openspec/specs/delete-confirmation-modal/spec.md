## Purpose

Styled dialog modal for confirming task deletion, replacing the browser's native confirm() dialog.

## Requirements

### Requirement: Styled delete confirmation modal
The frontend SHALL display a Tailwind-styled `<dialog>` modal when the user requests to delete a task. The modal SHALL display the text "Delete this task?" with the task title, a destructive "Delete" button (red), and a "Cancel" button. The modal SHALL NOT use the browser's native `confirm()` dialog.

#### Scenario: Delete icon triggers styled modal
- **WHEN** the user clicks the delete icon on a task card
- **THEN** a styled modal dialog appears with the text "Delete this task?", the task title, a red "Delete" button, and a "Cancel" button

#### Scenario: Confirm delete via modal
- **WHEN** the user clicks the "Delete" button in the delete confirmation modal
- **THEN** the frontend sends `DELETE /api/tasks/{id}`, closes the modal, and removes the task card from the board

#### Scenario: Cancel delete via modal
- **WHEN** the user clicks the "Cancel" button in the delete confirmation modal
- **THEN** the modal closes and no API call is made

#### Scenario: Close modal via backdrop click
- **WHEN** the user clicks outside the delete confirmation modal (on the backdrop)
- **THEN** the modal closes and no API call is made

#### Scenario: Close modal via Escape key
- **WHEN** the user presses the Escape key while the delete confirmation modal is open
- **THEN** the modal closes and no API call is made

#### Scenario: Delete from edit modal uses styled confirmation
- **WHEN** the user clicks the Delete button inside the task edit modal
- **THEN** the same styled delete confirmation modal appears (not the native confirm dialog)

### Requirement: Delete confirmation modal visual consistency
The delete confirmation modal SHALL follow the same visual styling as the existing TaskEditModal, using Tailwind CSS classes for backdrop overlay, rounded card, padding, and button styles.

#### Scenario: Modal matches app styling
- **WHEN** the delete confirmation modal is open
- **THEN** it displays with a semi-transparent backdrop overlay, a centered white rounded card, and buttons styled consistently with the rest of the application
