## Why

Errand's value proposition is executing long, multi-step tasks and workflows, but the task creation input is a single-line `<input type="text">` that cannot accommodate complex descriptions. Users entering detailed workflow instructions are forced to type into a cramped field with no visibility of their full description, undermining the core UX.

## What Changes

- Replace the `<input type="text">` in TaskForm with an auto-growing `<textarea>` that starts at a single line and expands vertically as the user types longer descriptions
- The textarea starts visually identical to the current single-line input (same height, same styling)
- As content exceeds one line, the textarea grows to fit — up to a sensible maximum height (e.g. ~6 lines), after which it scrolls
- On submission the textarea clears and shrinks back to its initial single-line height
- Submit on Enter is preserved (Shift+Enter for newlines), maintaining the quick-entry feel for simple tasks

## Capabilities

### New Capabilities

_None — this is a UI enhancement within an existing component._

### Modified Capabilities

- `kanban-frontend`: TaskForm input changes from `<input>` to auto-growing `<textarea>`, affecting form layout, submission behaviour (Enter vs Shift+Enter), and disabled state styling
- `voice-input`: Transcription result insertion must work with the new textarea element (focus and value setting)

## Impact

- **Component library** (`@errand-ai/ui-components`): `TaskForm.vue` — input element replacement, auto-resize logic
- **Frontend tests**: TaskForm and KanbanBoard tests that reference the text input element will need updating for the textarea
- **No backend changes**
- **No API changes**
