## ADDED Requirements

### Requirement: Driver is a pure MCP client
The eval driver SHALL interact with Errand exclusively through the Errand MCP endpoint (task submission, polling, transcript retrieval, profile management, result recording, history search). The driver SHALL NOT require database, Kubernetes, or SSH access to the Errand deployment.

#### Scenario: Driver runs from a remote machine
- **WHEN** the driver runs on a machine with only network access to the Errand MCP endpoint and a valid API key
- **THEN** a full eval run completes without any non-MCP access to the deployment

### Requirement: Matrix execution is sequential per model with one in-flight task
For a live run, the driver SHALL iterate models strictly sequentially (completing all workloads × reps for one model before starting the next) and SHALL have at most one eval task in flight at any time: submit via `new_task`, poll `task_status`, retrieve `task_output` and `task_logs`, score, record, then submit the next.

#### Scenario: Sequential model batching
- **WHEN** a run covers models `[gemma4, qwen3.6]`
- **THEN** no task for `qwen3.6` is submitted until every (workload, rep) cell for `gemma4` has been recorded

#### Scenario: Single in-flight task
- **WHEN** an eval task is pending or running
- **THEN** the driver does not submit another task until the current one reaches a terminal state or exceeds its corpus `timeout_minutes`

### Requirement: Eval profile lifecycle
For each (workload, model) cell the driver SHALL create the profile `eval--<workload>--<model-slug>` via `clone_task_profile` from the corpus task's `base_profile` with the model override applied, and SHALL delete the profiles it created via `delete_task_profile` at the end of the run. Profile creation SHALL be idempotent from the driver's perspective (an already-existing eval profile with the expected configuration is reused).

#### Scenario: Profile created and cleaned up
- **WHEN** a run evaluates `gemma4` on `job-research`
- **THEN** `eval--job-research--gemma4` exists during the cell's tasks and is deleted when the run finishes

#### Scenario: Interrupted run leaves reusable profiles
- **WHEN** a driver process dies mid-run and is restarted with the same run id
- **THEN** existing `eval--*` profiles are reused rather than causing an error

### Requirement: Driver yields to production work
Before each submission the driver SHALL check for pending or running non-eval tasks (via `list_tasks`) and wait until none are present, polling at a configurable interval. A `--no-yield` flag SHALL disable this behavior.

#### Scenario: Production task takes priority
- **WHEN** a production task is pending at the time the driver would submit the next eval task
- **THEN** the driver waits and re-checks instead of submitting

#### Scenario: Yielding disabled
- **WHEN** the driver runs with `--no-yield`
- **THEN** eval tasks are submitted regardless of production activity

### Requirement: Resumability via run id
When invoked with an existing `run_id`, the driver SHALL fetch previously recorded results for that run via `get_eval_run` and SHALL skip every (workload, model, rep) cell that already has a recorded result, executing only the remainder.

#### Scenario: Resume after interruption
- **WHEN** a run recorded 40 of 90 cells before the driver was killed and the driver is re-invoked with the same run id
- **THEN** only the 50 unrecorded cells are executed

### Requirement: Infra failures are retried once
When a rep is classified as an infrastructure failure, the driver SHALL re-submit that rep exactly once. If the retry also infra-fails, the rep SHALL be recorded with verdict `infra_failure`.

#### Scenario: Transient infra failure recovered
- **WHEN** a rep fails with an MCP-connection infra failure and its single retry completes normally
- **THEN** the retry's result is scored and recorded, and no `infra_failure` verdict is recorded for the rep

#### Scenario: Persistent infra failure recorded
- **WHEN** a rep infra-fails twice
- **THEN** one result row with verdict `infra_failure` is recorded for the rep

### Requirement: Retro-judging mode
The driver SHALL provide a retro mode (`evals retro --workload <w> --sample <n>`) that: searches historical non-eval tasks for the workload via `search_tasks`, retrieves each task's transcript via `task_logs`, attributes the model from the transcript's `llm_turn_start` events, scores the historical output against the workload rubric, and records results under an `eval_runs` row with `mode='retro'`. Retro mode SHALL NOT clone profiles or submit tasks.

#### Scenario: Retro run over history
- **WHEN** `evals retro --workload job-research --sample 10` runs
- **THEN** 10 historical job-research tasks are judged and recorded under a retro run, with each result's `model` taken from the task's transcript

#### Scenario: Historical task without parseable model
- **WHEN** a sampled historical transcript contains no `llm_turn_start` event
- **THEN** the task is skipped and reported, and another sample is drawn when available

### Requirement: Driver configuration
The driver SHALL read `evals/config.yaml` providing at minimum: the Errand MCP endpoint URL and API key reference, the list of models under test, the judge model, and the production-yield poll interval. Command-line flags SHALL override config values.

#### Scenario: Model list from config
- **WHEN** `config.yaml` lists three models and the driver is invoked without a `--models` flag
- **THEN** the run matrix covers exactly those three models
