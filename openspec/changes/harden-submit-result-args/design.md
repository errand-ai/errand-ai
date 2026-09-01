## Context

`submit_result` (`task-runner/tool_registry.py`) is the task-runner's primary output
mechanism. Since 2026-08-28 it has been rejecting 85–95% of calls with
`Invalid JSON input for tool submit_result`.

Measured from Loki (`{app="task-runner"}`, datasource `P8E80F9AEF21F6940`):

- 164 failures in 7 days across 29 task pods; `submit_result` is the **only** tool that
  ever appears in that error.
- Cause: the argument arrives as `"questions": "[]"` — a JSON-encoded string where the
  schema declares an array.
- Of 25 sampled `tool_call` events, 20 had a stringified `questions` (all failed) and 5
  omitted `questions` entirely (all succeeded).
- Failure rate per day from 2026-08-28: 75% → 88% → 90% → 81% → 95%. Before that,
  effectively zero across comparable call volume.

The trigger is a serving-stack change, not a model change: `qwen3.8-27b-mlx` (LM Studio)
and `Qwen3.8-27B-MLX-8bit` / `-4bit` (oMLX) are the same weights. No errand deploy
occurred at the step — pod `errand-server-7bb49f548d-q6xlw` ran continuously
2026-08-26 → 2026-08-30.

The schema errand emits is correct and explicit (verified by dumping
`submit_result.params_json_schema`):

```json
"questions": {
  "anyOf": [ {"type": "array", "items": {"type": "string"}}, {"type": "null"} ],
  "description": "Follow-up questions when status is \"needs_input\". Defaults to []."
}
```

## Goals / Non-Goals

**Goals:**

- Eliminate the `Invalid JSON input for tool submit_result` failure class.
- Make the fix independent of which serving stack LiteLLM routes to.
- Prevent regression of the schema shape that caused it.

**Non-Goals:**

- Fixing oMLX. That is an upstream bug, tracked separately.
- Changing `OUTPUT_INSTRUCTIONS` or any other system-prompt text.
- Changing the output-extraction fallback chain in `extract_output`. It worked: hard
  task failures stayed flat (~8–11/day) across the step.
- Generalised coercion across all tools. Only `submit_result` is affected, and a blanket
  coercion layer would mask real schema errors.

## Decisions

### Decision 1: Flatten the schema *and* coerce, not one or the other

Both, because they defend different failure modes.

Flattening removes the shape that oMLX mishandles. The evidence is a controlled
comparison: within the oMLX window, same weights and same tasks,
`discover_tools(tool_names: list[str])` — a plain, required array — was called 60 times
with **zero** failures, while `submit_result.questions` — a nullable union — failed
85–95%.

Coercion is needed anyway because `strict_json_schema=True` is only *enforced* by
OpenAI's constrained decoder; behind LiteLLM → MLX it is advisory. Nothing guarantees
the next serving stack respects the flattened schema either. Independent evidence that
the model is unconstrained rather than under-informed: the SDK's strict transform marks
all three properties `required`, yet 5 of 25 sampled calls omitted `questions`.

*Alternative considered — flatten only:* cheaper, but rests on an inference about oMLX's
parser that we cannot verify without reading its source. Leaves us re-diagnosing this if
a future stack behaves differently.

*Alternative considered — coerce only:* sufficient to stop the failures, but leaves in
place a schema shape now known to be hazardous, and leaves the next optional-list
parameter to rediscover it.

### Decision 2: Do not touch the system prompt

`OUTPUT_INSTRUCTIONS` (`task-runner/main.py:536`) already shows the literal call shape
`questions=["<question 1>", "<question 2>"]`, and the tool schema states the type. The
information is present twice. A model that omits a `required` property will not be
rescued by a third restatement of that property's type. Prose does not constrain
decoding; schema shape and server-side tolerance do.

### Decision 3: Coerce narrowly, and never silently discard

The parameter type becomes `QuestionList`, a `list` subclass carrying pydantic's
`__get_pydantic_core_schema__` / `__get_pydantic_json_schema__` hooks: the core-schema
hook routes validation through `_normalise_questions`, the JSON-schema hook emits a bare
string array. This is what lets Decisions 1 and 3 hold at once — a plain
`list[str] | str` union would put `anyOf: [array, string]` back into the emitted schema,
re-advertising to the model the very shape we are trying to stop it sending, and
`Annotated[list[str], BeforeValidator(...)]` does not survive: the agents SDK strips
`Annotated` to the bare type (keeping only a description or `FieldInfo`) before building
its pydantic model, discarding any validator or `WithJsonSchema` placed there.

`_normalise_questions` returns `[]` for `None`; `json.loads`-es a string and, if it
decodes to a list, stringifies its elements; if it decodes to anything else, or fails to
decode, the raw string is wrapped as a single-element list rather than dropped. A dropped
follow-up question is worse than a slightly malformed one — the user sees the question
either way, and the task is not silently degraded. The tool body calls the helper too, so
the stored value is normalised on the direct-call path as well as through SDK validation.

### Decision 4: Pin the schema shape in a test, not a comment

`test_submit_result_questions_schema_is_plain_array` asserts the generated
`params_json_schema` for `questions` has `type == "array"` and contains neither `anyOf`
nor a `"null"` type. A comment saying "don't add `| None`" is not enforcement; this
turns the regression into a test failure at the point it is introduced.

## Risks / Trade-offs

- **Flattening may not change oMLX's behaviour** → Coercion makes the outcome
  independent of that. The evidence for flattening is strong (60/60 under the same
  stack) but comes from production behaviour, not from reading oMLX's parser.
- **A mutable default `[]` in the signature** → Never mutated; the body builds a new
  list. The agents SDK also constructs arguments per call from the JSON payload. The
  alternative (`None` sentinel) is exactly the union being removed.
- **Coercion could mask a genuinely malformed payload** → It is scoped to one parameter
  of one tool, and the non-decoding path preserves the raw string rather than swallowing
  it, so the malformation stays visible in the delivered result.
- **The archive re-triggers CI and produces a new image tag** → Deployment verification
  must be repeated on the post-archive build, per the project workflow.

## Migration Plan

No data migration, no API change, no config change. Backwards compatible: callers
passing a proper list are unaffected, and omitting `questions` still yields `[]`.

Deploy is the normal task-runner image build. Rollback is reverting the commit — the
prior behaviour is the current (broken but non-fatal) state, since `extract_output`
absorbs the failure.

Verification after deploy: the count of
`Invalid JSON input for tool submit_result` in `{app="task-runner"}` should fall to zero
while `submit_result` `tool_call` volume stays flat. A drop in *both* would mean tasks
stopped running, not that the bug was fixed.

## Open Questions

- Should the upstream oMLX report be filed from this change or tracked separately?
  Proposed: separately — it does not gate this fix.
