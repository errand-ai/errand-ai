## Context

When tasks are created, `generate_title()` in `errand/llm.py` calls the LLM to extract a title, category, and timing fields from the user's input. The raw input is then stored verbatim as the task description (`main.py:637`). This means descriptions like "In two hours, publish one of the approved tweets" contain scheduling language that's redundant — the timing is already captured in `execute_at`.

## Goals / Non-Goals

**Goals:**
- LLM produces a cleaned task description with scheduling/timing references removed
- Tasks with empty/null cleaned descriptions route to `review` status so the user can add a description
- Single LLM call handles title, category, timing, profile, and description extraction

**Non-Goals:**
- Changing the short-input path (≤5 words) — those already go to review
- Grammar correction or input rewriting beyond removing timing references
- Changing how the raw input is logged or audited

## Decisions

### 1. Add `description` to the existing LLM JSON schema

Add a `"description"` field to the JSON object the LLM returns. The prompt instructs the model to return the task description with all scheduling/timing language removed, keeping only what the agent needs to do.

**Why not a separate LLM call?** Doubles cost and latency for no benefit — the model already has the full context.

### 2. Fallback chain for description

```
llm_result.description  →  input_text  →  (empty = review)
```

- If LLM returns a non-empty `description`: use it
- If LLM returns null/empty `description` but succeeds otherwise: task is created with scheduling info extracted but description set to null, "Needs Info" tag applied, routed to `review`
- If LLM fails entirely: existing fallback behaviour (input_text as description, "Needs Info" tag, `review` status)

### 3. Empty description triggers "Needs Info" + review

When the LLM succeeds (valid JSON, title extracted, scheduling parsed) but the description is empty/null, this means the input was purely scheduling language with no actionable task content. The task should still be created with the extracted scheduling, but placed in `review` so the user can provide the actual task description.

## Risks / Trade-offs

- **LLM strips too much**: The model might over-aggressively remove content that happens to sound temporal. Mitigation: the prompt explicitly says to only remove scheduling/timing references, and the fallback preserves the original input.
- **LLM ignores the new field**: Older or simpler models might not return the `description` field. Mitigation: `_parse_llm_response` treats missing `description` as null, falling back to `input_text`.
- **max_tokens budget**: Adding one more field to the JSON response. Current limit is 200 tokens — should be sufficient since the description is a substring of the input with parts removed.
