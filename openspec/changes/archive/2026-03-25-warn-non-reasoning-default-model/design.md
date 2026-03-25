## Context

The LLM Models settings page has three model selectors. The existing reasoning model warning logic treats Title Generation and Default Model (Task Processing) identically — warning when a reasoning model is selected. However, the Default Model powers the task-runner which benefits from reasoning capabilities for complex workflows and tool calling. The warning logic should be inverted for the Default Model: warn when a non-reasoning model is selected.

## Goals / Non-Goals

**Goals:**
- Warn admins when the Default Model lacks reasoning support
- Keep the existing reasoning warning for Title Generation unchanged

**Non-Goals:**
- Changing backend model metadata detection
- Adding reasoning warnings to the Transcription Model selector
- Blocking model selection — warnings are informational only

## Decisions

**Invert the warning condition for Default Model**: Instead of checking `isReasoningModel() === true`, check `isReasoningModel() === false` (explicitly `supports_reasoning: false`). When `null`/unknown, no warning is shown — consistent with the existing approach of only warning on definitive metadata.

**Different warning text**: The Default Model warning uses different copy than the Title Generation warning, explaining that reasoning models are recommended for task processing workflows.

**Same styling**: Use the same amber warning style (`text-amber-600 bg-amber-50 border-amber-200`) for visual consistency.

## Risks / Trade-offs

- [Users may ignore the warning] → Informational only, no enforcement — matches existing pattern
- [Model metadata may be unknown (`null`)] → No warning shown for unknown models, avoiding false positives — same approach as existing title generation warning
