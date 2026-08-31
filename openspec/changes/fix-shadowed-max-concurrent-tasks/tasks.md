## 1. Remove the chart default

- [x] 1.1 Delete `server.maxConcurrentTasks: 3` from `helm/errand/values.yaml`
- [x] 1.2 Confirm `helm/errand/templates/server-deployment.yaml` still guards the env var with `{{- if .Values.server.maxConcurrentTasks }}` and emits nothing when unset
- [x] 1.3 Document the value in the chart README / values comments as an optional operator override that makes the setting readonly in the UI
- [x] 1.4 Verify no values file in `~/github/argocd` (`errand-rancher`, `errand-cloud`, `errand-sh`) sets `server.maxConcurrentTasks`; if any does, decide with the operator whether to keep the pin

## 2. Make the refusal observable in the API

- [x] 2.1 In `errand/main.py` `update_settings`, log a WARNING when a key is skipped for being env-sourced, naming both the setting key and `meta["env_var"]`
- [x] 2.2 Confirm the response still returns `resolve_settings(session)` unchanged in shape, with refused keys carrying `source: "env"` and `readonly: true`
- [x] 2.3 Confirm editable keys sent in the same request body are still persisted (no early return / no exception path)

## 3. Tests

- [x] 3.1 Chart test: rendering with default values emits no `MAX_CONCURRENT_TASKS` env var on the server Deployment
- [x] 3.2 Chart test: `server.maxConcurrentTasks: 5` still emits `MAX_CONCURRENT_TASKS=5`
- [x] 3.3 API test: PUT of an env-shadowed key does not write a `settings` row and returns that key as `readonly: true`, `source: "env"`
- [x] 3.4 API test: a request mixing an editable key and an env-shadowed key returns 200, persists the editable key, and refuses the other
- [x] 3.5 API test: the WARNING is emitted once per refused key (assert via `caplog`)
- [x] 3.6 Run the errand suite: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -q`

## 4. Verify end to end

- [x] 4.1 Bump `VERSION` (patch)
- [x] 4.2 `docker compose -f testing/docker-compose.yml up --build` — compose sets no `MAX_CONCURRENT_TASKS`, so confirm the field saves and persists across a page reload
- [ ] 4.3 Push, open PR, confirm CI builds images + chart
- [ ] 4.4 Deploy the PR build to Kubernetes and confirm `GET /api/settings` reports `max_concurrent_tasks` with `source: "database"` (or `"default"`) and `readonly: false`
- [ ] 4.5 Change the value in the UI and confirm the task manager picks it up on the next poll cycle without a restart (look for `Updating max_concurrent_tasks: 3 -> N (source=database)` in the server log)

## 5. Archive

- [ ] 5.1 `openspec archive fix-shadowed-max-concurrent-tasks -y` and commit the flattened specs in this PR
- [ ] 5.2 Re-verify the post-archive build deploys cleanly (archiving produces a new image tag)

## Post-merge notes

- Merge the PR once the post-archive build is verified.
- The settings card still renders an editable input for keys the API reports as
  `readonly: true`. That is tracked as `surface-readonly-settings` in
  `errand-ai/errand-component-library`; it consumes the response contract locked
  by section 2 and needs a `@errand-ai/ui-components` release plus a version bump
  in `frontend/package.json` here.
