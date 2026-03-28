## 1. Replace input with auto-growing textarea

- [x] 1.1 In `TaskForm.vue`, replace the `<input type="text">` with a `<textarea>` element. Apply `resize: none`, set `rows="1"`, and match existing styling (border, padding, placeholder, disabled states). Change the `inputRef` type from `HTMLInputElement` to `HTMLTextAreaElement`.
- [x] 1.2 Add auto-resize logic: on the textarea's `input` event, set `style.height = 'auto'` then `style.height = scrollHeight + 'px'`. Cap growth at `max-height: 144px` (approx 6 lines) with `overflow-y: auto` when content exceeds max height.
- [x] 1.3 After successful form submission (input cleared), reset the textarea height to initial single-line height.

## 2. Enter/Shift+Enter key handling

- [x] 2.1 Add a `keydown` handler on the textarea: if Enter is pressed without Shift, call `preventDefault()` and trigger `submit()`. If Shift+Enter, allow the default newline insertion.
- [x] 2.2 After Shift+Enter inserts a newline, trigger the auto-resize logic so the textarea grows to accommodate the new line.

## 3. Voice input compatibility

- [x] 3.1 In the `onTranscription` handler, after appending text to the textarea value, trigger the auto-resize logic so the textarea height adjusts to fit the transcribed content.

## 4. Tests

- [x] 4.1 Update TaskForm unit tests: change element selectors from `input[type="text"]` / `<input>` to `<textarea>`. Verify the textarea renders with placeholder "New task..." and submits on Enter.
- [x] 4.2 Add test: textarea grows when multi-line content is entered (verify style.height changes).
- [x] 4.3 Add test: Enter submits form, Shift+Enter inserts newline (verify form submission vs textarea content).
- [x] 4.4 Add test: textarea height resets to initial height after successful submission.
- [x] 4.5 Update KanbanBoard integration tests if they reference the task input element type.
