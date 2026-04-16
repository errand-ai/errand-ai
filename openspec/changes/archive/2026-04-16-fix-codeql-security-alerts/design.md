## Context

CodeQL scanning reports 13 alerts on `main`. Three (cluster 2, `py/clear-text-logging-sensitive-data` on `container_runtime.py:371,652,654`) have already been dismissed via the GitHub API with justification "Logs the K8s Secret object name, not secret material" — triggered purely by the variable being named `secret_name`. The remaining 10 alerts are:

- **#11, #12, #13** `py/path-injection` — `errand/main.py:2503-2506`, the SPA fallback handler. The code is already guarded with `Path.resolve()` + `Path.is_relative_to()`, but CodeQL's taint tracking does not follow `is_relative_to()`, so the three taint-sink lines stay flagged.
- **#3, #4, #5** `py/incomplete-url-substring-sanitization` — `errand/telemetry.py:204,206,208`, `classify_provider_url` uses `"api.openai.com" in url_lower` to bucket provider URLs. The function is telemetry-only (no authorisation effect), but the analyser cannot prove that.
- **#6, #7** same rule in test assertions (`accounts.google.com`, `custom.search.com`).
- **#2** `py/polynomial-redos` — `errand/platforms/slack/routes.py:184`, `_BOT_MENTION_RE.sub(...)` called on attacker-controlled Slack message text. The regex `<@[A-Z0-9]+(?:\|[^>]+)?>\s*` is not obviously catastrophic, but the `[^>]+` can be flagged as ambiguous.
- **#1** `actions/missing-workflow-permissions` — `.github/workflows/build.yml` has no top-level `permissions:` block. Some jobs (e.g. `test`, build) already declare explicit permissions; others inherit the repository default, which is broader than needed.

The existing static-serving test suite (`errand/tests/test_static_serving.py`) has nine scenarios that cover the relevant behaviours — but its fixture **reimplements** the SPA handler inline instead of exercising the production wiring, so it will not catch behavioural drift introduced by the planned swap.

**Constraints**

- The Vue SPA relies on deep-link refresh: a hard-refresh on `/tasks/abc` must serve `static/index.html` so Vue Router resolves the route client-side.
- The PR CodeQL scan is the objective signal for whether the analyser is satisfied. A clean PR scan is a release gate for this change.
- `testing/docker-compose.yml` is the only supported local verification path for frontend + backend integration.
- Sequential development applies (per `CLAUDE.md`); this change lands before the six other in-progress changes per user direction.

## Goals / Non-Goals

**Goals:**

1. Close CodeQL alerts #1–7 and #11–13 at source so the PR scan shows zero remaining open alerts in these clusters.
2. Preserve SPA deep-link behaviour end-to-end (browser refresh on any non-asset path still serves `index.html`).
3. Make `/assets/*` misses fail loudly with a 404 so the browser can surface missing-bundle bugs immediately, matching user direction.
4. Convert the static-serving test fixture to exercise the production wiring so the existing nine tests become a real safety net, not a parallel reimplementation.
5. Harden the Slack regex against the specific ReDoS pattern CodeQL identified and add a regression test with a pathological input.
6. Apply GitHub Actions least-privilege (`contents: read` at workflow level, explicit per-job overrides only where needed), without weakening any existing job's permissions.

**Non-Goals:**

- Broader security review beyond the CodeQL queue (authz, secret rotation, dependency CVEs, etc.).
- Changes to the CodeQL configuration, query set, or ruleset.
- Re-reviewing cluster 2: already dismissed with justification; no code change.
- Refactoring the Slack event pipeline beyond the regex. Other Slack-routed alerts are out of scope.
- Rewriting the telemetry classifier's categories or output shape.

## Decisions

### D1. Replace custom SPA handler with `SPAStaticFiles` subclass

**Chosen approach:** define a `SPAStaticFiles(StaticFiles)` subclass in `errand/main.py` (or a small new module) that overrides `get_response()`. On a 404 from the parent class, it returns the response for `index.html` instead; other statuses pass through. Mount it at `/` with `html=True`. Keep the existing `/assets` mount as vanilla `StaticFiles` (no fallback) so that missing assets return 404.

**Why**
- Starlette/FastAPI's `StaticFiles` has been hardened against path traversal for years; delegating path handling moves the taint path out of our code and closes CodeQL's concern without needing suppression comments.
- The separation of the `/assets` mount (404 on miss) from the root `/` mount (SPA fallback) matches the user-directed routing design: assets fail loudly, navigation paths fall back gracefully.
- `html=True` on the root mount handles directory-request semantics (e.g. `/` → `index.html`) cleanly.

