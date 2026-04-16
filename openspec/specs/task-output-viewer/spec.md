## Purpose

Modal component for viewing task execution output rendered as formatted markdown with DOMPurify sanitisation.

## Requirements

### Requirement: Task output viewer popup
The system SHALL provide a `TaskOutputModal` component that displays the captured execution output from a task in a read-only popup. The modal SHALL be implemented as a `<dialog>` element styled consistently with the existing `TaskEditModal`. The modal SHALL use a responsive width of `w-[90vw] max-w-5xl` to fill approximately two-thirds of the viewport on wide screens. The modal SHALL display the task title as the header. The modal SHALL parse the output as markdown and render it as formatted HTML using `marked`, sanitized with `DOMPurify` at version `>= 3.4.0` (the minimum version required to close the default-config XSS class GHSA-v2wj-7wpq-c8vv and the mutation-XSS re-contextualization class GHSA-h8r8-wccr-v5f2, both of which affect `DOMPurify.sanitize()` calls without custom configuration options), and styled with Tailwind's `prose` class. The rendered output area SHALL be scrollable with a maximum modal height of `80vh`. The modal SHALL be dismissible by clicking the Close button, pressing Escape, or clicking the backdrop.

#### Scenario: View output of completed task
- **WHEN** the user clicks the "View Output" button on a task card in the Review column
- **THEN** a modal opens showing the task title as the header and the task's output field rendered as formatted markdown in a scrollable container

#### Scenario: View output of failed retry task
- **WHEN** the user clicks the "View Output" button on a task card in the Scheduled column that has output from a failed execution
- **THEN** a modal opens showing the task title as the header and the error output rendered as formatted markdown

#### Scenario: Markdown headings and lists render correctly
- **WHEN** the output contains markdown headings (`#`, `##`), bullet lists (`-`, `*`), and horizontal rules (`---`)
- **THEN** the modal renders them as styled HTML heading elements, unordered list elements, and `<hr>` separators

#### Scenario: Markdown code blocks render correctly
- **WHEN** the output contains fenced code blocks (triple backticks)
- **THEN** the modal renders them as `<pre><code>` blocks with monospace styling

#### Scenario: Plain text output renders without degradation
- **WHEN** the output contains no markdown formatting
- **THEN** the modal renders it as plain text paragraphs with no visual artifacts

#### Scenario: HTML in output is sanitized
- **WHEN** the output contains raw HTML tags (e.g. `<script>`, `<iframe>`)
- **THEN** the rendered output has dangerous tags stripped by DOMPurify

#### Scenario: Mutation-XSS payload class is neutralised
- **WHEN** the task output contains a payload from the GHSA-h8r8-wccr-v5f2 mutation-XSS re-contextualization class (HTML that would evade pre-3.3.2 default-config `DOMPurify.sanitize` when re-parsed into a template context)
- **THEN** the rendered DOM contains no executable script context and no `on*` event-handler attributes derived from the payload

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

#### Scenario: Modal uses responsive width
- **WHEN** the output modal is opened on a wide display (viewport > 1280px)
- **THEN** the modal width is approximately two-thirds of the viewport, capped at `64rem`

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
