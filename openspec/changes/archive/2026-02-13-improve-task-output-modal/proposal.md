## Why

The task output modal (`TaskOutputModal.vue`) displays LLM-generated output as raw monospace text in a fixed `36rem` wide container. On wide displays this uses roughly a third of the available viewport, wasting screen space and making long outputs harder to read. Additionally, LLM output frequently contains markdown (headings, bullet lists, horizontal rules, code blocks) which is rendered as plain text, reducing readability.

## What Changes

- **Widen the output modal**: Replace the fixed `w-[36rem]` width with a responsive width that uses approximately two-thirds of the viewport on wide screens, while remaining sensible on smaller screens.
- **Render markdown in output**: Parse the task output as markdown and render it as formatted HTML (headings, lists, separators, code blocks, etc.) instead of displaying raw text in a `<pre>` block.
- **Add a markdown rendering dependency**: Introduce a lightweight markdown-to-HTML library (e.g. `marked`) to the frontend.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-output-viewer`: Add requirements for responsive modal width and markdown rendering of output content.

## Impact

- **Frontend**: `TaskOutputModal.vue` — template and styling changes, new markdown rendering logic.
- **Dependencies**: New npm package for markdown parsing (e.g. `marked`).
- **No backend changes**: Output is already stored as plain text; rendering is purely frontend.
- **No breaking changes**: The modal still displays the same data, just formatted differently.
