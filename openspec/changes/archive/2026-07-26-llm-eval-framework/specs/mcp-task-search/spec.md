## ADDED Requirements

### Requirement: search_tasks MCP tool
The MCP server SHALL provide `search_tasks(profile?, status?, created_after?, created_before?, title_contains?, is_eval?, limit?, offset?)` returning a JSON array of task metadata: `id`, `title`, `status`, `profile_name`, `created_at`, `retry_count`, `has_logs` (boolean). Unlike `list_tasks`, it SHALL search the full task history including `archived` and `deleted` tasks. All filters SHALL combine with AND semantics. `limit` SHALL default to 50 and be capped at 200; results SHALL be ordered by `created_at` descending.

#### Scenario: Search by profile and status
- **WHEN** `search_tasks(profile="job-research", status="archived", limit=10)` is called
- **THEN** the 10 most recent archived job-research tasks are returned with all metadata fields

#### Scenario: Full history is searchable
- **WHEN** `search_tasks(status="archived")` is called
- **THEN** archived tasks not visible on the board are included in the results

#### Scenario: Date range filter
- **WHEN** `search_tasks(created_after="2026-03-01T00:00:00Z", created_before="2026-04-01T00:00:00Z")` is called
- **THEN** only tasks created in March 2026 are returned

#### Scenario: Limit capped
- **WHEN** `search_tasks(limit=1000)` is called
- **THEN** at most 200 results are returned

### Requirement: Eval tasks excluded from search by default
`search_tasks` SHALL exclude tasks with `is_eval=true` unless the `is_eval` parameter is explicitly provided (`is_eval=true` returns only eval tasks; `is_eval=false` returns only non-eval tasks).

#### Scenario: Default excludes eval tasks
- **WHEN** `search_tasks(profile="job-research")` is called without `is_eval`
- **THEN** no eval tasks appear in the results

#### Scenario: Explicitly searching eval tasks
- **WHEN** `search_tasks(is_eval=true)` is called
- **THEN** only eval tasks are returned
