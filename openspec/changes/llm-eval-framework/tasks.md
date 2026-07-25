# Tasks — LLM Eval Framework

## 1. Database & task marking

- [x] 1.1 Bump `VERSION` (minor) and create Alembic migration: `tasks.is_eval` (boolean NOT NULL DEFAULT false), `eval_runs`, `eval_results` tables with unique `(run_id, workload, model, rep)` and FKs per spec; verify reversibility
- [x] 1.2 Add `EvalRun` / `EvalResult` models to `errand/models.py` and `is_eval` to `Task`
- [x] 1.3 Set `is_eval=true` in all task-creation paths when the resolved profile name starts with `eval--`; include `is_eval` in `TaskResponse`
- [x] 1.4 Exclude `is_eval` tasks from `GET /api/tasks` and `GET /api/tasks/archived` unless `include_evals=true`; backend tests for flagging + filtering

## 2. MCP tools (server)

- [x] 2.1 `clone_task_profile` — copy all fields, apply `{model, llm_timeout, max_turns}` overrides, enforce `eval--` prefix, idempotent reuse; tests
- [x] 2.2 `delete_task_profile` — enforce `eval--` prefix, idempotent on missing; tests
- [x] 2.3 `search_tasks` — full-history search with AND filters, `is_eval` default exclusion, limit cap 200, ordered `created_at` desc; tests
- [x] 2.4 `start_eval_run` / `record_eval_result` / `finish_eval_run` / `get_eval_run` — validation (mode, verdict, finished-run rejection), server-side `errand_version` stamping; tests

## 3. Task-runner catalog exclusion

- [x] 3.1 Add `EXCLUDED_CATALOG_TOOLS` to `task-runner/tool_registry.py`; omit from catalog, refuse in `discover_tools`, skip in auto-enable recovery; task-runner tests

## 4. Eval driver skeleton (`evals/`)

- [ ] 4.1 Scaffold `evals/`: `README.md`, `requirements.txt` (MCP client, PyYAML), `config.yaml` template, CLI entrypoint with `run` and `retro` subcommands
- [ ] 4.2 MCP client wrapper for the errand endpoint (auth, retry, the tool calls the driver needs)
- [ ] 4.3 Corpus loader with validation (required fields, assertion types) and corpus-version detection (git SHA + dirty-tree warning)
- [ ] 4.4 Transcript parser: extract JSONL events from `runner_logs`, compute metrics (turns, recoveries, error events), classify infra vs judgeable per spec

## 5. Scoring

- [ ] 5.1 Assertion evaluator (`output_contains`, `output_regex`, `tool_called`)
- [ ] 5.2 Transcript digest builder (bounded, event-only, truncated tool results)
- [ ] 5.3 Judge invocation via `claude` CLI headless: prompt assembly, strict-JSON verdict parse with one retry, null-score fallback preserving raw response
- [ ] 5.4 Verdict combination (failed assertion ⇒ `fail`) and `record_eval_result` submission; unit tests with fixture transcripts from real history

## 6. Live run loop

- [ ] 6.1 Matrix executor: sequential per model, one in-flight task, per-cell profile clone/reuse, end-of-run profile cleanup
- [ ] 6.2 Submit/poll/collect cycle with corpus timeouts and infra-failure single retry
- [ ] 6.3 Yield-to-production gate (`list_tasks` check, poll interval, `--no-yield`)
- [ ] 6.4 Resumability: `get_eval_run` cell skip on re-invocation with existing run id

## 7. Retro mode & corpus

- [ ] 7.1 Retro subcommand: `search_tasks` sampling, model attribution from `llm_turn_start`, skip-and-report unparseable transcripts, `mode='retro'` recording
- [ ] 7.2 Author initial read-only corpus from history (job-research, tech-trends research, nginx log analysis, research summary, translation) with rubrics and assertions
- [ ] 7.3 Run retro-judging over history samples per workload; calibrate rubrics from disagreements; record baseline run

## 8. Verification & rollout

- [ ] 8.1 Local docker-compose end-to-end: migration, eval task flagging, board exclusion, MCP tools, catalog exclusion
- [ ] 8.2 Live pilot on deployment: one model × one workload × 2 reps end-to-end (clone → run → score → record → cleanup); verify results rows and Grafana Postgres queryability
- [ ] 8.3 Update `CLAUDE.md` (evals dir, new MCP tools, is_eval semantics); PR + K8s deployment validation per workflow
