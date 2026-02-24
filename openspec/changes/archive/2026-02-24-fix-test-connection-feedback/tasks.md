## 1. Setup Wizard — Test Connection Feedback

- [x] 1.1 Add `step2Success` ref and green inline success message to SetupWizard.vue step 2 (displayed when `connectionTested` is true, cleared when `testConnection()` starts)
- [x] 1.2 Change "Test Connection" button text to "Connection Verified" when `connectionTested` is true
- [x] 1.3 Add watchers on `providerUrl` and `apiKey` to clear `connectionTested` and `step2Success` when inputs change

## 2. User Management — OIDC Test Connection Feedback

- [x] 2.1 Add `oidcSuccess` ref and green inline success message to UserManagementPage.vue OIDC section (displayed on successful test, cleared on re-test)
- [x] 2.2 Change OIDC "Test Connection" button text to show "Connection Verified" on success

## 3. Tests

- [x] 3.1 Add SetupWizard.test.ts assertion: after successful test connection, inline success message is visible and button text shows verified state
- [x] 3.2 Add SetupWizard.test.ts assertion: success state clears when provider URL or API key changes
