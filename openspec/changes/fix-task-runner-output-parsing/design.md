## Context

The task runner agent (`task-runner/main.py`) instructs the LLM to output a JSON object with `{status, result, questions}`. Both the task runner and the worker (`backend/worker.py`) attempt to strip markdown code fences before parsing. However, the current logic only handles the case where the output **starts** with ```` ``` ```` — it fails when the LLM produces preamble text before the JSON block.

In production, the "Check ArgoCD Applications Health" task produced output like:

```
Based on my analysis of all 53 applications...

```json
{"status": "completed", "result": "## ArgoCD Health Report...", "questions": []}
```
```

The `startswith("```")` check missed this, JSON parsing failed, and the fallback wrapped the entire raw output (preamble + code fence + JSON) as the result string.

## Goals / Non-Goals

**Goals:**
- Extract valid JSON from LLM output regardless of surrounding preamble text or markdown formatting
- Apply the extraction logic in both the task runner and worker (defence in depth)
- Cover the new edge cases with tests

**Non-Goals:**
- Changing the LLM prompt (prompt changes are fragile and model-dependent)
- Adding markdown rendering to the frontend output viewer (separate concern)
- Handling cases where the LLM produces multiple JSON blocks (take the first valid one)

## Decisions

### 1. Extract JSON by searching for the outermost `{...}` object

Rather than only stripping leading code fences, the extraction logic will:

1. **Try direct parse** — if the full text is valid JSON, use it
2. **Try code-fence extraction** — find ```` ```json...``` ```` or ```` ```...``` ```` blocks anywhere in the text, extract the content, and try to parse
3. **Try brace extraction** — find the first `{` and last `}` in the text, extract that substring, and try to parse

This ordered approach handles: bare JSON, JSON in code fences (with or without preamble), and JSON embedded in prose.

**Alternative considered**: Using a regex to match the full `TaskRunnerOutput` schema — rejected because it's fragile against nested JSON and varying whitespace.

**Alternative considered**: Only improving the prompt — rejected because LLM compliance is probabilistic and the extraction should be robust regardless.

### 2. Shared utility function in both locations

The extraction logic will be implemented as a standalone function (`extract_json`) in both `task-runner/main.py` and `backend/worker.py`. Since the task runner runs in an isolated container with minimal dependencies, we won't create a shared library — duplicating a small utility is simpler than cross-package imports.

### 3. Validate extracted JSON against TaskRunnerOutput schema

After extraction, the JSON must still validate against `TaskRunnerOutput` (status + result + questions). If extraction finds JSON that doesn't match the schema, the existing fallback behaviour applies (task runner wraps as completed; worker retries).

## Risks / Trade-offs

- **False positive extraction**: The brace-matching fallback could match a JSON-like substring that isn't the intended output → Mitigation: schema validation after extraction catches this; fallback behaviour is unchanged.
- **Duplicated logic**: The same function exists in two codebases → Mitigation: the function is small (~20 lines), well-tested, and the two codebases are deployed independently.
