## Why

GitHub's CodeQL code scanning has 13 open alerts against the repository. Three of them (cluster 2 — clear-text logging of `secret_name` in `container_runtime.py`) have already been dismissed as false positives: the variable holds a Kubernetes Secret *object name*, not secret material. The remaining 10 alerts span real hardening opportunities that are each small individually but worth addressing together so the security-scanning dashboard reaches a clean state and future regressions stand out clearly.

## What Changes

Four clusters of fixes, plus a workflow hardening, all in one change.

- **Path handling for SPA serving** (alerts #11, #12, #13): replace the custom `spa_fallback` route in `errand/main.py` with an `SPAStaticFiles` subclass of `StaticFiles` that falls back to `index.html` on 404. Path handling is delegated to the hardened library, closing the taint path CodeQL flags in the custom handler. **Observable behaviour change**: requests under `/assets/*` that do not resolve to a file now return **404** (not SPA fallback), so the browser fails loudly on missing JS/CSS. SPA deep-link fallback is preserved for all other paths.
- **LLM provider URL classification** (alerts #3, #4, #5): in `errand/telemetry.py`, `classify_provider_url` SHALL match against the parsed URL host rather than substring containment. **Observable behaviour change**: URLs like `https://evil.example.com/api.openai.com/fake` that previously classified as `openai` now classify as `other` (or their true host). This affects telemetry categorisation only, not authorisation.
- **URL assertions in tests** (alerts #6, #7): tighten substring-based URL assertions in `errand/tests/test_integration_routes.py` and `errand/tests/test_mcp.py` to `startswith` against the full origin. Implementation-only; no spec behaviour changes.
- **Slack bot-mention regex** (alert #2): tighten `_BOT_MENTION_RE` in `errand/platforms/slack/routes.py` to exclude `|` from the inner character class (more accurately reflects Slack's mention format and removes the polynomial-ReDoS warning). Add a regression test with a pathological input that asserts the regex completes within a time budget.
- **GitHub Actions least-privilege** (alert #1): add top-level `permissions: contents: read` to `.github/workflows/build.yml` and explicit per-job overrides wherever write access is needed (GHCR push, OIDC token, etc.). No existing permission SHALL be weakened.

Out of scope:
- Cluster 2 (alerts #8, #9, #10): already dismissed as false positive via GitHub API; no code change.
- Broader security posture review beyond the CodeQL queue.
- Changes to CodeQL configuration or query set.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `static-file-serving`: SPA fallback mechanism changes implementation (custom handler → `SPAStaticFiles` subclass) and the missing-asset scenario becomes a hard 404 rather than an SPA fallback.
- `telemetry-llm-config`: provider URL classification becomes host-based rather than substring-based; scenarios must reflect the stricter matching.
- `slack-mention-events`: bot-mention stripping regex becomes resilient to pathological inputs; add a scenario that asserts this.
- `ci-pipelines`: CI workflow SHALL follow least-privilege permissions for `GITHUB_TOKEN`.

## Impact

- **Code**: `errand/main.py` (SPA route), `errand/telemetry.py` (classifier), `errand/platforms/slack/routes.py` (regex), `errand/tests/test_static_serving.py` (fixture refactor + new scenarios), `errand/tests/test_integration_routes.py` and `errand/tests/test_mcp.py` (assertion tightening), `errand/tests/test_telemetry.py` (classifier scenarios), `errand/tests/test_platforms_slack.py` or equivalent (ReDoS regression test), `.github/workflows/build.yml` (permissions block).
- **APIs**: No external API surface change. HTTP responses for missing `/assets/*` paths change from HTML (200) to 404 — a behavioural change for any client that currently relies on this.
- **Dependencies**: None added or removed.
- **CI/CD**: CodeQL scan on the PR MUST show alerts #1–7 and #11–13 closed; no new alerts introduced.
- **Deployment**: Patch-level version bump. No migration, no config change. ArgoCD sync is routine.
- **Security scanning dashboard**: Goes from 10 open high/medium alerts to 0 (dismissed cluster 2 already accounted for).
