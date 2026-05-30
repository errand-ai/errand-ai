## 1. Bump version and create feature branch

- [x] 1.1 Bump `VERSION` from `0.122.0` to `0.123.0` (minor — new feature, backwards-compatible)
- [x] 1.2 Create feature branch `cap-runner-retry-storm`

## 2. Server-side: retry cap + backoff ceiling in TaskManager

- [x] 2.1 Add module-level constants in `errand/task_manager.py`: `MAX_RETRY_BACKOFF_MINUTES = 60` and `DEFAULT_MAX_RETRY_ATTEMPTS = 5`
- [x] 2.2 Add a helper `_get_max_retry_attempts(session)` that resolves via `_get_setting` with env → DB → default, clamping `<= 0` to `1` and falling back to the default on non-integer DB values; emit a single WARNING log on the fallback path
- [x] 2.3 In `_schedule_retry`, read the current row's `retry_count`; if `current.retry_count >= max_retry_attempts - 1`, divert to a new private helper `_escalate_to_review_failed(task, output, runner_logs)` instead of computing backoff and writing `scheduled`
- [x] 2.4 In `_schedule_retry`, change backoff to `min(2 ** current.retry_count, MAX_RETRY_BACKOFF_MINUTES)` for the non-escalation path
- [x] 2.5 Implement `_escalate_to_review_failed`: writes `status="review"`, `output="Task exceeded max retries (<n>) — last failure: ...<truncated output>"`, `runner_logs`, `retry_count = retry_count + 1`, `updated_by="system"`, `updated_at=now()`, `position = _next_position("review")`
- [x] 2.6 In `_escalate_to_review_failed`, ensure the `Failed` tag exists (lazy create with the same `select → if None: add` pattern used for `Retry`), remove any `Retry` tag association on the task, and add the `Failed` tag association
- [x] 2.7 Emit `publish_event("task_updated", _task_to_dict(task))` after escalation, mirroring the existing post-update event publication
- [x] 2.8 Add the INFO log `"Task <id> exceeded max retries (<n>), moved to review"` on escalation
- [x] 2.9 Verify the `GitSkillsError` branch (currently uses its own `MAX_GIT_RETRIES` flow) is untouched and never reaches `_escalate_to_review_failed`

## 3. Runner-side: widen 401 detection in execute_command

- [x] 3.1 In `task-runner/main.py`, locate the existing `execute_command` substring check for `"status": "UNAUTHENTICATED"` and extract it into a named helper `_is_google_token_expired(output: str) -> bool` (preserves existing behaviour exactly)
- [x] 3.2 Extend `_is_google_token_expired` to also return `True` when both `"code": 401` and `"Request had invalid authentication credentials"` appear in the same `output` string (case-sensitive, literal substrings)
- [x] 3.3 Wire `_is_google_token_expired` into the existing refresh decision; ensure the one-retry-per-invocation cap, the module-level refresh lock, and the `token_refreshed` event emission are unchanged
- [x] 3.4 Confirm the rerun path uses the mutated `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` and the same args/cwd as the original invocation

## 4. Tests

- [x] 4.1 Add `errand/tests/test_task_manager_retry_cap.py` — unit tests covering: (a) `retry_count = 4` with default cap escalates to `review` + `Failed`, (b) `retry_count = 2` reschedules with backoff, (c) operator raising `max_retry_attempts` mid-flight changes the decision, (d) git-credential path is unchanged
- [x] 4.2 Add a test asserting `min(2 ** retry_count, 60)` behaviour for `retry_count ∈ {3, 6, 13}` (8 min, 60 min, 60 min)
- [x] 4.3 Add a test asserting `_get_max_retry_attempts` honours env → DB → default precedence and clamps `0` to `1`
- [x] 4.4 Add a test asserting `_escalate_to_review_failed` removes any pre-existing `Retry` tag and adds a `Failed` tag (mutually exclusive)
- [x] 4.5 Add a test asserting `publish_event("task_updated", ...)` is invoked on escalation
- [x] 4.6 Add `task-runner/tests/test_execute_command_401.py` — unit tests for `_is_google_token_expired` covering: existing UNAUTHENTICATED substring, new raw 401 conjunction, partial-match-only-`code:401` returns False, and one-retry cap honoured on a re-401
- [x] 4.7 Run full test suite: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ task-runner/tests/ -v` and confirm no regressions

## 5. Local verification

- [x] 5.1 Build and start the stack: `docker compose -f testing/docker-compose.yml up --build`
- [x] 5.2 Manually create a task whose container will fail (e.g. invalid profile / forced non-zero exit), set `max_retry_attempts = 2`, watch it escalate to `review` with the `Failed` tag after 2 retries
- [x] 5.3 Verify the kanban UI shows the `Failed`-tagged task in `review` distinctly from `needs_input` (visual sanity check)
- [x] 5.4 Stop the stack: `docker compose -f testing/docker-compose.yml down`

## 6. PR and deploy

- [x] 6.1 Push branch, open PR with title `feat: cap runner retry storms and widen gws 401 detection`
- [ ] 6.2 Confirm CI builds image + Helm chart successfully (immutable tag check, no duplicates)
- [ ] 6.3 Verify ArgoCD dry-run / staging apply succeeds against the new chart
- [ ] 6.4 Merge PR, delete local branch, pull `main`

## 7. Post-deploy verification

- [ ] 7.1 Inspect Loki: confirm the new `"Task <id> exceeded max retries"` log line appears for any chronically failing task post-deploy
- [ ] 7.2 Confirm the 12 currently-stuck tasks are migrated to `review` + `Failed` on their next retry (or have been manually cleared by operator, as agreed)
- [ ] 7.3 Trigger a `gws drive files list` against an intentionally-expired token in dev and confirm `token_refreshed` event is emitted and the command succeeds after one refresh

## 8. Archive

- [ ] 8.1 Run `/opsx:verify` to confirm implementation matches spec
- [ ] 8.2 Run `/opsx:archive` to finalize the change after merge
