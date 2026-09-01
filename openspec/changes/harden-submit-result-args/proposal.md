## Why

`submit_result` is the task-runner's only output mechanism, and it has been failing
validation on roughly 85–95% of calls since 2026-08-28 — 164 failures in seven days
across 29 tasks. The serving stack behind LiteLLM moved from LM Studio to oMLX (same
Qwen 8-bit weights), and oMLX serialises the `questions` argument as a JSON-encoded
string (`"questions": "[]"`) instead of an array. The agents SDK validates against
`list[str] | None` and rejects it with `Invalid JSON input for tool submit_result`.

Tasks still complete — the text-JSON fallback in `extract_output` absorbs it — but each
one burns 3–6 wasted retry turns at ~62k input tokens and 75–180s apiece, and the model
narrates its own tool failure into the user-visible result.

The trigger is external, but the exposure is ours: `questions: list[str] | None = None`
is the only *optional* list parameter among the native tools, and the agents SDK renders
it as `anyOf: [array, null]`. Under the same oMLX serving stack, `discover_tools`'
plain-array `tool_names` was called 60 times with zero failures. The nullable union is
the shape that breaks; errand chose that shape and can stop choosing it.

## What Changes

- **Flatten the argument schema.** Change `questions: list[str] | None = None` to a
  non-nullable array annotation so the generated JSON Schema is a plain
  `{"type": "array", "items": {"type": "string"}}` with no `anyOf`/null branch —
  structurally identical to the parameter that has a 100% success rate under the same
  serving stack.
- **Coerce a JSON-encoded string.** Accept a string for `questions` and decode it, so
  the whole failure class disappears regardless of which serving stack LiteLLM routes
  to. `strict_json_schema=True` is only *enforced* by OpenAI's constrained decoder and
  is advisory on this path, so the schema alone cannot be relied on.
- **Pin the generated schema in a test.** Assert the emitted
  `params_json_schema` for `questions` contains no `anyOf` and no `"null"` type, so a
  future `| None` cannot silently reintroduce the union that caused this.

No change to the system prompt. The schema and `OUTPUT_INSTRUCTIONS` already state the
expected shape twice; the model is unconstrained, not under-informed — evidenced by it
also omitting `questions` entirely on 5 of 25 sampled calls despite the SDK marking all
three properties `required`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `submit-result-tool`: the `submit_result` argument contract gains two requirements —
  the `questions` parameter SHALL be declared as a non-nullable array (no `anyOf`), and
  the tool SHALL accept a JSON-encoded string for `questions` and decode it to a list.

## Impact

- `task-runner/tool_registry.py` — `submit_result` signature and body.
- `task-runner/test_tool_registry.py` — coercion cases plus the schema-shape guard.
- No API, database, or frontend change. No migration. Backwards compatible: callers
  passing a proper list are unaffected, and omitting `questions` still yields `[]`.
- Does not fix oMLX. Worth reporting upstream separately as a tool-call argument
  serialisation bug for nullable-array parameters.
