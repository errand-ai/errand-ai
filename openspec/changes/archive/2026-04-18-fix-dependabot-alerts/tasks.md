## 1. Preconditions

- [x] 1.1 Confirm `fix-codeql-security-alerts` has been merged to `main` and this repository is at a clean state on `main`
- [x] 1.2 Confirm `@errand-ai/ui-components@0.6.0` is published to npm (`npm view @errand-ai/ui-components versions --json` SHALL include `0.6.0`)
- [x] 1.3 (Independent, does not block this change but coordinates with it) Verify whether the `errand-ai/.github` Renovate config PR is open / merged — this affects task 5.x ordering but not the dep-bump work in tasks 2–4

## 2. Feature branch and versioning

- [x] 2.1 Create a feature branch off `main` (suggest `fix-dependabot-alerts`)
- [x] 2.2 Bump the `VERSION` file with a patch-level increment (per CLAUDE.md semver policy)

## 3. Backend dependency bumps

- [x] 3.1 Edit `errand/requirements.txt`: change `cryptography==43.0.1` to `cryptography==46.0.6`
- [x] 3.2 Edit `errand/requirements.txt`: change `python-multipart==0.0.12` to `python-multipart>=0.0.26`
- [x] 3.3 Edit `errand/requirements-test.txt`: bump `pytest==8.3.3` to the latest `8.x` release
- [x] 3.4 Recreate the venv: `/opt/homebrew/bin/python3.12 -m venv errand/.venv && errand/.venv/bin/pip install -r errand/requirements.txt -r errand/requirements-test.txt`
- [x] 3.5 Run the backend test suite: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`. All tests SHALL pass.
- [x] 3.6 Spot-check `Fernet` round-trip: encrypt and decrypt a sample string in a REPL or one-off test to confirm the credential-storage path is unaffected by the `cryptography` upgrade
- [x] 3.7 Spot-check `Ed25519PrivateKey`: generate a key, sign a message, verify, confirm no API breakage

## 4. Frontend dependency bumps

- [x] 4.1 Edit `frontend/package.json`: bump `@errand-ai/ui-components` from `^0.5.0` to `^0.6.0`
- [x] 4.2 Edit `frontend/package.json`: bump `vite` to the latest patched `^5.4.x` release (do NOT jump to 6.x)
- [x] 4.3 Edit `frontend/package.json`: bump `tailwindcss` to a release whose transitive `chokidar`/`fast-glob` pull non-vulnerable `picomatch` (verify via `npm ls picomatch` after install)
- [x] 4.4 Run `cd frontend && npm install` to regenerate `package-lock.json`
- [x] 4.5 Run `cd frontend && npm audit` and document any remaining alerts; expected result is zero high/medium runtime alerts
- [x] 4.6 Run `cd frontend && npm run test`. All frontend tests SHALL pass.
- [x] 4.7 Run `cd frontend && npm run build`. The production build SHALL complete with no new warnings.
- [x] 4.8 Confirm `npm ls dompurify` resolves to `3.4.0` or higher via the `@errand-ai/ui-components` dep chain

## 5. Spec sync

- [x] 5.1 Sync this change's `task-output-viewer` delta to `openspec/specs/task-output-viewer/spec.md` (via `/opsx:sync` or the `openspec-sync-specs` skill) so the sanitizer version floor and mutation-XSS scenario land in the main spec
- [x] 5.2 Sync this change's `ci-pipelines` ADDED requirement to `openspec/specs/ci-pipelines/spec.md`

## 6. Regression test

- [x] 6.1 Add a frontend test covering the new `Mutation-XSS payload class is neutralised` scenario: render `TaskOutputModal` with a payload from the GHSA-h8r8-wccr-v5f2 class, assert the resulting DOM contains no executable script context or `on*` event handler attributes attributable to the payload

## 7. Local end-to-end smoke test

- [x] 7.1 Run `docker compose -f testing/docker-compose.yml up --build` from repo root; wait for `errand-server` to become healthy
- [x] 7.2 Open `http://localhost:8000`, log in (local auth or Keycloak per current config), create a simple task, wait for completion, open the TaskOutputModal, confirm markdown renders correctly
- [x] 7.3 Navigate to the voice transcription settings and upload a short audio file via the existing UI; confirm the upload succeeds and transcription returns. This exercises the `python-multipart` bump.
- [x] 7.4 Visit settings screens that exercise credential encryption (cloud, platform creds) to confirm `Fernet` round-trip works end-to-end
- [x] 7.5 `docker compose -f testing/docker-compose.yml down`

## 8. PR and review

- [x] 8.1 Commit on the feature branch, push to origin, open a PR against `main` titled `fix: close Dependabot alerts (cryptography, python-multipart, pytest, vite, tailwind, ui-components 0.6)`
- [x] 8.2 PR body SHALL enumerate the closed alert GHSAs and link to the `bump-dompurify` release in `errand-ai/errand-component-library`
- [x] 8.3 Confirm CI passes (tests, Docker build, Helm chart package)
- [x] 8.4 Verify the PR-tagged deployment on Kubernetes before merging (per CLAUDE.md Development Workflow step 5)
- [x] 8.5 Merge to `main`

## 9. Post-merge verification

- [x] 9.1 Wait for the main branch lockfiles to resolve in GitHub's Dependabot scan cycle
- [x] 9.2 Verify the repository's Dependabot dashboard shows zero open alerts (all 27 previously open alerts SHALL be in a closed state)
- [x] 9.3 If any alert remains open, investigate: either the bump did not resolve the transitive (requires `npm audit fix` or a tighter override) or the alert is for a different version range; triage and follow up in a small PR.

## 10. Disable Dependabot version-updates

- [x] 10.1 Coordinate with whoever owns `errand-ai/.github`: confirm the Renovate config PR is merged and Renovate is actively producing PRs against this repository
- [x] 10.2 In this repository's GitHub Settings → Security & analysis → disable Dependabot version-updates
- [x] 10.3 Leave Dependabot security-updates ENABLED for now (evaluation for removal is a follow-on change once Renovate's vulnerability-alerts behaviour has been observed)
