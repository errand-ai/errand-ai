## 1. Add submitting state and disable form inputs

- [x] 1.1 Add `submitting` ref<boolean> to TaskForm.vue and set it to `true` at the start of `submit()`, `false` in a `finally` block
- [x] 1.2 Bind `:disabled="submitting"` on the text input, submit button, and voice input microphone button
- [x] 1.3 Add Tailwind disabled styling (`disabled:opacity-50 disabled:cursor-not-allowed`) to the text input, submit button, and voice input button

## 2. Tests

- [x] 2.1 Add test: inputs are disabled during submission and re-enabled after success
- [x] 2.2 Add test: inputs are re-enabled after failed submission and error is displayed
- [x] 2.3 Add test: rapid double-submit only creates one task