**Alternatives considered**
- *Keep the handler, rewrite to a CodeQL-recognised pattern* (e.g. explicit `os.path.commonpath` check, or reject `..` components before `resolve()`). Workable but fragile — what CodeQL accepts changes over time and varies across rulesets.
- *Suppress with a CodeQL comment.* Fast but accumulates tech debt; the underlying concern (hand-rolled path handling) persists and future changes could reintroduce real risk.
- *Use Starlette's `Route(path="/{path:path}", ...)` with a whitelist regex for `path`.* Possible, but duplicates what `StaticFiles` already does and leaves us maintaining a whitelist.

### D2. Ordering of root `/` mount vs API/auth routes

**Chosen approach:** mount `SPAStaticFiles` at `/` *after* all API and auth routes are registered. FastAPI/Starlette matches routes in registration order, so API routes (`/api/*`, `/auth/*`, `/mcp/*`, `/slack/*`, `/metrics/*`) resolve first; only requests that miss all of those fall through to the SPA mount.

**Why**
- This preserves the current "API routes unaffected" invariant (covered by `test_api_routes_unaffected` and `test_api_tasks_unaffected`).
- Mounting `StaticFiles` at `/` is a well-known way to capture everything-else; ordering is the sole safeguard against it swallowing API routes.

**Alternatives considered**
- *Explicit prefix exclusions inside `SPAStaticFiles.get_response()`.* Overcomplicates the subclass and introduces a second source of truth for which prefixes are API.
- *Keep the catch-all `@app.get("/{path:path}")` and only change its body.* Leaves the taint-path issue alive; the whole point is to delegate.

### D3. `classify_provider_url` — host-based allowlist

**Chosen approach:** parse the input with `urllib.parse.urlparse`, extract `netloc` (strip credentials/port), lowercase, and compare against a fixed allowlist of exact hosts (`api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.x.ai`) plus the localhost forms for Ollama.

**Why**
- Eliminates the substring-anywhere taint: a malicious URL like `https://evil.example.com/api.openai.com/fake` has netloc `evil.example.com` and falls through to the default category.
- Matches the intent of the function (bucketing known providers) without adding complexity.
- Closes CodeQL's `py/incomplete-url-substring-sanitization` warning because the host check is specific, not substring-based.

**Alternatives considered**
- *`netloc.endswith(".openai.com")`.* More permissive (would match `api-experimental.openai.com`), but the existing scenarios match exact hosts, so tighter is better.
- *Leave the substring checks and suppress.* Keeps the weakness even if it is non-exploitable; no reason to retain it.

**Observable behaviour change**: URLs where the well-known host appears in the *path or query* rather than the authority now classify differently. This is correct: those URLs were never actually an OpenAI/Anthropic/etc. endpoint.

### D4. Test URL assertions — `startswith` on full origin

**Chosen approach:** tighten `"accounts.google.com" in url` (and the `custom.search.com` test) to `url.startswith("https://accounts.google.com/")` (adjust origin as appropriate per test). Preserves the intent of each test (the URL really does go to the expected host) while satisfying CodeQL.

**Why**
- Same reasoning as D3: pinning to the origin, not a substring, is both more correct and CodeQL-compatible.
- Pure test-code change; no production code touched.

### D5. Slack regex tightening

**Chosen approach:** change `_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]+)?>\s*")` → `r"<@[A-Z0-9]+(?:\|[^>|]+)?>\s*"`. Add a regression test that runs `.sub()` against a pathological input (e.g. `"<@0|" * 10_000`) with no terminating `>` and asserts completion within a small wall-clock budget (e.g. 200 ms) to catch future regressions.

**Why**
- Excluding `|` from the label class more accurately reflects Slack's actual mention syntax (`<@USERID|label>` where `|` is a field separator, not valid inside the label) and narrows the ambiguity CodeQL flagged.
- A wall-clock regression test guards against future regex edits reintroducing the pattern.

**Alternatives considered**
- *Replace regex with a manual scanner.* Over-engineering for a 30-character pattern.
- *Cap input length before running the regex.* Defence in depth worth considering but not the root cause; keep the regex correct.

### D6. Workflow permissions — top-level `contents: read`, explicit overrides

