## ADDED Requirements

### Requirement: Retry attempt cap with escalation to review

The TaskManager SHALL cap the number of times a task can be rescheduled by `_schedule_retry` for non-git failure classes. The cap value SHALL be read from a `max_retry_attempts` setting (env → DB → default), with a default of `5`. When `_schedule_retry` is invoked and the task's current `retry_count` is `>= max_retry_attempts - 1` (i.e., this would be at least the Nth retry), the TaskManager SHALL NOT reschedule the task. Instead it SHALL move the task to `review` status, set `output` to a human-readable message identifying the cap was reached and quoting the most recent failure output, increment `retry_count` one final time, set `updated_by` to `"system"` and `updated_at` to the current UTC time, and add a `Failed` tag (creating the tag row on demand if it does not exist).

The `Failed` tag SHALL be distinct from the `Retry` tag — when a task is escalated to `review`, the TaskManager SHALL remove any existing `Retry` tag on the task and add the `Failed` tag, so the two states are mutually exclusive.

The TaskManager SHALL emit a `task_updated` event after escalation, publishing the task's new state via the existing `publish_event` channel, so SSE consumers see the transition immediately.

The TaskManager SHALL log at INFO level on escalation: `"Task <id> exceeded max retries (<count>), moved to review"`.

This cap SHALL apply to every failure path that funnels into `_schedule_retry`, including: structured output parse failures, container non-zero exit codes, generic unhandled exceptions, and CancelledError during shutdown. The cap SHALL NOT change the behaviour of the existing `MAX_GIT_RETRIES` path, which has its own escalation logic in the git-credential failure branch.

#### Scenario: Task escalated after reaching the retry cap

- **WHEN** a task has `retry_count = 4`, `max_retry_attempts = 5`, and its container exits with a non-zero code and no structured output
- **THEN** the TaskManager moves the task to `review`, adds the `Failed` tag, removes the `Retry` tag if present, increments `retry_count` to `5`, writes a "max retries reached" message to `output`, emits a `task_updated` event, and logs the escalation

#### Scenario: Task below the cap is rescheduled normally

- **WHEN** a task has `retry_count = 2`, `max_retry_attempts = 5`, and its container exits non-zero
- **THEN** the TaskManager schedules the next retry via the existing backoff logic, tags the task `Retry`, and does NOT add a `Failed` tag

#### Scenario: Operator raises the cap at runtime

- **WHEN** an operator updates `max_retry_attempts` from `5` to `10` while a task is mid-flight at `retry_count = 4`
- **THEN** on the task's next failure the TaskManager reads the new setting value, computes `4 < 10 - 1`, and reschedules normally rather than escalating

#### Scenario: Git-credential failures continue to use their own cap

- **WHEN** a task fails with a `GitSkillsError` carrying a credential-error hint and `retry_count >= MAX_GIT_RETRIES`
- **THEN** the existing `Credentials` tag is added, the task moves to `review`, and the new `Failed` tag is NOT added (git path is unchanged)

### Requirement: Exponential backoff capped at 60 minutes

`_schedule_retry` SHALL compute backoff as `min(2 ** retry_count, 60)` minutes. The cap value (60) SHALL be a module-level constant `MAX_RETRY_BACKOFF_MINUTES` to ease tuning. The cap SHALL be applied before `execute_at` is computed, so a task at `retry_count = 6` and a task at `retry_count = 13` both wait the same 60 minutes between attempts.

The cap SHALL NOT change behaviour for tasks at `retry_count <= 5` (where `2 ** retry_count` is already `<= 32`).

#### Scenario: Backoff growth capped at the ceiling

- **WHEN** `_schedule_retry` is invoked on a task with `retry_count = 7`
- **THEN** `execute_at` is set to `now() + 60 minutes`, not `now() + 128 minutes`

#### Scenario: Low retry counts unaffected

- **WHEN** `_schedule_retry` is invoked on a task with `retry_count = 3`
- **THEN** `execute_at` is set to `now() + 8 minutes` (`2 ** 3`), the cap is not engaged

### Requirement: max_retry_attempts setting honours resolution order

The `max_retry_attempts` value SHALL be resolved at each retry decision via the existing `_get_setting` helper using the same `env → DB → default` order as `max_concurrent_tasks`. The default SHALL be `5`. Negative or zero values SHALL be treated as `1` (any failure escalates immediately) to avoid runaway loops if mis-configured. Non-integer DB values SHALL fall back to the default.

#### Scenario: Setting absent uses default

- **WHEN** neither `MAX_RETRY_ATTEMPTS` env var nor `max_retry_attempts` DB row is set
- **THEN** `_schedule_retry` uses `5` as the cap

#### Scenario: Env var overrides DB row

- **WHEN** `MAX_RETRY_ATTEMPTS=8` is set in the environment and a DB row holds `max_retry_attempts = 3`
- **THEN** `_schedule_retry` uses `8`

#### Scenario: Invalid value falls back to default

- **WHEN** `max_retry_attempts` is set to `"foo"` in the DB
- **THEN** `_schedule_retry` uses `5` (the default) and logs a warning

#### Scenario: Zero treated as one

- **WHEN** `max_retry_attempts` is set to `0`
- **THEN** any task that enters `_schedule_retry` is escalated to `review` immediately (no retries permitted)
