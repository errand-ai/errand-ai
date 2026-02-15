## MODIFIED Requirements

### Requirement: Task edit modal dismissal behavior
The task edit modal SHALL be dismissible by clicking the Cancel button, pressing Escape, or clicking the backdrop (outside the modal content area). Backdrop-click dismissal SHALL be implemented via `@click.self` on the `<dialog>` element. When the form has unsaved changes (any field value differs from the original task props), backdrop click and Escape SHALL show a browser `confirm("Discard unsaved changes?")` dialog before closing. If the user cancels the confirmation, the modal SHALL remain open. If the form has no unsaved changes, the modal SHALL close immediately on backdrop click or Escape.

#### Scenario: Backdrop click closes clean modal
- **WHEN** the edit modal is open with no changes made and the user clicks the backdrop
- **THEN** the modal closes immediately

#### Scenario: Backdrop click with unsaved changes shows confirmation
- **WHEN** the edit modal has unsaved changes and the user clicks the backdrop
- **THEN** a confirmation dialog "Discard unsaved changes?" appears

#### Scenario: User confirms discard on backdrop click
- **WHEN** the confirmation dialog is shown and the user clicks OK
- **THEN** the modal closes and changes are discarded

#### Scenario: User cancels discard on backdrop click
- **WHEN** the confirmation dialog is shown and the user clicks Cancel
- **THEN** the modal remains open with the user's changes preserved

#### Scenario: Escape with unsaved changes shows confirmation
- **WHEN** the edit modal has unsaved changes and the user presses Escape
- **THEN** a confirmation dialog "Discard unsaved changes?" appears
