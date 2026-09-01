## 1. Setup

- [x] 1.1 Bump `VERSION` from `0.148.0` to `0.148.1` (patch — bug fix, no API change)

## 2. Implementation

- [x] 2.1 Flatten the `questions` parameter in `task-runner/tool_registry.py`: change `questions: list[str] | None = None` to a non-nullable array annotation so the generated schema has no `anyOf` and no `"null"` type
- [x] 2.2 Accept a string without widening the emitted schema: a bare `list[str] | str` union re-adds `anyOf` (forbidden by 3.1), and the agents SDK strips `Annotated` metadata so `BeforeValidator`/`WithJsonSchema` are discarded. Instead declare `questions: QuestionList`, a `list` subclass whose `__get_pydantic_core_schema__` coerces via `_normalise_questions` and whose `__get_pydantic_json_schema__` emits a plain string array — so a JSON-encoded array reaches the tool body while the model still sees a bare array
- [x] 2.3 Add a `_normalise_questions` helper that returns `[]` for `None`, decodes a string via `json.loads`, stringifies the elements of a decoded array, and wraps a non-decoding or non-array string as a single-element list
- [x] 2.4 Call the helper when building `ctx.context.submitted_result` so the stored `questions` is always a list of strings
- [x] 2.5 Update the `questions` docstring line to state that a JSON-encoded array string is accepted, keeping the generated tool description accurate

## 3. Tests

- [x] 3.1 Add `test_submit_result_questions_schema_is_plain_array` asserting the generated `params_json_schema` for `questions` has `type == "array"` with string items and contains neither `anyOf` nor a `"null"` type
- [x] 3.2 Add coercion tests for each spec scenario: JSON-encoded empty array, JSON-encoded populated array, non-JSON string, JSON-encoded non-array, and `questions` omitted
- [x] 3.3 Confirm the existing `submit_result` tests still pass unchanged (`test_submit_result_stores_in_context`, `test_submit_result_needs_input`, `test_submit_result_defaults`, `test_submit_result_last_call_wins`, `test_submit_result_rejects_invalid_status`)

## 4. Local verification

- [x] 4.1 Run the task-runner suite: `task-runner/.venv/bin/python -m pytest task-runner/ -v` — all tests pass
- [x] 4.2 Run the errand suite to confirm no cross-impact: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -q`
- [x] 4.3 Bring up the stack with `docker compose -f testing/docker-compose.yml up --build` and confirm it starts clean

## 5. PR and deployment verification

- [ ] 5.1 Push the branch and open a PR
- [ ] 5.2 Confirm the GitHub Actions build completes (images + Helm chart pushed to GHCR)
- [ ] 5.3 Confirm the built artifacts deploy cleanly on Kubernetes (ArgoCD sync) and the deployment is healthy
- [ ] 5.4 Run a task end-to-end on the deployed build and confirm `submit_result` succeeds on the first call — check the transcript for absence of `Invalid JSON input for tool submit_result`
- [ ] 5.5 Confirm in Loki that `Invalid JSON input for tool submit_result` falls to zero while `submit_result` `tool_call` volume stays flat (a drop in both would mean tasks stopped running, not that the bug was fixed)

## 6. Archive

- [ ] 6.1 Run `openspec archive "harden-submit-result-args" -y` and commit the flattened spec plus the archive move as part of this PR
- [ ] 6.2 Re-verify the redeployed post-archive build, since archiving produces a new image tag

## Post-merge notes

- Merge the PR once the post-archive build is verified.
- Delete the local branch: `git branch -d harden-submit-result-args`.
- File the oMLX upstream report separately: nullable-array tool parameters (`anyOf: [array, null]`) are serialised as JSON-encoded strings. It does not gate this fix.
- Watch the `Invalid JSON input for tool submit_result` count on `main` for a few days to confirm the fix holds across serving-stack changes.
