# LLM Eval Framework

## Why

Errand's task profiles assign models (local MLX via LM Studio, free cloud, paid cloud — all through one LiteLLM gateway) by guesswork. As new models become available, there is no evidence-based way to decide which model best serves each workload — especially for the primary goal of running Errand entirely on local models where viable. Task history (~1,300 tasks, 98% with fully parseable JSONL transcripts) already contains the raw material for a standing evaluation suite, and mining it revealed that model-quality failures are silent (they hide inside "completed" tasks — retries measure infrastructure failures, not model quality), so a judging layer is required to see quality at all.

## What Changes

- New top-level `evals/` directory containing a standalone eval driver (CLI process) that interacts with Errand **exclusively through the MCP endpoint**, so it can run from any machine with network access to Errand (it will typically run on the machine hosting LM Studio, which also has the `claude` CLI).
- A versioned eval corpus: frozen task specs per workload (description, rubric, programmatic assertions), lifted from the recurring workloads found in task history. Initial corpus is **read-only workloads only** (research, log analysis, translation, summarization); side-effectful workloads (email-triage, tweet-pipeline) are deferred to a future dry-run-tools change.
- Scoring via LLM-as-judge using the `claude` CLI headless under the existing Max subscription — deliberately independent of the LiteLLM gateway under test, with zero marginal cost. Scorer classifies failures as **infra vs model** (from transcript events) and excludes infra failures from model scores.
- A **retro-judging mode** as phase zero: judge samples of historical task outputs per workload to calibrate rubrics and establish the current quality baseline before any live bake-off.
- New MCP tools so the driver is a pure MCP client: eval profile clone/delete, eval run/result recording, and task history search. Eval/admin tools are catalog-only and excluded from task-side `discover_tools`.
- Two new database tables (`eval_runs`, `eval_results`) storing scores, metrics (turns, tool-call recoveries, error events, wall time), full judge output (JSONB), and pinned run context (corpus version, errand version, runner image, judge model) for longitudinal comparability. Grafana charts results via a Postgres datasource (dashboard itself is out of scope).
- Eval tasks are marked (`is_eval` column, set server-side for `eval--*` profiles) and retained (not deleted) as raw evidence; the task list APIs exclude them by default so the board never shows them.
- Driver supports drip-feed submission (one task at a time, interleaving with production tasks) and sequential per-model batching to respect single-model LM Studio hosting.

## Capabilities

### New Capabilities

- `eval-corpus`: Corpus format and content — per-workload frozen task specs with rubrics and assertions, versioned in-repo.
- `eval-driver`: The driver CLI — model×workload matrix runs, drip-feed submission, per-model sequential batching, rep budgets, retro-judging mode, resumability.
- `eval-judge`: Scoring — claude CLI judge invocation, rubric verdict schema, programmatic assertions, infra-vs-model failure classification, metrics extraction from transcripts.
- `eval-results-recording`: MCP tools `start_eval_run` / `record_eval_result` and the `eval_runs` / `eval_results` tables with pinned run context.
- `mcp-task-search`: MCP tool to search full task history with filters (profile, status, date range, limit) — needed by retro-judging, generally useful.

### Modified Capabilities

- `mcp-profile-tools`: Add `clone_task_profile` and `delete_task_profile` tools, restricted to `eval--*`-prefixed profile names, catalog-only.
- `task-api`: `tasks.is_eval` column set server-side at creation for `eval--*` profiles; `GET /api/tasks` and `GET /api/tasks/archived` exclude eval tasks unless `include_evals=true`.
- `lazy-mcp-tool-registry`: New `EXCLUDED_CATALOG_TOOLS` set — eval/admin tools never appear in the catalog and `discover_tools` refuses to enable them.

## Impact

- **New code**: `evals/` (driver, scorer, corpus files, own README); no coupling to server internals — MCP client only.
- **Backend**: `errand/mcp_server.py` (new tools), `errand/models.py` + Alembic migration (two tables), tool catalog exclusion list.
- **Frontend**: no changes required (filtering is server-side).
- **Security**: new MCP tools are reachable with the shared `mcp_api_key` (readable by running tasks); mitigated by catalog exclusion and the `eval--*` name restriction on profile mutation. A separate admin key is the upgrade path if Errand goes multi-user.
- **Operations**: eval runs share the TaskManager semaphore with production tasks; local-model evals may cause LM Studio model swapping when interleaved with production tasks on a different local model — driver mitigates by yielding to pending production work.
- **Out of scope (future changes)**: dry-run capture mode for side-effectful tools (unlocks email-triage/tweet-pipeline corpora), Grafana dashboard, token-usage emission in runner events.
