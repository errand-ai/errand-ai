## 1. Docker & CI — Bake version into image

- [x] 1.1 Add `ARG APP_VERSION="dev"` and `ENV APP_VERSION=$APP_VERSION` to Dockerfile (in the final stage)
- [x] 1.2 Update `build-errand` step in `.github/workflows/build.yml` to pass `--build-arg APP_VERSION=${{ needs.version.outputs.tag }}` via the `build-args` input
- [x] 1.3 Optionally pass `APP_VERSION` in `docker-compose.yml` build args (from VERSION file or default `dev`)

## 2. Backend — Version checker module

- [x] 2.1 Create `errand/version_checker.py` with: `APP_VERSION` read from env, GHCR token exchange, tag list fetch, pre-release filtering (`-pr\d+$`), semver comparison, cached latest version state
- [x] 2.2 Implement `run_version_checker()` async loop: check on startup, then every 15 minutes; log warnings on GHCR errors; update cached state on success
- [x] 2.3 Implement `get_version_info()` function returning `{current, latest, update_available}` from cached state

## 3. Backend — API endpoint

- [x] 3.1 Add `GET /api/version` endpoint in `errand/main.py` that calls `get_version_info()` and returns the result (no auth required)
- [x] 3.2 Launch `run_version_checker()` as a background task in the lifespan (alongside scheduler, zombie cleanup, etc.) and cancel on shutdown

## 4. Frontend — Version display

- [x] 4.1 Add version fetch on app mount in `App.vue`: call `GET /api/version`, store response in reactive state
- [x] 4.2 Add version text element in the header (left of GitHub link): display `v{current}` in muted style, or `dev` without prefix for non-semver
- [x] 4.3 Add update indicator: colored dot next to version text when `update_available` is true, with tooltip showing `v{latest} available`
- [x] 4.4 Handle fetch failure gracefully: hide version area entirely if the API call fails

## 5. Tests

- [x] 5.1 Backend tests for `version_checker.py`: tag filtering, semver comparison, dev version handling, GHCR error handling (mock httpx)
- [x] 5.2 Backend test for `GET /api/version` endpoint: returns expected shape, works without auth
- [x] 5.3 Frontend tests for version display: renders version text, shows/hides update dot based on API response, handles fetch failure
