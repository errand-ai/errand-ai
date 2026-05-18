## Why

The Settings page sidebar (`pages/SettingsPage.vue`) uses a fixed `w-48` (192px) `flex-shrink-0` nav. On a 375px iPhone viewport (minus `<main>` `px-4` padding = 343px usable) the nav + 32px gap takes 224px, leaving ~119px for content. The System Prompt textarea wraps every 2-3 words and Edit/Delete buttons on Task Profile cards get clipped.

The full architectural fix — moving cards into `@errand-ai/ui-components` and gating by capabilities — lands in subsequent phases. This change is the cosmetic stop-gap so admins can use Settings on mobile *now* without waiting for the library migration.

See `ui-components-breakdown.md` (repo root) for the broader plan.

## What Changes

- Replace the fixed `<nav class="w-48 flex-shrink-0">` block in `frontend/src/pages/SettingsPage.vue` with a responsive layout:
  - `< sm` (< 640px): dropdown picker rendered above the content area, listing all settings sections; selecting a section navigates to that route.
  - `≥ sm`: existing sidebar layout unchanged.
- Add a small `SettingsSectionPicker.vue` component local to errand UI for the dropdown (will eventually be replaced by the equivalent in the shared library; intentionally not extracted now to keep the change minimal).

## Capabilities

### Modified Capabilities

- `admin-settings-ui`: Settings page layout adds a responsive nav mode for narrow viewports.

## Impact

- **Frontend only.** No backend changes. No new tests needed beyond a vitest snapshot or render test for the picker.
- **Out of scope**: card-level mobile fixes (textarea overflow, profile card Edit/Delete clipping). Those land alongside Phase 1 when cards move to the library.
