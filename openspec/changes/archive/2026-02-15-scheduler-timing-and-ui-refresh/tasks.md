## 1. Scheduler Poll Interval

- [x] 1.1 Change `SCHEDULER_INTERVAL` default from `30` to `15` in `backend/scheduler.py`
- [x] 1.2 Update the existing scheduler tests that assert the default interval (if any reference the 30s value)

## 2. Frontend Live Countdown

- [x] 2.1 Create `useNow` composable in `frontend/src/composables/useNow.ts` that returns a reactive `Ref<Date>` updated every 30 seconds, with cleanup via `onScopeDispose`
- [x] 2.2 Add optional `now` parameter to `formatRelativeTime(isoString, now?)` in `useRelativeTime.ts` (defaults to `new Date()` for backward compatibility)
- [x] 2.3 Update `TaskCard.vue` to use `useNow(30000)` and pass the reactive `now` to `formatRelativeTime`, but only when `columnStatus === 'scheduled'`
- [x] 2.4 Add unit tests for `useNow` composable (returns a ref, updates on interval, cleans up on dispose)
- [x] 2.5 Add/update unit tests for `formatRelativeTime` with explicit `now` parameter
- [x] 2.6 Add unit test for TaskCard verifying the relative time display updates when the `now` ref changes

## 3. Spec Sync and Verification

- [x] 3.1 Run full backend test suite and verify all scheduler tests pass
- [x] 3.2 Run full frontend test suite and verify all TaskCard/relative time tests pass
