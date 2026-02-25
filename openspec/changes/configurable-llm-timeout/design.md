## Context

`errand/llm.py:generate_title()` calls `client.chat.completions.create()` with `timeout=5.0` (hardcoded). All other LLM-related configuration (model, base URL, API key, timezone) is already stored in the `settings` DB table and exposed via `GET/PUT /api/settings`. The timeout is the only LLM parameter that isn't configurable.

The frontend settings UI has an "LLM Models" card (`LlmModelSettings.vue`) on the Task Management settings page that handles model selection and saving. The timeout field belongs in this same card.

## Goals / Non-Goals

**Goals:**
- Make the LLM title generation timeout configurable via a DB setting
- Expose the setting in the existing LLM Models settings card
- Use a sensible default (30s) that works for both cloud and local models

**Non-Goals:**
- Making the transcription timeout configurable (separate concern)
- Adding per-model timeout profiles
- Adding a client-level timeout on the AsyncOpenAI instance

## Decisions

### Store timeout as `llm_timeout` in the settings table

Use the existing `settings` key-value table with key `llm_timeout` and a numeric value (seconds). Read it in `generate_title()` using the same pattern as `_get_model()` and `_get_timezone()`.

**Rationale**: Consistent with the existing settings pattern. No migration needed.

### Default to 30 seconds

The current 5s default is too short for local models. A 30s default accommodates cold-start model loading while still failing on genuinely unresponsive services. Users connecting to fast cloud APIs can lower it if they prefer faster fallback.

**Rationale**: 30s is the OpenAI SDK's own default timeout. It's a well-understood baseline.

### Add a number input to the LLM Models settings card

Add a labelled number input below the model selects in `LlmModelSettings.vue`. Save it via `PUT /api/settings` with key `llm_timeout`. The input should have min=1 (seconds) to prevent zero/negative values.

**Rationale**: Keeps all LLM configuration in one place. The input pattern is simple — no dropdown needed for a numeric value.

## Risks / Trade-offs

- [Very large timeout delays error feedback] → The input has a min of 1s. Users who set extremely high values accept the delay. The UI could add guidance text noting that 30s is recommended.
- [Setting doesn't apply to transcription] → Intentional non-goal. Transcription can be addressed separately if needed.