**Chosen approach:** add `permissions: contents: read` at the top of `.github/workflows/build.yml`. Audit every job; add explicit per-job blocks only where write access is required (e.g. GHCR push → `packages: write`; any OIDC exchange → `id-token: write`; any job that pushes branches/tags → `contents: write`). Do not weaken any existing block.

**Why**
- Top-level least-privilege is the CodeQL-recommended pattern; per-job overrides make intent explicit at the point of use.
- Keeping existing stronger permissions intact ensures no regression in the build/push path.

**Alternatives considered**
- *Only add per-job blocks with no top-level default.* Leaves any un-audited job inheriting the broader default; CodeQL would still flag.
- *Apply the same tightening to other workflow files.* If other workflow files exist and are not flagged, out of scope for this change; revisit if CodeQL picks them up later.

### D7. Test fixture: exercise real wiring, not a replica

**Chosen approach:** refactor `errand/tests/test_static_serving.py` so the fixture imports and mounts the production `SPAStaticFiles` against a temporary static directory. Update `test_static_dir_not_mounted_when_missing` to check for the `spa` mount by name (the `spa_fallback` named route disappears with this change). The existing nine scenarios keep their assertions.

**Why**
- The current fixture silently duplicates the handler. After the swap it would no longer match production, giving false green. Refactoring forces the fixture to stay in sync with whichever mechanism is live.

## Risks / Trade-offs

- **Risk: `StaticFiles(html=True)` has subtle semantics we haven't pinned down (e.g. directory with trailing slash, HEAD method, Content-Type on edge-case files).** → Mitigation: the expanded test suite (new scenarios for HEAD, trailing slash, URL-encoded traversal, Content-Type on root files) pins these behaviours before merge. Any unexpected behaviour surfaces in tests, not prod.
- **Risk: Missing-asset returning 404 is a behaviour change for clients that previously relied on getting `index.html` back.** → Mitigation: this is the user-directed design goal, not an accident. Documented in proposal. In practice the existing handler's fallback for missing assets was almost always a bug-masking behaviour (serving HTML when JS was expected), so hardening here is a net improvement. Production verification step catches regressions in actual asset paths.
- **Risk: Workflow permissions change breaks a build/push job that was relying on an implicit permission.** → Mitigation: audit every job before writing the permissions block; explicit overrides are additive to the top-level default. First PR build run is the forcing function — if something breaks, we see it before merge.
- **Risk: `classify_provider_url` change reclassifies some previously-"matched" telemetry rows to `other`.** → Mitigation: the affected rows were URLs where the well-known host appeared outside the authority, which is exactly the mis-classification we're fixing. Update the classifier's tests to pin the new semantics (add a scenario where a malicious-path URL lands in `other`).
- **Risk: Slack regex edit changes behaviour for real mentions containing `|`.** → Mitigation: `|` is already a field separator in Slack's mention syntax and not valid inside a label. Existing mention scenarios should keep passing. If a real Slack payload surfaces an edge case, we learn in the smoke test.
- **Risk: The PR CodeQL scan still flags one of these alerts even after the fix (analyser imperfect).** → Mitigation: treat as a discovery during the PR. Either refine the fix or dismiss with justification at that point. Do not merge until the queue is as expected.

## Migration Plan

No data migration, no config change, no ordering constraint on deploy. Standard flow:

1. Feature branch, patch-level bump of `VERSION`, PR.
2. CI (including CodeQL) runs; verify alerts #1–7 and #11–13 close on the PR and no new alerts appear.
3. Local verification: `docker compose -f testing/docker-compose.yml up --build`, walk through the SPA, refresh on deep links, curl missing asset, curl adversarial paths. See `tasks.md` for the exact checklist.
4. Merge after CI green + deployment validation on Kubernetes (per `CLAUDE.md` PR workflow).
5. ArgoCD syncs the main image. Run production verification (curl + browser deep-link refresh).

Rollback: revert the PR. No forward migrations to undo.

## Open Questions

- Is there anything else in `.github/workflows/` that should get the same permissions treatment in this change? If other workflow files exist (`dependabot.yml`, `release.yml`, etc.), CodeQL would have flagged them — but if we spot something obvious during the audit, small extra fixes in the same PR are cheap. Decide during implementation.
- Does Starlette's `StaticFiles` emit the exact same `Content-Type` for `favicon.ico` as the current `FileResponse`-based handler? Expected yes (both rely on `mimetypes`), but the new Content-Type test scenario will confirm.
