## 1. Frontend Warning Logic

- [x] 1.1 In `LlmModelSettings.vue`, change the Default Model warning condition from `isReasoningModel() === true` to `isReasoningModel() === false` (explicitly `supports_reasoning: false`, not `null`)
- [x] 1.2 Update the Default Model warning text to: "This is not a reasoning model. Reasoning models are recommended for task processing to support complex workflows and tool calling. Consider using a reasoning model."
- [x] 1.3 Ensure the Title Generation reasoning warning remains unchanged

## 2. Tests

- [x] 2.1 Add test: non-reasoning model selected for Default Model shows the non-reasoning warning
- [x] 2.2 Add test: reasoning model selected for Default Model shows no warning
- [x] 2.3 Add test: unknown model (`supports_reasoning: null`) selected for Default Model shows no warning
- [x] 2.4 Verify existing Title Generation reasoning warning tests still pass
