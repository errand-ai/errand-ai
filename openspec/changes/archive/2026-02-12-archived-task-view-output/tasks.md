## 1. Add View Output button to archived tasks table

- [x] 1.1 Import `TaskOutputModal` in `ArchivedTasksPage.vue` and add `outputTask` ref state
- [x] 1.2 Add an "Actions" column header to the table
- [x] 1.3 Add a "View Output" button cell to each row, conditionally rendered when `task.output` is non-null and non-empty, using `@click.stop` to prevent row-click propagation
- [x] 1.4 Add `TaskOutputModal` to the template, bound to `outputTask` state with close handler

## 2. Tests

- [x] 2.1 Add test: "View Output" button renders for tasks with output and does not render for tasks without
- [x] 2.2 Add test: clicking "View Output" opens the output modal with correct task title and output
- [x] 2.3 Run frontend tests and verify all pass
