## ADDED Requirements

### Requirement: eval_runs table
The database SHALL have an `eval_runs` table with columns: `id` (UUID PK), `mode` (text, `live` or `retro`), `started_at` / `finished_at` (timestamptz, `finished_at` nullable), `corpus_version` (text), `errand_version` (text), `judge_model` (text), `driver_host` (text, nullable), `notes` (text, nullable).

#### Scenario: Migration creates table
- **WHEN** the Alembic migration for this change runs
- **THEN** `eval_runs` exists with the columns above and the migration is reversible

### Requirement: eval_results table
The database SHALL have an `eval_results` table with columns: `id` (UUID PK), `run_id` (FK → `eval_runs.id`, CASCADE delete), `workload` (text), `model` (text), `task_id` (nullable FK → `tasks.id`, `ON DELETE SET NULL`), `rep` (integer), `verdict` (text: `pass`, `fail`, or `infra_failure`), `score` (numeric, nullable), `turns` / `recoveries` / `error_events` (integer, nullable), `wall_seconds` (numeric, nullable), `judge_output` (JSONB, nullable), `created_at` (timestamptz). A unique constraint SHALL cover `(run_id, workload, model, rep)`.

#### Scenario: Duplicate cell rejected
- **WHEN** a result for `(run, job-research/001, gemma4, rep 2)` already exists and a second insert for the same cell is attempted
- **THEN** the insert is rejected by the unique constraint

### Requirement: start_eval_run MCP tool
The MCP server SHALL provide `start_eval_run(mode, corpus_version, judge_model, driver_host?, notes?)` which creates an `eval_runs` row, stamps `errand_version` server-side from the deployed `VERSION`, and returns the run id. `mode` SHALL be validated as `live` or `retro`.

#### Scenario: Run started
- **WHEN** `start_eval_run(mode="live", corpus_version="abc1234", judge_model="claude-opus-4-8")` is called
- **THEN** a run row is created with `errand_version` equal to the server's VERSION and the tool returns the run id

#### Scenario: Invalid mode rejected
- **WHEN** `start_eval_run` is called with `mode="dryrun"`
- **THEN** the tool returns an error and no row is created

### Requirement: record_eval_result MCP tool
The MCP server SHALL provide `record_eval_result(run_id, workload, model, rep, verdict, task_id?, score?, turns?, recoveries?, error_events?, wall_seconds?, judge_output?)` which inserts an `eval_results` row. `verdict` SHALL be validated against the allowed values. Recording against an unknown or finished run SHALL return an error.

#### Scenario: Result recorded
- **WHEN** `record_eval_result` is called with a valid run id and verdict `pass`
- **THEN** a result row is inserted and the tool returns the result id

#### Scenario: Recording against finished run rejected
- **WHEN** `record_eval_result` is called for a run whose `finished_at` is set
- **THEN** the tool returns an error and no row is inserted

### Requirement: finish_eval_run MCP tool
The MCP server SHALL provide `finish_eval_run(run_id, notes?)` which sets `finished_at` (and appends notes when provided). Finishing an already-finished run SHALL be an error.

#### Scenario: Run finished
- **WHEN** `finish_eval_run(run_id)` is called on an open run
- **THEN** `finished_at` is set and subsequent `record_eval_result` calls for the run are rejected

### Requirement: get_eval_run MCP tool
The MCP server SHALL provide `get_eval_run(run_id)` returning the run's metadata and its recorded results as JSON (each result: workload, model, rep, verdict, score, task_id). This supports driver resumability.

#### Scenario: Resume queries recorded cells
- **WHEN** `get_eval_run(run_id)` is called for a run with 40 recorded results
- **THEN** the response lists all 40 (workload, model, rep) cells with verdicts

### Requirement: Eval MCP tools are excluded from the task-side catalog
`clone_task_profile`, `delete_task_profile`, `search_tasks`, `start_eval_run`, `record_eval_result`, `finish_eval_run`, and `get_eval_run` SHALL NOT be in `DEFAULT_HOT_TOOLS` and SHALL be listed in the task-runner's excluded-catalog set so they never surface to task LLMs.

#### Scenario: Tool absent from catalog
- **WHEN** a task-runner builds its tool catalog from the Errand MCP server
- **THEN** none of the eval/admin tools appear in the `<available_mcp_tools>` block
