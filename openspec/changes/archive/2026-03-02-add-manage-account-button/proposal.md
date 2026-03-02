## Why

When connected to Errand Cloud, there is no way to navigate to the cloud account management portal from the settings page. Users need a quick link to manage their subscription, view connection history, and configure their account at https://errand.cloud.

## What Changes

- Add a "Manage Account" button to the connected state in the Cloud Service settings page that opens https://errand.cloud in a new tab

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `cloud-settings-ui`: Add a "Manage Account" link to the connected state

## Impact

- `frontend/src/pages/settings/CloudServicePage.vue` — Add button to connected-state template block
- `frontend/src/pages/settings/__tests__/CloudServicePage.test.ts` — Add test for new button
