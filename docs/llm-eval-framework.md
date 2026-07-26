# LLM Eval Framework — Operator Handbook

This guide covers running the Errand LLM eval framework: deciding, with evidence,
which model best serves each workload — especially **which local model** (LM
Studio via the LiteLLM gateway) is viable.

Eval tasks run through the **real** Errand task pipeline (the same compaction,
tool-call recovery, and skill/prompt assembly production uses), then an
LLM-as-judge scores them and the results are stored in Errand's database for
longitudinal comparison.

The driver is a **pure MCP client**: it talks to Errand only through the MCP
endpoint (no database, Kubernetes, or SSH access). You run it from wherever LM
Studio and the `claude` CLI live — typically the Mac hosting LM Studio.

---

## Mental model

| Term | Meaning |
|------|---------|
| **Corpus task** | A frozen task spec (YAML) for one workload: a verbatim `description`, a judging `rubric`, programmatic `assertions`, `reps`, `timeout_minutes`. |
| **Workload** | A recurring job type (e.g. `job-research`, `translation`). One directory of corpus tasks. |
| **Run** | One eval session. `live` = a model×workload bake-off; `retro` = judging historical outputs. Stored in `eval_runs`. |
| **Cell** | One `(workload, model, rep)` combination. Each produces one `eval_results` row. |
| **Verdict** | `pass` / `fail` / `infra_failure`. Infra failures are excluded from model scores. |
| **Eval profile** | A throwaway clone `eval--<workload>--<model-slug>` of a production profile, with the model overridden. Created and deleted by the driver. |
| **`is_eval`** | Eval tasks are flagged server-side and hidden from the board; retained as raw evidence. |

The typical order is: **retro first** (baseline history, calibrate rubrics),
then a small **live pilot**, then the **full live matrix**.

---

## Prerequisites

### On the Errand deployment (one-time, done by this change)

- **Migration `030`** applied (adds `tasks.is_eval`, `eval_runs`, `eval_results`).
  Alembic runs it automatically on deploy.
- Server and task-runner images that include the eval MCP tools and the catalog
  exclusion (i.e. this change is deployed).
- The workloads you want to evaluate have **real production profiles** in Errand
  (Settings → Task Profiles) — the corpus clones these.

### On the driver machine (the Mac hosting LM Studio)

- **Python 3.12+**.
- **LM Studio** running and serving the local model(s) under test. LM Studio
  serves **one model at a time**, which is why the driver batches models
  sequentially.
- The **`claude` CLI** installed and logged in (used for judging under your Max
  subscription — judging is independent of the models under test and has zero
  marginal cost).
- Network access to the Errand MCP endpoint and the **shared MCP API key**
  (the `mcp_api_key` Errand setting).

> **Security note.** The eval/admin MCP tools are reachable with the shared API
> key. They are excluded from the task-runner catalog (a task LLM can never see
> or call them), and profile mutation is restricted to the `eval--` name prefix,
> so the blast radius is bounded. Treat the API key like a password. A separate
> admin key is the upgrade path if Errand ever goes multi-user.

---

## 1. Install the driver

From a checkout of this repo, on the driver machine:

```bash
cd evals
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt        # mcp client + PyYAML
```

## 2. Configure

Edit `evals/config.yaml`:

```yaml
errand:
  mcp_url: "https://errand.devops-consultants.net/mcp"   # include the /mcp path
  api_key_env: "ERRAND_MCP_API_KEY"     # NAME of the env var holding the key
models:                                 # LiteLLM model slugs under test
  - "gemma-3-27b"
  - "qwen3-30b"
judge_model: "claude-opus-4-8"          # passed to `claude --model`
yield_poll_interval_seconds: 30         # how often to re-check for production work
task_poll_interval_seconds: 15          # how often to poll a submitted eval task
digest_max_chars: 12000                 # judge transcript-digest cap
```

The API key itself is **never** stored in the file — export it in the shell:

```bash
export ERRAND_MCP_API_KEY="<the shared mcp_api_key>"
```

| Config key | Meaning |
|------------|---------|
| `errand.mcp_url` | Errand MCP streamable-HTTP endpoint (with `/mcp`). |
| `errand.api_key_env` | Name of the env var the driver reads the Bearer key from. |
| `models` | LiteLLM model slugs to evaluate. Each becomes one sequential batch and one `eval--<workload>--<slug>` profile. |
| `judge_model` | Model passed to the `claude` CLI for judging. |
| `yield_poll_interval_seconds` | Cadence for the yield-to-production check. |
| `task_poll_interval_seconds` | Cadence for polling a submitted eval task to completion. |
| `digest_max_chars` | Max size of the transcript digest shown to the judge. |

