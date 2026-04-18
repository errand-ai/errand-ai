## MODIFIED Requirements

### Requirement: Frontend test infrastructure
The frontend SHALL have a Vitest test suite using `@vue/test-utils` and `jsdom` 29.x. Tests SHALL mock the API layer (`fetch` or `useApi` composable) to avoid real HTTP requests. The Pinia store SHALL be instantiated fresh for each test using `createTestingPinia` or manual setup.

#### Scenario: Test suite runs without backend
- **WHEN** a developer runs `npm test` in the frontend directory
- **THEN** all tests execute without requiring a running backend or any external service

#### Scenario: Test isolation
- **WHEN** multiple test functions run sequentially
- **THEN** each test starts with a fresh DOM, fresh store state, and fresh mocks
