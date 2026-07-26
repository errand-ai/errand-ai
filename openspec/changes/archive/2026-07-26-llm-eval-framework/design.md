# Design — LLM Eval Framework

## Context

Errand runs ~10 recurring workloads through task profiles whose models (local MLX via LM Studio, free/paid cloud — all behind one LiteLLM gateway) were assigned by guesswork. History mining (July 2026, ~1,324 tasks) established:

- 98% of tasks retain `runner_logs` containing a parseable JSONL event stream (`llm_turn_start` with model name, `tool_call` with args, `tool_result`, `thinking`, `error`, `agent_end`, recovery events).
- Retries measure **infrastructure** failures (skill pip-install breakage, MCP connect failures, zombie recovery), not model quality. Model-quality failures hide inside `completed` tasks.
- The runner's rescue machinery is load-bearing for local models: 68 `tool_call_recovered_from_reasoning` events across job-research/tweet-pipeline (qwen3.6 local) vs 0 in 300 email-triage runs (cloud). Model performance is inseparable from the runner — evals must run through the real task pipeline.
- Workload cost varies ~15× (email-triage median 2 turns; job-research median 30, p90 66).

Constraints: Errand runs on Kubernetes; the driver runs wherever LM Studio and the `claude` CLI live (Rob's Mac). LM Studio serves one model at a time. Free-tier cloud models are rate-limited and their backends drift. The MCP API key is readable by running tasks via `/workspace/mcp.json`.

## Goals / Non-Goals

**Goals:**

- Standing, re-runnable suite producing per-workload model league tables (best local; best overall), stored longitudinally in the errand DB.
- Driver is a **pure MCP client** — no direct DB or Kubernetes access required.
- Judge runs on the `claude` CLI under the existing Max subscription, independent of the LiteLLM gateway under test; raw evidence retained so old runs can be re-judged.
- Retro-judging mode to baseline historical output quality and calibrate rubrics before any live bake-off.
- Scoring distinguishes infra failures from model failures.

**Non-Goals:**

- Dry-run/capture mode for side-effectful tools (email-triage, tweet-pipeline live evals) — future change; initial corpus is read-only workloads.
- Grafana dashboard (results are chartable via Postgres datasource; dashboard authored later).
- Token/cost metrics (runner events carry no usage; adding it is a future runner change).
- Multi-user authorization for the new MCP tools (single-user deployment; see Risks).
- CI integration or automated scheduling of eval runs.

## Decisions

### D1. Eval runs go through the production task pipeline

Eval tasks are ordinary Errand tasks submitted via `new_task` under cloned profiles. Alternatives considered: an external harness (promptfoo/Inspect AI) re-implementing the agent loop — rejected because it would bypass the runner's compaction, tool-call recovery, and prompt/skill assembly, measuring a system that doesn't exist in production.

### D2. Eval task identity: `is_eval` column, set server-side at creation

Tasks created under a profile whose name starts with `eval--` get `is_eval = true` (new boolean column on `tasks`, default false, set in the task-creation path — not by the client). `GET /api/tasks` and `GET /api/tasks/archived` exclude `is_eval` rows unless `include_evals=true` is passed, so the board needs no frontend change.

Alternatives: tag-based marking (requires join + client cooperation); deriving from profile name at query time (breaks when eval profiles are deleted — `tasks.profile_id` is `ondelete=SET NULL`). A persisted column set at creation survives profile deletion and can't be forgotten by the driver.

### D3. Eval profiles are prefixed clones, mutable only via name-restricted tools

`clone_task_profile(source_profile, new_name, overrides)` copies all profile fields and applies overrides limited to `{model, llm_timeout, max_turns}`; `new_name` MUST start with `eval--` (convention: `eval--<workload>--<model-slug>`). `delete_task_profile(name)` refuses names not starting with `eval--`. This keeps the mutation surface reachable with the shared API key harmless to production profiles.

### D4. New MCP tools; excluded from the task-side catalog

New tools on `errand/mcp_server.py`: `clone_task_profile`, `delete_task_profile`, `search_tasks`, `start_eval_run`, `record_eval_result`, `finish_eval_run`, `get_eval_run` (read-back of a run's recorded results, used for driver resumability). None are in `DEFAULT_HOT_TOOLS`; additionally the task-runner's `tool_registry.py` gains an `EXCLUDED_CATALOG_TOOLS` set so these never appear in the catalog and `discover_tools` refuses to enable them — the task LLM cannot invoke them. Residual risk: code inside a task container can still hit the MCP endpoint directly with the shared key (accepted for single-user; upgrade path is a separate admin key checked by these tools).

`search_tasks(profile?, status?, created_after?, created_before?, title_contains?, is_eval?, limit=50, offset=0)` returns task metadata (id, title, status, profile name, created_at, retry_count, has_logs) — transcripts are fetched per-task via the existing `task_logs` tool. This unlocks retro-judging without DB access and is generally useful.

### D5. Results schema: two tables, DB is the driver's state store

```
eval_runs:    id, mode ('live'|'retro'), started_at, finished_at,
              corpus_version, errand_version (stamped server-side from VERSION),
              judge_model, driver_host, notes
eval_results: id, run_id FK, workload, model, task_id (nullable FK -> tasks, SET NULL),
              rep, verdict ('pass'|'fail'|'infra_failure'), score numeric nullable,
              turns, recoveries, error_events, wall_seconds,
              judge_output JSONB, created_at
```

Resumability falls out for free: the driver re-invoked with an existing `run_id` queries recorded results and skips completed (workload, model, rep) cells. No driver-side state file. Eval tasks are retained (never bulk-deleted) as raw evidence; `task_id` links result to transcript.

### D6. Judge = `claude` CLI headless; assertions run first

Scoring per rep: (1) programmatic assertions from the corpus spec (output regex/contains, expected tool calls present in transcript events); (2) `claude -p` invoked with a rubric prompt containing the task description, rubric, final output, and a filtered transcript digest (tool names + truncated results — not the raw log, which contains pip noise and can exceed judge context), requesting a strict JSON verdict `{pass, score (0-10), reasons}`. Judge model is pinned in `evals/config.yaml` and recorded per run. Full judge output stored in `judge_output` for auditability and re-scoring.

Infra-vs-model classification runs before judging: a rep is `infra_failure` (excluded from model aggregates, reported as suite health) when the transcript shows skill-install failure, MCP connection failure, zombie recovery, or terminates with no `agent_start`. The driver re-submits an infra-failed rep once before recording it.

### D7. Driver: drip-feed, sequential per model, yields to production

The driver (Python CLI in `evals/`, own `requirements.txt` + venv, MCP client + PyYAML only; judge via subprocess) iterates models in sequence (LM Studio hosts one model at a time), and within a model iterates corpus tasks × reps, submitting **one task at a time**: submit → poll `task_status` → fetch `task_output` + `task_logs` → score → `record_eval_result` → next. Before each submission it checks `list_tasks` for pending/running production work and waits (configurable `--no-yield` to disable). Per-workload rep counts and timeouts live in the corpus specs (cheap workloads get more reps).

Wall-time is measured driver-side (running→terminal transition granularity of the poll interval) because runner events carry no timestamps — accepted imprecision.

### D8. Corpus format: one YAML per task, versioned in-repo

`evals/corpus/<workload>/<nnn>-<slug>.yaml`: `id`, `base_profile` (source profile to clone), `description` (verbatim task text), `rubric` (markdown), `assertions` (typed list), `reps`, `timeout_minutes`. Corpus version recorded per run = short git SHA of the repo at run time. Initial corpus: read-only workloads mined from history — job-research, Twitter tech-trends research, nginx log analysis, weekly research summary, language translation — descriptions lifted from recurring historical tasks.

### D9. Retro-judging is a driver mode, not a separate tool

`evals retro --workload <w> --sample N`: `search_tasks` for historical completed/archived tasks of that workload → `task_logs` per task → extract model from `llm_turn_start` events → judge output against the workload rubric → record under an `eval_runs` row with `mode='retro'` (model attribution from transcript, `rep=0`, no cloned profiles, no task submission). Serves as rubric calibration and quality baseline.

## Risks / Trade-offs

- [Free-tier cloud models drift (backend/quantization changes)] → Record everything per-run; treat free-cloud scores as weaker evidence than local scores in reporting; re-runs are cheap to schedule.
- [Judge nondeterminism] → Full `judge_output` stored; rubrics ask for per-criterion booleans before an overall verdict; option to re-judge stored evidence later (raw transcripts retained). Majority-of-3 judging is a config option deferred until needed.
- [LM Studio model swap thrash when production tasks (qwen3.6) interleave with local eval batches] → Driver yields to pending production work by default; local batches best run in quiet windows. Accepted residual: a production task arriving mid-eval-task still forces a swap.
- [Shared MCP API key reachable from task containers] → Catalog + discover_tools exclusion stops the LLM path; name-restricted profile mutation bounds blast radius; separate admin key documented as upgrade path.
- [Eval load competes with production via the TaskManager semaphore] → Drip-feed (one in-flight eval task) caps eval share at 1 of `max_concurrent_tasks` slots.
- [Judge context overflow on long transcripts (job-research p90 = 66 turns)] → Scorer builds a bounded digest (event summaries, truncated tool results) rather than passing raw logs.
- [`search_tasks` exposes full history to any API-key holder] → Same trust domain as existing `task_logs`/`task_output`; no new data class exposed.

## Migration Plan

1. Alembic migration (additive): `tasks.is_eval` boolean NOT NULL DEFAULT false; `eval_runs`, `eval_results` tables.
2. Deploy server with new MCP tools + `is_eval` filtering (no behavior change for existing clients; `include_evals` defaults preserve current responses).
3. Task-runner image with `EXCLUDED_CATALOG_TOOLS` (independent of server deploy; tools are absent from catalog either way until server ships).
4. Land `evals/` driver + corpus; run retro-judging first, then a small live pilot (one model, one workload) before full matrix runs.

Rollback: revert deployments; migration is additive (columns/tables can remain or be dropped in a follow-up downgrade) — no data-model coupling with existing features.

## Open Questions

- Judge prompt/rubric calibration quality — deliberately front-loaded via retro-judging phase; rubrics are corpus content and iterate without schema changes.
- Whether `search_tasks` should paginate via cursor instead of offset if history grows large (start with offset; revisit at >10k tasks).
