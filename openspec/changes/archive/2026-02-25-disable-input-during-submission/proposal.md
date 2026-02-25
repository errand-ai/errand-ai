## Why

When a user submits a new task via the TaskForm input, there is a noticeable delay while the backend creates the task and the LLM generates a title. During this delay, nothing visually changes — the input stays active and the button stays clickable. This leads to accidental double submissions (pressing Enter twice or clicking twice) which creates duplicate tasks. The form needs immediate visual feedback that submission is in progress.

## What Changes

- Add a `submitting` loading state to TaskForm that activates immediately on form submission
- Disable the text input and submit button while `submitting` is true
- Apply a grayed-out visual style to the disabled input and button
- Re-enable the form after the API call completes (success or error)
- Also disable the voice input button during submission to prevent all input paths

## Capabilities

### New Capabilities

_None_ — this is a UX improvement to an existing component.

### Modified Capabilities

- `kanban-frontend`: TaskForm adds a submitting/loading state that disables all inputs during task creation API calls

## Impact

- **Frontend only**: `TaskForm.vue` component — add reactive `submitting` ref, wire it to `submit()` async flow
- **No backend changes**: The API and store remain unchanged
- **No breaking changes**: Pure additive UX behavior
