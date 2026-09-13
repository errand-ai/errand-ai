## 1. Branch and version

- [x] 1.1 Create branch `first-run-model-selection` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` (minor — new API surface, new scan-result fields, changed task routing)

## 2. Title generation reports why it failed

- [x] 2.1 Write failing tests: an unconfigured model reports not-attempted; a model naming a departed provider reports not-attempted; a completed request returning unusable content reports attempted; a success reports success. In every failing case the fallback title is still returned
- [x] 2.2 Carry the cause on `LLMResult` — the caller must not re-derive it from the setting (D2), because `resolve_model_setting` already treats a departed provider as unset and re-reading races the state being described
- [x] 2.3 Confirm the other callers of `generate_title` still compile against the widened result and are unaffected by the new field

## 3. A task the classifier could not reach is not `Needs Info`

- [x] 3.1 Write failing tests: with no model configured, a long input creates a `pending` task with no `Needs Info` tag and the user's input as its description; with a departed provider likewise; a completed-but-unusable classification still gets `Needs Info` and `review`
- [x] 3.2 Route on the cause in `create_task` rather than on `success` alone — and in the two Slack intake paths, which replicate the same tagging. The requirement is capability-level ("Auto-routing after task creation"), so fixing only the web path would have left the defect reachable from Slack
- [x] 3.3 Carry a machine-readable indication of the unconfigured state on the creation response, so a caller can explain the degraded classification rather than the user inferring it
- [x] 3.4 Leave the short-input rule alone — there the classifier is deliberately not run, which is a judgement about the input and not a failure to reach anything (D1)
- [x] 3.5 Confirm a task created this way actually reaches the runner, rather than trading a silent park for a silent failure

The renamed scenario, and why it is done this way: `task-categorisation`'s existing `#### Scenario: LLM failure goes to review` now describes only the completed-but-unusable case, so its heading is wrong. `openspec archive` compares scenario headings and refuses to drop one, and renaming is not an expressible delta operation — so the delta keeps the old heading with corrected content, and the flattened spec is renamed separately.

- [ ] 3.6 After archiving, rename that scenario in `openspec/specs/task-categorisation/spec.md` to describe the case it now covers, in this PR — correcting only the body leaves a heading that contradicts it

## 4. Choosing a model, and never guessing one

- [x] 4.1 Write failing tests: a provider listing exactly one model establishes it; a provider listing several with no supplied choice establishes nothing; a listing that cannot be retrieved establishes nothing; no selection is made by position or by name
- [x] 4.2 Implement establishing model settings from a provider, setting both `llm_model` and `task_processing_model` (D3, and the two-settings note in Risks)
- [x] 4.3 Apply only where no model is configured, by the empty-installation rule detection already uses for the default provider (D6) — an installation with settings keeps them
- [ ] 4.4 Verify against a real multi-model runtime that nothing is written, and against a single-model one that it is

## 5. The caller-supplied choice

- [x] 5.1 Write failing tests: a valid provider and listed model establishes both settings; a model the provider does not list is refused and changes nothing; a provider that does not exist is refused and changes nothing
- [x] 5.2 Expose the choice through the API, validating the model against the provider's listing — a setting naming a model the provider does not serve fails at the point of use, far from where the mistake was made
- [x] 5.3 Confirm it sets the settings that actually govern classification and execution, not one of them — leaving either unset keeps this change's own defect alive in that role (D10)
- [x] 5.4 Keep it a single operation rather than a settings write, so no caller carries the current set of role keys (D9)

## 6. Whether a model is configured is answerable

- [x] 6.1 Write failing tests: unset reports not-configured; a valid setting reports configured; a setting naming a deleted provider reports not-configured
- [x] 6.2 Expose the state so a caller need not read the settings and cross-check the provider list (D7)
- [x] 6.3 Add the provider and the model-configured state to the scan result, so a caller can ask the question at the moment the scan answers (D5), and say which model was established where one was
- [x] 6.4 Confirm an unavailable scan reports nothing about models — "cannot tell" is not "not configured", the distinction this capability already makes for detection
- [x] 6.5 Confirm the state is readable where a caller managing providers already looks, without running a scan — a card renders on mount, and a scan is a side-effecting reconciliation, not a question

## 7. The hardcoded task-processing model

- [x] 7.1 Write a failing test asserting that an unset `task_processing_model` does not resolve to a model name with no provider
- [x] 7.2 Establish what reaching `DEFAULT_TASK_PROCESSING_MODEL` should do now that the unset state is addressed upstream — it cannot succeed as written, producing an empty `OPENAI_BASE_URL` and a runner that exits on missing environment variables
- [x] 7.3 Check for callers relying on the constant's string value before changing or removing it

## 8. Settings UI

Requires a `@errand-ai/ui-components` release and a consumer bump; everything above ships without it, and the ordering is forced — the card cannot ship against a server that does not serve these endpoints (D8).

- [x] 8.1 Specify the scan-panel and settings changes as an OpenSpec change in `errand-component-library` — the model question after a scan, the automatically-established model stated rather than asked, the missing-model state shown without being an error, a refused choice keeping the question open, and the question disclosing that one answer sets both roles. Raised there as `first-run-model-choice`, planning only, declaring no type or fixture until captured responses exist
- [ ] 8.2 Implement and release it there
- [ ] 8.3 Bump the pin here and confirm the lockfile diff touches only that entry
- [ ] 8.4 Extend `frontend/src/components/__tests__/LlmProviderCardSeam.test.ts` with the new scan-result shape and the model-choice call, captured from this repo's endpoints via `errand/tests/capture_seam_fixture.py` rather than written by hand

The capture is a handoff, and `first-run-model-choice` is waiting on it before it writes a single type. It declares no field or fixture until then, deliberately: the two defects that survived releases across this seam — `base_url` typed `string` where this server sends null, and a required `has_api_key` this server has never sent — both came from fixtures derived from a delta document, which proves only that both sides read the spec the same way. Send the capture before they type anything, and if a field disagrees with what the card expects, the capture is right.

- [ ] 8.5 Capture and hand over, at minimum: a scan on an installation with **no model configured**; a scan where a **sole model was established automatically**, including the field naming that model — stating it is a requirement on their side and they cannot invent the field; a scan where **detection is unavailable**, so all three model fields are `null` — asked for specifically, because the three-valued rule is the one most worth failing against a real response rather than a fixture written to match one reading of the spec; the **model-selection read**, which is what the card reads on mount; and the selection call **accepted**, **refused for a model the provider does not list**, and **refused for a provider that does not exist**

## 9. Verify

- [ ] 9.1 Run the full errand, task-runner and frontend test suites
- [ ] 9.2 End to end from an empty database: bring the stack up with no providers and no settings, scan, observe the reported missing model, choose one, create a task in the user's own words, and watch it run to completion
- [ ] 9.3 Confirm the same flow with a single-model runtime asks nothing and still runs
- [ ] 9.4 Confirm an installation that already has model settings is untouched by a scan

## 10. Archive

- [ ] 10.1 `openspec archive first-run-model-selection -y` and commit the result in this PR

## Post-merge notes

- `interactive-task-spec` becomes implementable after this: its clarification loop is an LLM call and cannot run on an installation with no model configured.
- The automatic path covers only single-model providers, which is the minority. If first-run friction is still the complaint after this ships, the next lever is the model *listing* — a provider that reported which of its models can chat would remove the question entirely, and that is a request to make of the runtimes rather than a heuristic to write here.
- `DEFAULT_TASK_PROCESSING_MODEL` naming a specific vendor model is worth revisiting across the codebase, not only where this change touches it.
