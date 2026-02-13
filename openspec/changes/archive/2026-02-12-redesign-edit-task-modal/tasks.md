## 1. Modal Container & Grid Layout

- [x] 1.1 Change modal form width from `w-[28rem]` to `max-w-3xl w-full` and add `max-h-[85vh] overflow-y-auto`
- [x] 1.2 Add a CSS Grid container (`grid grid-cols-1 md:grid-cols-2 gap-6`) inside the form, wrapping the field sections between the title and action buttons
- [x] 1.3 Make the Title input span both columns (`md:col-span-2`)
- [x] 1.4 Make the error message and action buttons section span both columns (`md:col-span-2`)

## 2. Left Column — Metadata Fields

- [x] 2.1 Wrap Status, Category, Execute at / Completed at, Repeat interval (conditional), Repeat until (conditional), and Tags into the left column (first grid cell, natural flow)

## 3. Right Column — Content Fields

- [x] 3.1 Wrap Description and Runner Logs into the right column (second grid cell)
- [x] 3.2 Increase Description textarea from `rows="3"` to `rows="8"`
- [x] 3.3 Replace Runner Logs `<details>/<summary>` with an always-visible read-only panel: heading label + `<pre>` block with `max-h-48 overflow-auto`, keeping the `v-if="task.runner_logs"` conditional

## 4. Tests

- [x] 4.1 Update runner logs tests in `TaskEditModal.test.ts` to query for the `<pre>` block directly instead of through `<details>/<summary>`
- [x] 4.2 Add test: two-column grid class is present on the layout container
- [x] 4.3 Add test: description textarea has `rows="8"`
- [x] 4.4 Run full frontend test suite and fix any regressions