Command-line flags override config values (`--models`, `--workload`, etc.).

## 3. The corpus

Corpus tasks live at `evals/corpus/<workload>/<nnn>-<slug>.yaml`. The initial
corpus ships with **read-only** workloads only (no email, tweets, or Slack
side-effects): `job-research`, `tech-trends`, `log-analysis`, `research-summary`,
`translation`.

```yaml
id: job-research/001-contract-market      # "<workload>/<nnn>-<slug>"
base_profile: job-research                # a REAL production profile to clone
description: |                            # verbatim task text submitted to Errand
  Research the current UK contract market for senior DevOps roles...
rubric: |                                # markdown judging criteria
  Grade on coverage (>=10 sourced roles), evidence (real URLs, concrete rates)...
assertions:                              # programmatic, single-key maps
  - tool_called: web_search              #   a tool that must appear in the transcript
  - output_regex: "https?://"            #   regex against the final output
reps: 2                                   # repetitions (cheap workloads get more)
timeout_minutes: 40
```

**Before your first run, set every `base_profile` to a profile name that
actually exists in your Errand deployment.** The three assertion types are
`output_contains` (case-insensitive substring), `output_regex`, and
`tool_called`. A rep with any failed assertion is a `fail` regardless of the
judge's score (the judge still runs, to capture qualitative detail).

The recorded `corpus_version` is the repo's short git SHA at driver start —
**commit corpus changes before a run**; the driver warns on a dirty
`evals/corpus/` tree.

---

## 4. Run it

### Phase 0 — retro (baseline + rubric calibration)

Judge historical outputs for a workload against its rubric. No profiles cloned,
no tasks submitted — it just reads history and scores it.

```bash
python -m evals.cli retro --workload job-research --sample 10
```

Read the recorded scores and the `judge_output.judge.reasons`. Where the judge
disagrees with your own read, **edit the rubric** in the corpus YAML and re-run.
This is how you calibrate before spending real inference on a live bake-off.

### Phase 1 — live pilot

One model, one workload, a couple of reps, to prove the whole loop
(clone → submit → poll → score → record → cleanup):

```bash
python -m evals.cli run --workload translation --models "gemma-3-27b" --no-yield
```

### Phase 2 — full live matrix

All configured models × all corpus workloads:

```bash
python -m evals.cli run
```

The driver iterates **models sequentially** (one LM Studio model at a time),
runs **one eval task at a time**, and by default **yields to production**: before
each submission it waits while any non-eval task is pending or running. Best run
in a quiet window.

| Flag | Effect |
|------|--------|
| `--workload W` | Limit the run to one workload. |
| `--models "a,b"` | Override the config model list. |
| `--no-yield` | Don't wait for production tasks (use only in a quiet window). |
| `--run-id ID` | **Resume** an interrupted run — skips every already-recorded cell. |

**Resuming:** if a run is interrupted, re-invoke with the same `--run-id`
(printed at run start, or find it in `eval_runs`). Completed cells are skipped;
the eval profiles it created are reused. Profiles are cleaned up and the run is
marked finished only on successful completion.

---

## 5. View and interpret results

Results live in two Postgres tables. Query them directly (psql), via a Grafana
Postgres datasource, or via the `get_eval_run` MCP tool.

**`eval_runs`** — one row per session: `id`, `mode` (`live`/`retro`),
`started_at`, `finished_at`, `corpus_version`, `errand_version`, `judge_model`,
`driver_host`, `notes`.

