# Errand LLM eval framework

A standalone driver that measures which model best serves each Errand workload —
especially **which local model** (LM Studio via the LiteLLM gateway) is viable.
It runs eval tasks through the **real Errand task pipeline** (so it measures the
system that actually runs in production — compaction, tool-call recovery, skill
assembly and all), scores them with an LLM judge, and stores results in Errand's
database for longitudinal comparison.

The driver is a **pure MCP client**: it talks to Errand only through the MCP
endpoint (no DB, Kubernetes, or SSH). Run it from wherever LM Studio and the
`claude` CLI live.

## How it works

- **Corpus** (`corpus/<workload>/<nnn>-<slug>.yaml`): frozen task specs per
  workload — a verbatim `description`, a judging `rubric`, programmatic
  `assertions`, `reps`, and a `timeout_minutes`. The initial corpus covers
  **read-only** workloads only (job-research, tech-trends, log-analysis,
  research-summary, translation); side-effectful workloads wait for a dry-run
  tool capability.
- **Live run** (`run`): for each model (strictly sequential — LM Studio hosts one
  at a time) and each corpus task, the driver clones an `eval--<workload>--<slug>`
  profile, then runs each rep one-in-flight: yield to production → submit →
  poll → fetch output+transcript → score → record. Infra failures retry once.
  It cleans up the profiles and finishes the run only on success, so an
  interrupted run is resumable (`--run-id <id>` skips already-recorded cells).
- **Scoring**: programmatic assertions run first (a failed assertion forces a
  `fail`); then the `claude` CLI judges the output against the rubric using a
  bounded transcript digest, returning `{pass, score, reasons}`. Reps whose
  transcript shows infrastructure failure (skill install, MCP connection, zombie
  recovery, or no `agent_start`) are classified `infra_failure` and excluded from
  model scores.
- **Retro** (`retro --workload W --sample N`): phase-zero calibration — judges
  historical task outputs for a workload against its rubric (model attributed
  from the transcript) and records them under a `mode='retro'` run. No profiles,
  no task submission.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # mcp client + PyYAML
export ERRAND_MCP_API_KEY=<the shared mcp_api_key>
# Edit config.yaml: mcp_url, models under test, judge_model.
```

The `claude` CLI must be installed and logged in (used for judging under the Max
subscription).

## Usage

```bash
# Live matrix over all configured models and workloads:
python -m evals.cli run

# One workload, specific models, no yielding (quiet window):
python -m evals.cli run --workload translation --models "gemma-3-27b,qwen3-30b" --no-yield

# Resume an interrupted run:
python -m evals.cli run --run-id <run-id>

# Retro-baseline a workload from history:
python -m evals.cli retro --workload job-research --sample 10
```

## Authoring corpus tasks

Each YAML needs: `id` (`<workload>/<nnn>-<slug>`), `base_profile` (an **existing
production profile** to clone — set these to your deployment's real profile
names), `description` (verbatim task text), `rubric` (markdown), `assertions`
(list of single-key maps: `output_contains` / `output_regex` / `tool_called`),
`reps`, `timeout_minutes`. Cheap workloads get more reps.

The recorded `corpus_version` is the repo's short git SHA at driver start; commit
corpus changes before a run (the driver warns on a dirty `evals/corpus/` tree).

## Tests

```bash
python -m pytest evals/tests -q
```

Unit tests cover the pure logic (corpus, transcript parsing, assertions, digest,
judge JSON handling, verdict combination, matrix sequencing/resumability/infra
retry, retro attribution) with a fake MCP client and a fake judge — no live
Errand or `claude` needed.
