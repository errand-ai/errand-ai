## Context

A Loki sweep over 2026-05-25 → 2026-05-27 found 12 tasks stuck in retry cycles with retry counts of 4–13. The failures clustered into four root-cause classes (LLM 503s, model-side `EmptyResponseError`, `gws` CLI misuse, and a Google 401 that the task-runner's refresh wrapper failed to recognise). Every one of these failure classes recurs on each retry — the cause is persistent — yet the TaskManager will keep rescheduling forever because:

- Only the git-skill path enforces an attempt cap (`MAX_GIT_RETRIES`). Every other failure class falls through to `_schedule_retry` unconditionally.
- `_schedule_retry` computes `backoff_minutes = 2 ** retry_count` with no upper bound, so at retry 13 a task sleeps ~136 minutes between attempts. Tasks remain visible (status `scheduled` with a `Retry` tag) but neither escalate to humans nor stop consuming worker slots periodically.
- The transparent Google token refresh in `task-runner/main.py` only matches the substring `"status": "UNAUTHENTICATED"`. The `gws` CLI surfaces Google's raw 401 JSON (`{"error": {"code": 401, "message": "Request had invalid authentication credentials..."}}`) which does not contain that substring, so token refresh never fires and the task fails the same way on every retry.

## Goals / Non-Goals

**Goals:**
- Bound the retry storm: every task SHALL reach a terminal state (`completed`, `review`, or `Failed`-tagged `review`) within a finite number of attempts.
- Surface persistent failures to operators by tagging escalated tasks `Failed` and routing them to `review` (same column the UI uses today for `needs_input` tasks).
- Recover `gws` CLI tasks that fail because of token expiry by extending the existing refresh trigger to Google's raw 401 shape.
- Keep the change blast-radius small: server-side TaskManager + a one-line regex widening on the runner side. No DB schema changes.

**Non-Goals:**
- Fixing the LM Studio 503 surface or the qwen3.6 `EmptyResponseError` model artefact — both are upstream / model-side concerns tracked separately.
- Rewriting the gws CLI usage guidance — the shareable `gws-cli-usage` skill in `~/github/ai-skills/skills/` is being authored separately.
- Migrating the 12 currently-stuck tasks. Operator action stays the path for clearing the backlog; the cap applies only to new retry decisions after deploy.
- Reclassifying transient vs non-retryable failure types — those classifications stay where they live today.

## Decisions

### Cap is enforced in `_schedule_retry`, not at dequeue time

`_schedule_retry` is the single funnel for all non-git failure paths in `errand/task_manager.py` (LLM parse failure, container non-zero exit, generic exception, cancellation-on-shutdown). Putting the cap at the funnel means one code path enforces the new behaviour for every failure class without needing to change every call site. The function reads the current `retry_count` from the row before incrementing, so it can branch on `current.retry_count >= max_retry_attempts - 1` and divert to a `_move_to_review` path with a `Failed` tag instead of rescheduling.

Alternative considered: branching at `_run_task`'s individual `except` blocks. Rejected because there are 4+ paths today and adding new failure classes in future would require touching every one.

### Setting is `max_retry_attempts`, default 5, resolved at retry time

Followed the existing `max_concurrent_tasks` pattern: settings table row, env → DB → default resolution order via `_get_setting`. Read on each retry decision (not cached) so an operator can raise the limit without restarting the server when a sustained outage causes false escalations.

The value `5` is calibrated against what we saw in Loki: every chronic task has a stable failure signature by retry 3–4. By retry 5 the loop has had enough attempts to ride out transient backend hiccups but not so many that a stuck task occupies a slot for hours.

Alternative considered: per-profile override (`task_profiles.max_retry_attempts`). Rejected for v1 — keep one knob until we see a real need; the per-profile pattern already exists for `llm_timeout` if we want it later.

### Exponential backoff capped at 60 min

`min(2 ** retry_count, 60)`. At the cap (retry 5) the longest sleep would be 60 minutes; with the existing growth this would already be 32 minutes at retry 5, so the cap is dormant when `max_retry_attempts=5` but protects future operators who raise the limit. Capping also means the cap behaviour and retry-count cap behaviour are independently tunable.

### `Failed` tag is bootstrapped lazily, same pattern as `Retry`

`_schedule_retry` already creates the `Retry` tag on demand with `select` → `if None: add`. The new `_move_to_review_failed` helper SHALL use the same pattern for `Failed`. No migration needed.

### 401 detection widens via substring set, not JSON parsing

Today `task-runner/main.py` checks `if "\"status\": \"UNAUTHENTICATED\"" in output`. The new code SHALL check for either that substring OR the conjunction `"code": 401` AND `"Request had invalid authentication credentials"`. Substring matching is fragile but matches the existing implementation style — switching to JSON parsing would expand the change footprint and risks regressing the existing path.

Alternative considered: parse `output` as JSON and inspect the error shape. Rejected because `output` is a mix of stdout/stderr that is not always valid JSON, and the runner already commits to substring matching for the working case.

### `review` not a new column / status

The UI already surfaces `review` and operators are accustomed to triaging it (`needs_input` lands there, as do exhausted git retries). Keeping escalated tasks in `review` avoids any frontend change. The new `Failed` tag is the discriminator between `needs_input` and "retry storm" tasks visually.

## Risks / Trade-offs

- [Risk] A genuine transient outage (e.g. LM Studio down for 90 minutes) could escalate tasks that would have succeeded on retry 6. → Mitigation: setting is operator-tunable at runtime; backoff cap of 60 min means we lose at most ~5 hours of attempts at `max_retry_attempts=5`; document escalation in CHANGELOG so operators can raise the cap during outages.
- [Risk] Repeating tasks that hit the cap will stop firing future runs (because they sit in `review`, not `scheduled` or `completed`). → Mitigation: the `Failed` tag makes them findable in the UI; document the operator path ("unassign Failed tag and re-pend" or recreate from schedule). Acceptable because the alternative — silent infinite retry — is what we're fixing.
- [Risk] Widening the 401 detection could match false positives in other CLI output. → Mitigation: the conjunction (`"code": 401` AND `"Request had invalid authentication credentials"`) is Google-specific phrasing; we'd need a tool whose output also contains both substrings to misfire, which is improbable.
- [Trade-off] Holding the retry count cap separate from the backoff cap means two knobs to reason about. Accepted because conflating them would couple "how long until escalation" to "how long between attempts" — operators need both levers independently.

## Migration Plan

1. Ship the code with `max_retry_attempts` defaulting to 5 and the backoff ceiling of 60 min. No DB migration needed.
2. On first deploy, tasks already at `retry_count >= 5` will be escalated to `review` + `Failed` on their next failure (not pre-emptively — only when they next attempt and fail). The 12 currently stuck tasks left untouched by the change can be cleared by operator action.
3. Rollback: reverting the deploy restores the previous unbounded behaviour. `Failed`-tagged tasks remain in `review` until manually re-pended — no state corruption.

## Open Questions

- Should we also emit a structured task event (`task_escalated_to_review`) for SSE consumers, so the kanban UI can show a visual cue distinct from `needs_input`? Leaning yes but defer to the implementation phase if it's straightforward.
- Once this cap exists, do we want repeating tasks to be allowed to schedule their next occurrence even when the last one was `Failed`? Current behaviour reschedules on `completed` only; this change inherits that. Probably correct for v1 — a stuck repeating task should pause rather than spam.
