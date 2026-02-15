## MODIFIED Requirements

### Requirement: Task output viewer popup
The task output viewer modal SHALL include a "Copy raw" button alongside the existing Close button in the modal footer. Clicking "Copy raw" SHALL copy the raw (unrendered) output text to the clipboard using `navigator.clipboard.writeText()`. After a successful copy, the button text SHALL change to "Copied!" for 2 seconds before reverting to "Copy raw". The button SHALL be styled consistently with the Close button but as a secondary/outline variant.

#### Scenario: Copy raw output to clipboard
- **WHEN** the output modal is open showing task output and the user clicks "Copy raw"
- **THEN** the raw output text (not the rendered HTML) is copied to the clipboard

#### Scenario: Copy confirmation feedback
- **WHEN** the user clicks "Copy raw" and the copy succeeds
- **THEN** the button text changes to "Copied!" for 2 seconds then reverts to "Copy raw"

#### Scenario: Copy button position
- **WHEN** the output modal is open
- **THEN** the "Copy raw" button appears next to the "Close" button in the modal footer
