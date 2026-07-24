## 1. Cloud storage REST surface

- [x] 1.1 Add `GET /api/cloud-storage/status` returning `CloudStorageStatus` `{connected, provider?, account?, authorize_url?}`, wired to the existing cloud-storage/OneDrive machinery (`integration_routes` onedrive provider); ensure `application/json` always.
- [x] 1.2 Add `POST /api/cloud-storage/authorize` returning `{authorize_url}` initiating the connection flow (re-keys the machinery's `redirect_url`).
- [x] 1.3 Add `DELETE /api/cloud-storage` (idempotent, 204) removing the stored connection.
- [x] 1.4 Unit/integration tests asserting each endpoint's status code, JSON content-type, and response shape (connected + not-connected + idempotent-delete). — `tests/test_cloud_storage_google_routes.py`

## 2. Google Workspace REST surface

- [x] 2.1 Add `GET /api/google-workspace/status` returning `GoogleWorkspaceStatus` `{connected, email?, scopes?}`, wired to `integration_routes` google_drive provider; `application/json` always.
- [x] 2.2 Add `POST /api/google-workspace/authorize` returning `{redirect_url}` for the top-level OAuth redirect.
- [x] 2.3 Add `DELETE /api/google-workspace` (idempotent, 204).
- [x] 2.4 Tests for status (connected/not), authorize URL, and idempotent delete + JSON content-type.

## 3. Capability reconciliation

- [x] 3.1 Two parts. (a) The `/api/cloud-storage/*` and `/api/google-workspace/*` status endpoints are registered **unconditionally**, so whenever the capability is advertised the status call resolves to real JSON (never the SPA catch-all). (b) Capability gating is **availability-aware**: `cloud_storage`/`google_workspace` are advertised when the provider is connectable via local OAuth client credentials **or a connected errand-cloud OAuth proxy** (plus any required MCP URL), or is already connected — this makes the cards appear on cloud-connected deployments (which use the proxy, not local client id/secret). An earlier iteration kept the plain `ONEDRIVE_MCP_URL` / `GOOGLE_CLIENT_ID`+`SECRET` env gates; that was superseded by the availability-aware gate in `capabilities.py`.
- [x] 3.2 Tests: capability present ⇒ `status` endpoint returns 200 JSON (`test_cloud_storage_google_routes.py::test_*_capability_implies_working_status`).

## 4. Plugin listing robustness (`GET /api/plugins`)

- [x] 4.1 In `errand/plugin_routes.py`, `_serialize_plugin` now degrades gracefully when the on-disk tree is missing/unreadable (empty skills/MCP + `load_error` flag, warning logged); `list_plugins` adds a per-plugin backstop so no single plugin can 500 the listing.
- [x] 4.2 Regression test reproducing the `FileNotFoundError` on a missing `.../installed/<marketplace>/<plugin>/latest` path → `_serialize_plugin` returns a degraded entry with `load_error` (`test_plugin_routes.py::test_serialize_plugin_degrades_on_missing_ondisk`).

## 5. Marketplace sync/resync robustness

- [x] 5.1 `sync_marketplace` already captured all failures into `last_sync_status="error"` (so resync never 500s). Added a `RuntimeError` branch categorizing fetch-layer failures — `git clone failed` and disallowed-scheme rejections now get a clean, actionable `last_sync_error` instead of the generic "unexpected error (see server logs)". Detail (which may contain URLs) stays in logs.
- [x] 5.2 Listing survives a failed resync: `sync_marketplace` only mutates sync-status fields (never installed plugins), and `GET /api/plugins` is now robust to missing on-disk state (task 4). `GET /api/marketplaces/{id}/plugins` was already guarded with `.is_dir()`/`.is_file()` checks.
- [x] 5.3 Test: git-clone-failure captured and categorized, not raised (`test_plugin_marketplace.py::test_sync_marketplace_git_clone_failure_categorized`). (The `PluginInstallError: relative plugin path` case originates in `install_plugin`, a separate flow already handled by `install_plugin_endpoint`'s `except PluginInstallError`, not by resync.)

## 6. Dependency & version bump

- [x] 6.1 Bumped `@errand-ai/ui-components` `^0.10.0` → `^0.11.0` in `frontend/package.json`; `npm install` updated the lockfile. Companion library change was already published as v0.11.0; installed dist verified to contain `extractSettingValue`, `/credentials/jira`, and the `settings-content` spacing slot.
- [x] 6.2 Frontend test suite green with 0.11.0 (261 passed) — no tests asserted the old behavior (envelope handling lives in the library), so no fixes were needed.
- [x] 6.3 Bump `VERSION` (minor) → `0.133.0`. (Subsequently advanced within the same PR as follow-up config-tab fixes were added and deployed via CI/ArgoCD — see the `VERSION` file for the current release number.)

## 7. Verification (local docker-compose + Playwright)

- [x] 7.1 Confirmed live (rebuilt container + Playwright, 0.11.0 frontend): System prompt shows its stored value, MCP servers textarea has no envelope keys (`source`/`sensitive` gone), and all card gaps are a uniform 24px (was 0/24/0/0/24).
- [x] 7.2 Confirmed live (rebuilt container + Playwright): Integrations → Cloud storage shows "Not connected" (no `Unexpected token '<'`); `/api/cloud-storage/status` + `/api/google-workspace/status` return 200 `application/json`.
- [x] 7.3 Confirmed live: `GET /api/plugins` returns 200; git-clone sync failures surface a clean inline error (no 500). Degradation covered by unit tests.
- [x] 7.4 Backend: full errand suite green (1775 passed). Frontend test suite deferred to 6.2 (no frontend changes in this change until the dep bump).
