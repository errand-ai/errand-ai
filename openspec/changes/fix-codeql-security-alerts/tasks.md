## 1. Branch & version

- [ ] 1.1 Create feature branch from latest `main` (e.g. `fix-codeql-security-alerts`)
- [ ] 1.2 Bump `VERSION` by a patch level (security hardening, no behaviour change externally visible)

## 2. SPA static serving (cluster 1: alerts #11, #12, #13)

- [ ] 2.1 Add an `SPAStaticFiles` class in `errand/main.py` that subclasses `fastapi.staticfiles.StaticFiles` and overrides `get_response()` to return the response for `index.html` when the base class would return a 404
- [ ] 2.2 Remove the existing `@app.get("/{path:path}") async def spa_fallback(...)` handler from `errand/main.py` (lines ~2500-2507)
- [ ] 2.3 Keep the existing `/assets` mount unchanged (vanilla `StaticFiles`, no fallback), so missing assets return 404
- [ ] 2.4 After all API and auth routes are registered, mount `SPAStaticFiles(directory=STATIC_DIR, html=True)` at `/` with name `"spa"`
- [ ] 2.5 Verify by reading the module that the SPA mount is only registered inside the `if STATIC_DIR.is_dir():` guard

## 3. Static serving tests (cluster 1 coverage)

- [ ] 3.1 Refactor the `static_client` fixture in `errand/tests/test_static_serving.py` so it mounts the production `SPAStaticFiles` class (imported from `main`) against a temporary static directory — remove the inline `@app.get("/static-test/{path:path}")` handler
- [ ] 3.2 Update existing tests in `test_static_serving.py` to hit the real mount path (whatever prefix the fixture uses for isolation) rather than the removed `/static-test/...` prefix
- [ ] 3.3 Update `test_static_dir_not_mounted_when_missing` to assert the presence (or absence) of a mount named `"spa"`, not a route named `spa_fallback`
- [ ] 3.4 Add scenario: `HEAD /tasks/123` returns `200` and `Content-Type: text/html`
- [ ] 3.5 Add scenario: `GET /tasks/abc/` (trailing slash) returns `200` with SPA HTML
- [ ] 3.6 Add scenario: `GET /assets/missing.js` returns `404` (NOT SPA fallback)
- [ ] 3.7 Add scenario: `GET /deep/link/missing.html` returns `200` with SPA HTML
- [ ] 3.8 Add scenario: `GET /%2e%2e/%2e%2e/etc/passwd` does not leak `/etc/passwd` contents
- [ ] 3.9 Add scenario: `GET //etc/passwd` does not leak system files
- [ ] 3.10 Add scenario: `GET /favicon.ico` returns the favicon bytes with an `image/*` Content-Type
- [ ] 3.11 Add scenario: `GET /robots.txt` (fixture provides one) returns `text/plain`
- [ ] 3.12 Add scenario: `GET /.env` and `GET /.git/config` fall back to SPA HTML (no leak)
- [ ] 3.13 Add scenario: `GET /auth/login` continues to hit the auth route (not the SPA mount)
- [ ] 3.14 Run `errand/.venv/bin/python -m pytest errand/tests/test_static_serving.py -v` locally and confirm all green

## 4. LLM provider URL classification (cluster 3: alerts #3, #4, #5)

- [ ] 4.1 In `errand/telemetry.py`, rewrite `classify_provider_url` to parse `base_url` with `urllib.parse.urlparse`, extract `netloc`, strip any userinfo/port, lowercase, and compare against an allowlist of exact hosts (`api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.x.ai`) plus the Ollama localhost forms (`localhost:11434`, `127.0.0.1:11434`)
- [ ] 4.2 Handle malformed URLs gracefully: a URL that raises from `urlparse` or has an empty `netloc` SHALL fall through to the generic categories, not raise to the caller
- [ ] 4.3 Update `errand/tests/test_telemetry.py` scenarios for `classify_provider_url` to reflect host-based matching (existing canonical scenarios keep passing)
- [ ] 4.4 Add a test scenario: `classify_provider_url("https://evil.example.com/api.openai.com/v1", "openai_compatible")` returns `openai-compatible-other` (NOT `openai`)
- [ ] 4.5 Add a test scenario: `classify_provider_url("https://api.openai.com.attacker.example/v1", "openai_compatible")` returns `openai-compatible-other`
- [ ] 4.6 Add a test scenario for a malformed URL (e.g., empty string, missing scheme) returning the appropriate generic category
- [ ] 4.7 Run `errand/.venv/bin/python -m pytest errand/tests/test_telemetry.py -v` locally and confirm all green

## 5. Test URL assertions (cluster 3: alerts #6, #7)

- [ ] 5.1 In `errand/tests/test_integration_routes.py:69`, change `assert "accounts.google.com" in url` to `assert url.startswith("https://accounts.google.com/")`
- [ ] 5.2 In `errand/tests/test_mcp.py:1323`, change `assert "custom.search.com" in call_args.args[0]` to an equivalent `startswith` against the full expected origin (`https://custom.search.com/` or whichever scheme the code uses — confirm from the test setup)
- [ ] 5.3 Run both test files locally and confirm all green

## 6. Slack bot-mention regex (cluster 4: alert #2)

