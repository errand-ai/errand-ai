## Context

TaskForm.vue is the component where users type a task description and submit it via Enter key or clicking "Add Task". The `submit()` function calls `store.addTask(input)` which POSTs to `/api/tasks` and then reloads all tasks. During this async operation (which includes LLM title generation on the backend), the form remains fully interactive — users can press Enter again or click the button again, creating duplicate tasks.

## Goals / Non-Goals

**Goals:**
- Prevent double-submission by disabling all form inputs immediately on submit
- Provide clear visual feedback that a submission is in progress
- Re-enable the form after the API call completes (success or failure)

**Non-Goals:**
- Adding a loading spinner or progress bar (simple disable/gray-out is sufficient)
- Changing the API or store layer
- Adding debounce or throttle logic (disabling the form is the primary guard)

## Decisions

### Use a reactive `submitting` ref to gate form interactivity

Add a `submitting` ref<boolean> that is set to `true` at the start of `submit()` and `false` in a `finally` block. Bind `:disabled="submitting"` on the input, submit button, and voice input button.

**Rationale**: This is the simplest approach — a single boolean controls all form elements. Using `finally` ensures the form is re-enabled even if the API call throws. No new dependencies or patterns needed.

**Alternative considered**: Debouncing the submit function — rejected because it doesn't provide visual feedback and still allows brief double-clicks.

### Gray-out styling via Tailwind disabled variants

Use Tailwind's `disabled:` variant to style the disabled state: `disabled:opacity-50 disabled:cursor-not-allowed` on the input and button. No custom CSS needed.

**Rationale**: Consistent with the existing Tailwind approach used throughout the app. The opacity change is a widely-understood visual signal for "disabled".

## Risks / Trade-offs

- [Form stays disabled if `finally` doesn't fire] → Extremely unlikely in normal browser JS execution; `finally` is reliable for async/await.
- [User may not notice the subtle gray-out] → The cursor change to `not-allowed` provides an additional signal. A spinner could be added later if needed, but this is a non-goal for now.
