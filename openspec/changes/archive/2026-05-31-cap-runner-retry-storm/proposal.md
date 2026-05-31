## Why

Tasks that fail for a reason other than git-credential errors retry indefinitely with exponential backoff capped only by the implicit ceiling of `2^retry_count` minutes. A Loki sweep over the last three days found 12 tasks stuck in retry cycles (retry counts 4–13), all repeating the same root cause every attempt — there is currently no escalation path that surfaces these to a human or stops the loop. The git-skill path already routes credential failures to `review` after `MAX_GIT_RETRIES`; the same protection is missing for every other failure class.

A second, smaller cause of stuck tasks: the task-runner's `execute_command` wrapper only triggers transparent Google token refresh on the substring `"status": "UNAUTHENTICATED"`. The `gws` CLI surfaces Google's raw 401 payload (`"code": 401, "message": "Request had invalid authentication credentials..."`), which doesn't match — so the refresh path is silently skipped and the task retries forever with the same expired token.

## What Changes

- TaskManager SHALL cap retry escalation for non-git failure classes (LLM crashes, runner non-zero exit, structured-output parse failures, runner cancellations on shutdown). After a configurable threshold (default 5 retries), the task SHALL move to `review` with a `Failed` tag and an output line explaining why it stopped retrying.
- The retry cap SHALL be exposed as a setting (`max_retry_attempts`, default `5`) alongside the existing `MAX_GIT_RETRIES`, with semantics: "retries permitted before forced escalation to `review`."
- The exponential backoff used in `_schedule_retry` SHALL cap at 60 minutes (currently grows to ~136 minutes at retry 13 with no ceiling).
- The task-runner's `execute_command` wrapper SHALL detect Google's raw 401 payload (`"code": 401` together with `"Request had invalid authentication credentials"` or `"error": {"code": 401`) in addition to the existing `"status": "UNAUTHENTICATED"` substring, so transparent token refresh fires for `gws` CLI errors.
- Tasks currently stuck in retry cycles SHALL NOT be migrated automatically — operator action remains the path for clearing the backlog.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `task-manager`: add a retry-attempt cap and exponential-backoff ceiling; define the `Failed` tag and the path to `review` for non-git failures.
- `task-runner-error-resilience`: widen the `execute_command` 401 detection so Google's raw error shape triggers transparent token refresh.

## Impact

- **Code**: `errand/task_manager.py` (`_schedule_retry`, `_run_task`), `errand/models.py` (Tag bootstrap for `Failed`), `task-runner/main.py` (`execute_command` wrapper regex).
- **Settings**: new `max_retry_attempts` row added by migration (no schema change).
- **DB**: no schema changes; existing `retry_count` column suffices.
- **Backwards compatibility**: existing tasks with `retry_count >= 5` at deploy time will be promoted to `review` on their next failed retry rather than continuing to cycle.
- **Telemetry**: a new log line `"Task X exceeded max retries (N), moved to review"` lets operators correlate this in Loki.
- **Out of scope**: handling LM Studio 503s, fixing `EmptyResponseError` from qwen3.6, and the broader gws-CLI usage skill — those are separate concerns tracked outside this change.
