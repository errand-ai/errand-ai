## Context

The TaskForm component in `@errand-ai/ui-components` uses a single-line `<input type="text">` for task description entry. This works for short tasks but is inadequate for Errand's core use case: long, multi-step workflow descriptions. The input cannot display more than one line of text, giving users no visibility into what they've typed for complex descriptions.

The TaskForm is consumed by the errand frontend via `KanbanBoard.vue`, which passes voice input through a slot. The form handles submission via Enter key and exposes an `onTranscription` callback for voice input.

## Goals / Non-Goals

**Goals:**
- Replace the `<input>` with a `<textarea>` that starts at single-line height and grows as content is added
- Maintain the current look and feel for simple single-line tasks (no visual regression)
- Preserve Enter-to-submit behaviour for quick task entry
- Support Shift+Enter for explicit newlines in multi-line descriptions
- Ensure voice transcription insertion continues to work with the new element

**Non-Goals:**
- Markdown editing or preview in the task input
- A separate "expanded" composition modal (potential future enhancement)
- Rich text formatting
- Changes to the backend or API

## Decisions

### 1. CSS `field-sizing: content` vs JavaScript auto-resize

**Decision**: Use JavaScript auto-resize (`scrollHeight` adjustment on input event).

**Rationale**: `field-sizing: content` is the ideal CSS-native solution but has limited browser support (Chrome 123+, no Firefox/Safari as of early 2026). JavaScript auto-resize is universally supported and well-understood. The implementation is minimal: set `height: auto`, then `height: scrollHeight + 'px'` on each input event.

**Alternatives considered**:
- `field-sizing: content` — elegant but browser support too narrow
- Third-party auto-resize library — unnecessary overhead for ~5 lines of JS

### 2. Maximum height with scroll

**Decision**: Cap the textarea growth at approximately 6 lines (~144px at text-sm), then allow scrolling.

**Rationale**: Unbounded growth would push the kanban board down excessively. 6 lines provides enough visibility for a detailed task description while keeping the form compact. Users with even longer descriptions can scroll within the textarea.

### 3. Enter vs Shift+Enter behaviour

**Decision**: Enter submits the form. Shift+Enter inserts a newline.

**Rationale**: This matches the convention of chat applications (Slack, Discord, ChatGPT) that users are familiar with. It preserves the quick-submit feel of the current input for simple tasks while allowing multi-line entry when needed. The textarea will handle the `keydown` event to intercept Enter (without Shift) and trigger form submission.

### 4. Textarea reset on submission

**Decision**: After successful submission, clear the value and reset height to the initial single-line height.

**Rationale**: The textarea should return to its compact initial state after each task is created, maintaining the clean appearance of the form.

## Risks / Trade-offs

- **Enter key convention**: Some users may expect Enter to create a newline in a textarea. Mitigated by the widespread chat-app convention of Enter-to-send, Shift+Enter-for-newline. This is the same convention the existing input uses (Enter submits).
- **Mobile keyboards**: On mobile, the Enter key on the virtual keyboard should still submit. Shift+Enter may be less discoverable on mobile. Accepted trade-off — mobile users can still type multi-line by pasting or using voice input.
- **Test updates**: Existing tests reference `<input>` elements; they'll need updating to target `<textarea>`. Straightforward but touches multiple test files.
