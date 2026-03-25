## Why

The Default Model setting controls which LLM the task-runner uses for complex workflows, tool calling, and multi-step reasoning. Non-reasoning models lack the extended thinking capabilities needed for reliable task execution. The settings page already warns when a reasoning model is selected for title generation (where it's a poor fit), but doesn't warn when a non-reasoning model is selected as the default — the inverse problem.

## What Changes

- Add an informational warning on the Default Model selector when the selected model does **not** support reasoning
- The warning text explains that reasoning models are recommended for task processing due to complex workflow and tool-calling requirements
- Warning only appears when `supports_reasoning` is explicitly `false` (not when `null`/unknown)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `llm-provider-settings-ui`: Add non-reasoning warning to the Default Model selector

## Impact

- **Frontend**: `LlmModelSettings.vue` — add conditional warning below Default Model dropdown
- **Tests**: Update `SettingsPage.test.ts` to cover the new warning
- No backend changes required — `supports_reasoning` metadata is already available from the model metadata registry
