## Why

Adopting the shared `@errand-ai/ui-components` settings cards (Wave 1 #203, Wave 2 #206) regressed several settings pages: the Agent Configuration, Task Management, and Integrations pages no longer populate saved values, render raw JSON envelopes in textareas, throw `Unexpected token '<'` errors, and have inconsistent spacing between cards. Investigation (code + Grafana production logs + live API + live browser on the local stack) traced this to two independent contract mismatches between the errand backend and the shared library, plus pre-existing plugin/marketplace backend fragility surfaced in the same views.

This change covers the **errand-backend** side. The library-side defects (settings-envelope unwrap, card spacing, and the Jira `direct.ts` path) are fixed in a companion change in the component-library repo: `errand-component-library` change `fix-settings-cards-envelope-and-spacing`. This change depends on that release and bumps to it.

## What Changes

- **Implement the cloud-storage & Google Workspace REST surface (backend).** On a standalone errand-server the library's `CloudStorageCard` and `GoogleWorkspaceCard` call `/api/cloud-storage/{status,authorize}` + `DELETE /api/cloud-storage` and `/api/google-workspace/{status,authorize}` + `DELETE /api/google-workspace`, which errand does not implement (only `/api/onedrive/refresh-token` and `/api/google/refresh-token` exist). Requests fall through to the SPA catch-all (`index.html`) → `Unexpected token '<', "<!DOCTYPE"` (confirmed live: `/api/cloud-storage/status` → 200 text/html). errand will implement these endpoints, returning the library's typed shapes (`CloudStorageStatus` = `{connected, provider?, account?, authorize_url?}`, `CloudStorageAuthorizeResponse` = `{authorize_url}`, and the `GoogleWorkspaceStatus`/authorize equivalents), wired to the existing OneDrive/cloud-storage and Google Workspace machinery. Capability advertisement (`cloud_storage`, `google_workspace`) will be reconciled with the endpoints so a card only renders when its backend surface is present.
- **Plugin/marketplace 500 robustness (backend).** `GET /api/plugins` 500s with `FileNotFoundError: .../plugins/installed/anthropics_claude-plugins-official/code-review/latest` (reproduced locally), and marketplace resync fails with `PluginInstallError: relative plugin path does not exist: .../plugins/code-review` (and upstream `git clone failed`). Missing/partially-synced plugin state will degrade gracefully (skip + surface a per-marketplace error) instead of returning 500, and resync failures will be reported without corrupting the listing.
- **Dependency + version bumps.** errand bumps `@errand-ai/ui-components` to the companion release (envelope unwrap + spacing + Jira path) and its `VERSION`.

## Capabilities

### New Capabilities
- `cloud-storage-rest-api`: errand-server SHALL expose `/api/cloud-storage/{status,authorize}` and `DELETE /api/cloud-storage` returning the library's `CloudStorageStatus`/`CloudStorageAuthorizeResponse` shapes, wired to the OneDrive/cloud-storage machinery.
- `google-workspace-rest-api`: errand-server SHALL expose `/api/google-workspace/{status,authorize}` and `DELETE /api/google-workspace` returning the library's `GoogleWorkspaceStatus`/authorize shapes, wired to the Google Workspace machinery.

### Modified Capabilities
- `plugin-management`: `GET /api/plugins` MUST NOT 500 when an installed-plugin directory is missing; it MUST degrade gracefully.
- `plugin-marketplaces`: marketplace resync MUST report install/clone failures per-marketplace without breaking the plugins listing.

## Impact

- **errand (this repo):**
  - Backend: implement cloud-storage + google-workspace REST endpoints (new routes wired to `errand/onedrive_routes.py`/`cloud_storage`/`errand/google_routes.py` machinery); reconcile `get_capabilities()` (`capabilities.py`) so `cloud_storage`/`google_workspace` are advertised only when the surface is available; harden `errand/plugin_routes.py` + plugin install/sync (`plugin_marketplace`).
  - Frontend: bump `@errand-ai/ui-components` in `frontend/package.json`; adjust any tests asserting the old (broken) behavior.
  - `VERSION` bump (minor — user-visible fixes + new endpoints).
- **Companion change (`errand-component-library` → `fix-settings-cards-envelope-and-spacing`):** settings cards unwrap the `{value, ...}` envelope; `SettingsShell`/`SettingsCard` spacing; `createDirectApi` Jira path corrected to `/api/credentials/jira`; publishes the new `@errand-ai/ui-components` version this change depends on.
- **errand-cloud (separate repo):** bumps `@errand-ai/ui-components` to the same release; its `createCloudApi` Jira proxy path (`/api/proxy/jira/credentials`) will need correcting to `/api/proxy/credentials/jira` in its own repo (noted, out of scope here). Cloud-storage/google-workspace proxy paths already match the new errand endpoints.
- **Not in scope / follow-up:** the intermittent shared-workspace 500 (`rclone rc 5572/config/update`) is transient (health is 200 now); tracked as an observation, not fixed here unless design surfaces a cheap guard.