- [ ] 6.1 In `errand/platforms/slack/routes.py:44`, change `_BOT_MENTION_RE` from `r"<@[A-Z0-9]+(?:\|[^>]+)?>\s*"` to `r"<@[A-Z0-9]+(?:\|[^>|]+)?>\s*"`
- [ ] 6.2 Identify the existing test module for Slack routes/events (search under `errand/tests/` for `_BOT_MENTION_RE`, `slack`, or `process_slack_event`); create one if none exists
- [ ] 6.3 Add a regression test: run `_BOT_MENTION_RE.sub("", "<@0|" * 10_000)` and assert it completes within a small wall-clock budget (e.g., 200 ms) using `time.perf_counter()`
- [ ] 6.4 Add positive test: `<@U01ABCDEFGH> hello` strips to `hello`
- [ ] 6.5 Add positive test: `<@U01ABCDEFGH|errand-bot> hello` strips to `hello`
- [ ] 6.6 Run the Slack test module locally and confirm all green

## 7. Workflow permissions (cluster 5: alert #1)

- [ ] 7.1 Audit every job in `.github/workflows/build.yml` and list which ones currently have explicit `permissions:` blocks and which rely on implicit defaults
- [ ] 7.2 Identify which jobs require write access (e.g., GHCR push → `packages: write`; tag push → `contents: write`; OIDC → `id-token: write`)
- [ ] 7.3 Add `permissions: contents: read` at the top level of `.github/workflows/build.yml`, after the `env:` block
- [ ] 7.4 Add or preserve per-job `permissions:` blocks so every job that needs write access declares exactly the scopes it uses (do NOT weaken any existing block)
- [ ] 7.5 Cross-check: the `test` job's existing `contents: read` + `packages: read` block is preserved; the `version` job gets an explicit block if anything beyond `contents: read` is required (it likely doesn't need anything beyond the default)
- [ ] 7.6 If any other workflow files in `.github/workflows/` need the same treatment and the change is small, include them in this PR; otherwise note for a future change

## 8. Local verification (full stack)

- [ ] 8.1 Run `docker compose -f testing/docker-compose.yml up --build` and wait for the app to be healthy on http://localhost:8000
- [ ] 8.2 Open http://localhost:8000/ in a browser; confirm the SPA loads, open DevTools → Network, and confirm no 404s and correct MIME types on bundled assets
- [ ] 8.3 Navigate to a task detail view; copy the deep-link URL; open it in a new tab and hard-refresh; confirm the SPA re-renders the task view (no 404)
- [ ] 8.4 `curl -I http://localhost:8000/` returns `200` with `Content-Type: text/html`
- [ ] 8.5 `curl -I http://localhost:8000/tasks/abc` returns `200` with `Content-Type: text/html`
- [ ] 8.6 `curl -I http://localhost:8000/assets/definitely-does-not-exist.js` returns `404`
- [ ] 8.7 `curl -I http://localhost:8000/api/health` returns `200` with JSON
- [ ] 8.8 `curl http://localhost:8000/../../etc/passwd` does NOT return `/etc/passwd` contents
- [ ] 8.9 `curl http://localhost:8000/%2e%2e/%2e%2e/etc/passwd` does NOT return `/etc/passwd` contents
- [ ] 8.10 `curl http://localhost:8000/.env` and `/.git/config` return the SPA HTML or 404; no repo files leak
- [ ] 8.11 `docker compose -f testing/docker-compose.yml down` to tear down the stack

## 9. Full test suite

- [ ] 9.1 From the repo root, run `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v` and confirm all green (839+ tests)
- [ ] 9.2 From `frontend/`, run `npm test` and confirm all green (440+ tests)

## 10. PR, CI, and CodeQL re-scan

- [ ] 10.1 Commit with a clear message referencing the alert numbers (e.g. "Close CodeQL alerts #1–7, #11–13; cluster 2 dismissed separately")
- [ ] 10.2 Push the branch and open a PR; reference this OpenSpec change in the PR description
- [ ] 10.3 Wait for the PR build to complete; confirm images + Helm chart published to GHCR with the `<VERSION>-pr<N>` tag
- [ ] 10.4 Open the PR's CodeQL scan results and verify alerts #1, #2, #3, #4, #5, #6, #7, #11, #12, and #13 are all closed (resolved or no longer reported); verify no new alerts of the same categories appear
- [ ] 10.5 If any of those alerts persist, revisit the fix (do not dismiss them without strong justification); re-run CodeQL after the new commit
- [ ] 10.6 Deploy the PR build to the Kubernetes cluster (`kubectl` or ArgoCD preview) and confirm pod health + a smoke-test request to `/api/health`

## 11. Merge and production verification

- [ ] 11.1 Merge the PR after green CI + successful PR-build deployment
- [ ] 11.2 Wait for ArgoCD to sync the new main-tagged image
- [ ] 11.3 `curl -I https://content-manager.devops-consultants.net/` returns `200 text/html`
- [ ] 11.4 `curl -I https://content-manager.devops-consultants.net/tasks/<any-real-task-id>` returns `200 text/html` (SPA fallback works through TLS-terminating ingress)
- [ ] 11.5 `curl -I https://content-manager.devops-consultants.net/assets/<an-actual-hashed-bundle-filename>` returns the asset with the correct MIME type
- [ ] 11.6 `curl -I https://content-manager.devops-consultants.net/api/health` returns `200` with the expected JSON body
- [ ] 11.7 Browser: open a real task deep link, refresh, confirm the SPA re-renders the task view
- [ ] 11.8 Confirm GitHub's code-scanning dashboard shows 0 open alerts in the affected categories for this repo (cluster 2 already dismissed; clusters 1, 3, 4, 5 closed)
- [ ] 11.9 Clean up the local branch (`git branch -d fix-codeql-security-alerts` after `git pull`)
