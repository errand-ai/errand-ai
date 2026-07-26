# eval-corpus Specification

## Purpose
TBD - created by archiving change llm-eval-framework. Update Purpose after archive.
## Requirements
### Requirement: Corpus task spec format
Each corpus task SHALL be a YAML file at `evals/corpus/<workload>/<nnn>-<slug>.yaml` containing: `id` (string, `<workload>/<nnn>-<slug>`), `base_profile` (name of the task profile to clone), `description` (the verbatim task text submitted to Errand), `rubric` (markdown judging criteria), `assertions` (list, MAY be empty), `reps` (integer ≥ 1), and `timeout_minutes` (integer). The driver SHALL reject a corpus file missing any required field with an error naming the file and field.

#### Scenario: Valid corpus task loads
- **WHEN** the driver loads `evals/corpus/job-research/001-contract-market.yaml` containing all required fields
- **THEN** the task is included in the run matrix with its declared reps and timeout

#### Scenario: Invalid corpus task rejected
- **WHEN** a corpus file omits `rubric`
- **THEN** the driver exits with an error identifying the file and the missing field before submitting any tasks

### Requirement: Assertion types
Corpus assertions SHALL support at minimum: `output_contains` (case-insensitive substring of final output), `output_regex` (regex against final output), and `tool_called` (a tool name that MUST appear in the transcript's `tool_call` events). Each assertion SHALL evaluate to pass/fail independently.

#### Scenario: tool_called assertion
- **WHEN** a corpus task asserts `tool_called: read_rss_feed` and the transcript contains a `tool_call` event with `tool: read_rss_feed`
- **THEN** the assertion passes

#### Scenario: output_regex assertion fails
- **WHEN** a corpus task asserts `output_regex: "\\d+ jobs found"` and the final output contains no match
- **THEN** the assertion fails and is reported in the rep's scoring detail

### Requirement: Initial corpus covers read-only workloads only
The initial corpus SHALL contain only workloads whose tasks perform no external side effects (no email moves/forwards, no tweet posting, no Slack messages). Descriptions SHALL be derived from recurring historical tasks. Side-effectful workloads (email-triage, tweet-pipeline) SHALL NOT have live corpus entries until a dry-run tool capability exists.

#### Scenario: Corpus contents at introduction
- **WHEN** the corpus ships with this change
- **THEN** it contains tasks only for read-only workloads (e.g. job-research, tech-trends research, nginx log analysis, research summary, language translation)

### Requirement: Corpus versioning
Every live eval run SHALL record a corpus version equal to the repository's short git SHA at driver start. The driver SHALL warn when the working tree under `evals/corpus/` is dirty, since the recorded SHA would not describe the actual corpus content.

#### Scenario: Corpus version recorded
- **WHEN** the driver starts a run at commit `abc1234`
- **THEN** `start_eval_run` is called with `corpus_version="abc1234"`

#### Scenario: Dirty corpus warning
- **WHEN** `evals/corpus/` has uncommitted modifications at driver start
- **THEN** the driver prints a warning that the recorded corpus version is unreliable