**`eval_results`** — one row per cell: `run_id`, `workload`, `model`, `task_id`
(links to the retained eval task transcript), `rep`, `verdict`, `score`
(0–10, null if the judge couldn't be parsed), `turns`, `recoveries`,
`error_events`, `wall_seconds`, `judge_output` (JSONB: assertions + full judge
response + digest).

### The league table — best model per workload

Average model quality per workload, **excluding infra failures**, with pass rate
and cost proxies:

```sql
SELECT workload,
       model,
       round(avg(score) FILTER (WHERE verdict <> 'infra_failure'), 2) AS avg_score,
       round(avg((verdict = 'pass')::int)::numeric, 2)                AS pass_rate,
       round(avg(turns)::numeric, 1)                                  AS avg_turns,
       round(avg(recoveries)::numeric, 1)                             AS avg_recoveries,
       count(*)                                                       AS reps
FROM eval_results
WHERE run_id = '<run-id>'
GROUP BY workload, model
ORDER BY workload, avg_score DESC NULLS LAST;
```

### Suite health — infra failure rate

A high infra rate means the *environment* (skill installs, MCP connectivity),
not the model, is failing — fix that before trusting the scores:

```sql
SELECT workload, model,
       round(avg((verdict = 'infra_failure')::int)::numeric, 2) AS infra_rate,
       count(*) AS reps
FROM eval_results
WHERE run_id = '<run-id>'
GROUP BY workload, model
ORDER BY infra_rate DESC;
```

### Interpreting the numbers

- **`avg_score`** — the judge's 0–10 rubric quality, averaged over judgeable
  reps. This is your primary "which model is better" signal.
- **`pass_rate`** — fraction of reps that both passed all assertions *and* got a
  passing judge verdict. A model can score well on average but fail assertions
  (e.g. never called a required tool) — check both.
- **`avg_recoveries`** — `tool_call_recovered_from_reasoning` events. High counts
  mean a local model is emitting malformed tool calls that the runner's rescue
  machinery is catching. It "works," but it's a fragility signal for that model.
- **`avg_turns` / `wall_seconds`** — cost proxies. Two models with similar scores
  but very different turn counts have very different real cost.
- **`score IS NULL`** — the judge's response couldn't be parsed twice; the raw
  responses are in `judge_output.judge.raw` for re-judging. A cluster of nulls
  means the judge prompt/model needs attention, not the model under test.
- **Free-cloud caveat.** Free-tier cloud models drift (backend/quantization
  changes). Treat their scores as weaker evidence than local-model scores, and
  re-run when comparing.

### Reading one rep in detail

`judge_output` holds the full picture for a cell — the per-assertion results, the
judge's `{pass, score, reasons}`, and the transcript digest the judge saw. To see
the actual task the model produced, look up its `task_id`:

```bash
# via MCP (search is is_eval-aware):
search_tasks(is_eval=true, profile="eval--job-research--gemma-3-27b")
task_logs(<task_id>)      # full transcript
task_output(<task_id>)    # final output
```

### Grafana

Point a Grafana **Postgres datasource** at the Errand database and chart
`eval_results` (e.g. `avg(score)` by `model`, faceted by `workload`, filtered to
one `run_id`). A packaged dashboard is out of scope for this change — the tables
are designed to be directly chartable.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|-------------------|
| `MCP API key env var '...' is unset` | Export the key under the name in `api_key_env`. |
| `source profile '<x>' not found` | A corpus `base_profile` doesn't match a real Errand profile. |
| High `infra_failure` rate | Skill installs or MCP connectivity are failing in the task-runner — fix the environment, not the corpus. |
| Many `score IS NULL` | The `claude` CLI isn't returning parseable JSON — check it's logged in and the `judge_model` is valid; inspect `judge_output.judge.raw`. |
| Run seems stuck | The driver is yielding to production work. Use `--no-yield` in a quiet window, or let production drain. |
| LM Studio thrashing between models | A production task on a *different* local model arrived mid-eval, forcing a swap. Run local batches in quiet windows. |
| Dirty-corpus warning | Commit your `evals/corpus/` changes so the recorded `corpus_version` describes what actually ran. |

---

## What comes next

1. **Calibrate rubrics** via retro until the judge agrees with your own reading,
   then record a retro baseline per workload.
2. **Run the live matrix** and build per-workload league tables (best local, best
   overall). Re-run periodically as new models appear — runs are cheap to
   schedule and fully comparable via the pinned `corpus_version` / `errand_version`.
3. **Act on the results** — reassign production task profiles to the winning
   model per workload (especially promoting viable local models to cut cost).
4. **Expand the corpus** — add more tasks per workload for statistical weight;
   cheap workloads can afford more `reps`.

### Deliberately out of scope (future changes)

- **Side-effectful workloads** (email-triage, tweet-pipeline) need a dry-run/
  capture mode for their tools before they can be evaluated live — a separate
  change. The initial corpus is read-only only.
- **A packaged Grafana dashboard** (the tables are chartable today).
- **Token/cost metrics** — runner events currently carry no token usage; adding
  it is a future runner change. Use `turns` and `wall_seconds` as proxies for now.
- **Automated scheduling / CI integration** of eval runs.
