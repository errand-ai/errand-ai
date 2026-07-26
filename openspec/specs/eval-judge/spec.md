# eval-judge Specification

## Purpose
TBD - created by archiving change llm-eval-framework. Update Purpose after archive.
## Requirements
### Requirement: Failure classification precedes judging
Before any scoring, each rep SHALL be classified as `infra_failure` or judgeable. A rep is `infra_failure` when its transcript shows a skill dependency-install failure, an MCP server connection failure, zombie-state recovery, or terminates without an `agent_start` event. `infra_failure` reps SHALL NOT be judged and SHALL be excluded from model score aggregates.

#### Scenario: Pip-install breakage classified as infra
- **WHEN** a rep's transcript shows a skill `requirements.txt` install failure and no `agent_start` event
- **THEN** the rep is classified `infra_failure` and the judge is not invoked

#### Scenario: Bad output is a model failure, not infra
- **WHEN** a rep completes with an `agent_end` event but produces an incorrect result
- **THEN** the rep is judgeable and its verdict comes from assertions and the judge

### Requirement: Programmatic assertions evaluated before the judge
The scorer SHALL evaluate all corpus assertions for a rep against the final output and transcript events. Assertion results SHALL be included in the recorded scoring detail. A rep with any failed assertion SHALL be recorded with verdict `fail` regardless of the judge's rubric score; the judge SHALL still run to capture qualitative detail.

#### Scenario: Failed assertion forces fail verdict
- **WHEN** a required `tool_called` assertion fails but the judge scores the output 8/10
- **THEN** the rep's verdict is `fail` and both the assertion result and judge output are recorded

### Requirement: LLM judge via claude CLI
The scorer SHALL invoke the `claude` CLI headless (print mode with JSON output) using the judge model pinned in `evals/config.yaml`. The judge prompt SHALL contain the corpus task description, the rubric, the final output, and a transcript digest, and SHALL request a strict JSON verdict containing at minimum `pass` (boolean), `score` (0–10), and `reasons`. The judge's full response SHALL be recorded in the result's `judge_output`. A judge response that is not parseable as the required JSON SHALL be retried once; a second parse failure SHALL record the rep with a null score and the raw response preserved.

#### Scenario: Judge verdict recorded
- **WHEN** the judge returns `{"pass": true, "score": 7, "reasons": [...]}` for a rep
- **THEN** the rep's verdict is `pass`, score `7`, and the full judge response is stored in `judge_output`

#### Scenario: Unparseable judge response
- **WHEN** the judge returns non-JSON output twice for the same rep
- **THEN** the rep is recorded with a null score and the raw responses preserved in `judge_output`

### Requirement: Bounded transcript digest
The scorer SHALL build the judge's transcript view as a bounded digest — the sequence of tool calls (names and truncated arguments) and truncated tool results — rather than the raw `runner_logs`. Dependency-install output and other non-event log lines SHALL be excluded. The digest SHALL be capped at a configurable size.

#### Scenario: Long transcript digested
- **WHEN** a rep's transcript has 66 turns and raw logs of 240 kB
- **THEN** the judge receives a digest within the configured cap containing every tool call name and truncated results

### Requirement: Metrics extracted from transcript events
For each judgeable rep the scorer SHALL extract from the transcript: turn count (`llm_turn_start` events), tool-call recovery count (`tool_call_recovered_from_reasoning` events), and error event count (`error` events). Wall time SHALL be measured driver-side from observed status transitions. These metrics SHALL be recorded with the result.

#### Scenario: Metrics recorded
- **WHEN** a rep's transcript contains 23 `llm_turn_start`, 2 recovery, and 0 error events
- **THEN** the recorded result has `turns=23`, `recoveries=2`, `error_events=0`

