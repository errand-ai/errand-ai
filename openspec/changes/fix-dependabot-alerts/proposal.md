## Why

GitHub Dependabot has 27 open alerts against this repository's dependency manifests (8 in `errand/requirements*.txt`, 19 in `frontend/package*.json`). A per-alert exposure review shows 2 of 27 hit real code paths in this codebase — both are XSS-class vulnerabilities in `dompurify`'s default `sanitize()` call, which is used to render LLM-generated task output in the `TaskOutputModal`. The remaining 25 alerts are mitigated by one of: our usage not passing the vulnerable options (ADD_TAGS-as-function, ADD_ATTR predicate, USE_PROFILES in `dompurify`; non-default parser config in `python-multipart`); the vulnerable primitive not being used (SECT elliptic curves, peer TLS name constraints in `cryptography`); the dependency being build-time only (`picomatch` via Tailwind's `chokidar`/`fast-glob`); or the dependency being development-only (`vite`, `undici`, `rollup`, `esbuild`, `minimatch`, `pytest`).

Low exploitability does not mean the alerts should be ignored. A noisy security-scanning dashboard trains everyone to filter it out — closing the backlog with a small set of version bumps keeps future alerts high-signal. The runtime alerts additionally expose risk through LLM-supplied content (task output rendered by `TaskOutputModal`) which must be treated as untrusted input.

This change sequences *after* `fix-codeql-security-alerts` lands (per project convention of one change at a time), and *after* `@errand-ai/ui-components@0.6.0` ships (handled by the separate `bump-dompurify` change in the component library) so that the consumer-side bump closes all dompurify alerts in this repo in one step.

## What Changes

### Dependency bumps

- `errand/requirements.txt`: `cryptography` `43.0.1` → `46.0.6` (closes 3 alerts; 43→46 changelog audit confirms no API surface change for our `Fernet` / `Ed25519PrivateKey` / `serialization` usage)
- `errand/requirements.txt`: `python-multipart` `==0.0.12` → `>=0.0.26` (closes 3 alerts; FastAPI 0.115 only requires `>=0.0.7` so the current exact pin is over-constrained; moving to a floor range lets FastAPI's own range drive future updates)
- `errand/requirements-test.txt`: `pytest` `8.3.3` → latest `8.x` (closes 1 alert; test-only scope)
- `frontend/package.json`: `@errand-ai/ui-components` `^0.5.0` → `^0.6.0` (depends on the `bump-dompurify` change in the component library shipping `0.6.0` first; sweeps all 5 dompurify Dependabot alerts and closes the real-code-path XSS exposure)
- `frontend/package.json`: `vite` `^5.4.0` → latest patched `^5.4.x` (closes 4 vite alerts; sweeps `rollup`, `esbuild`, `undici` transitives)
- `frontend/package.json`: bump `tailwindcss` major/minor to a release whose transitive `chokidar`/`fast-glob` pull non-vulnerable `picomatch` (closes 4 picomatch alerts; picomatch never ships in `dist/`, so the alerts are build-scope despite Dependabot's `scope: "runtime"` labelling)
- `frontend/package-lock.json`: regenerated from the above; `npm audit` run as a final sweep for any remaining transitives

### Switch from Dependabot to Renovate

- Move all dependency-update automation from GitHub Dependabot to Renovate, configured centrally in the `errand-ai/.github` default-repo (so the same policy inherits to all org repos automatically). The Renovate config is NOT added to this repo — the org-level default-repo mechanism handles it.
- The Renovate config work itself is tracked outside OpenSpec (it's a single JSON file in a different repo and does not change behaviour of anything in `errand-ai/errand-ai`). This proposal records the decision and the resulting state change; the implementation is a coordinated small PR against `errand-ai/.github` by whoever owns that repo.
- Renovate policy: **PRs for all updates** (no auto-merge). Patches, minors, and majors all go through human review. This is the conservative starting posture; we can loosen it later if the PR volume becomes a burden.
- Dependabot: disable `version-updates` in this repo's GitHub UI once Renovate is producing PRs. Leave `security-updates` on until Renovate has proven it handles urgent CVEs on an acceptable cadence (Renovate has its own `vulnerabilityAlerts` config; enabling that is a follow-on).

### Behaviour changes

- **Markdown rendering in `TaskOutputModal`**: the XSS and mutation-XSS classes fixed in `dompurify 3.3.2` + `3.4.0` become unreachable for LLM-generated task output. The observable contract (tagged in the `task-output-viewer` spec) tightens from "sanitized with DOMPurify" to "sanitized with DOMPurify at a version resistant to the XSS and mutation-XSS classes fixed in `dompurify >= 3.4.0`".
- **No runtime behaviour change for `python-multipart`**: the endpoint that uses `UploadFile` (voice transcription) continues to accept the same input shapes; parser defaults are unchanged.
- **No runtime behaviour change for `cryptography`**: `Fernet` and `Ed25519PrivateKey` APIs used by this codebase are stable across 43→46.

### Out of scope

- Tightening `dompurify` configuration (explicit `ALLOWED_TAGS`, `SAFE_FOR_TEMPLATES`, etc.). The defaults are sufficient once patched; a sanitizer-posture review belongs in its own change.
- Removing `python-multipart` as a dependency or replacing `UploadFile`. The existing endpoint is kept.
- Migrating `cryptography` away from Fernet to a different encryption primitive.
- Any code changes to test fixtures that use RSA from `cryptography`.
- Changes to `errand-ai/errand-component-library` — that repo has its own `bump-dompurify` change and its own release.
- Changes to the Renovate config file contents beyond the "PRs for all updates" decision. Detailed schedule, grouping rules, and branch policy live in the `.github` repo PR.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-output-viewer`: the `TaskOutputModal displays task output` requirement SHALL tighten the sanitizer version contract to `dompurify >= 3.4.0`, matching the upstream contract in the `@errand-ai/ui-components` `task-components` spec. This is a pure contract tightening; the rendered output for typical markdown inputs is unchanged.
- `ci-pipelines`: ADD a new requirement establishing Renovate (configured at the org default-repo `errand-ai/.github`, not per-repo) as the dependency-update automation mechanism, superseding the implicit use of GitHub Dependabot. The requirement SHALL specify PRs-for-all-updates as the initial posture, with human review required before merge.

## Impact

- **Code**: `errand/requirements.txt` (2 lines), `errand/requirements-test.txt` (1 line), `frontend/package.json` (3+ direct deps), `frontend/package-lock.json` (regenerated).
- **APIs**: No external API surface change. FastAPI upload endpoints behave identically. MCP server behaviour unchanged.
- **Dependencies**: no new packages added, none removed. Version floors raised as described above.
- **CI/CD**: Dependabot alerts closed after lockfile resolves; Renovate starts opening PRs after the separate `.github` repo PR lands. No change to the existing `.github/workflows/build.yml` test gates.
- **Deployment**: Patch-level semver bump of this repo. ArgoCD sync is routine; no migration, no config change, no Helm value change. The `cryptography` wheel ships bundled OpenSSL — this is handled at pip install time, not at runtime.
- **Security scanning dashboard**: goes from 27 open alerts to 0 after both this change and the `bump-dompurify` component-library release ship and the `.github` Renovate config lands.
- **Tests**: Existing tests continue to pass. One new regression test in the frontend exercising the mutation-XSS payload class against `TaskOutputModal` (matching the spec's new scenario).
