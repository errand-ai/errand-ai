## 1. Grid Layout Changes

- [ ] 1.1 Change the grid class on the two-column container from `md:grid-cols-2` to `md:grid-cols-[1fr_2fr]` in `TaskEditModal.vue`
- [ ] 1.2 Convert the right column from `space-y-4` to `flex flex-col gap-4` and set the description container to `flex-1` with the textarea using `h-full min-h-[8rem]`

## 2. Runner Logs Repositioning

- [ ] 2.1 Move the runner logs block out of the right column and into a full-width `md:col-span-2` row between the content columns and the action buttons row

## 3. Tests

- [ ] 3.1 Update `TaskEditModal.test.ts` assertions for the new grid class (`grid-cols-[1fr_2fr]`)
- [ ] 3.2 Update test assertions for runner logs position (now full-width bottom row instead of right column)
- [ ] 3.3 Update any test assertions for the description textarea flex-grow layout
- [ ] 3.4 Run full frontend test suite and verify all tests pass
