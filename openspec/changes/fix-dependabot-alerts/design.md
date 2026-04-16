## Context

### Dependabot alert landscape

| Package | Ecosystem | Scope | # alerts | Severity mix | Current pin | Target |
|---|---|---|---|---|---|---|
| `dompurify` | npm (transitive via `@errand-ai/ui-components`) | runtime | 5 | 1 high, 4 medium | `^3.3.1` (in component library) | `^3.4.0` via `@errand-ai/ui-components@^0.6.0` |
| `python-multipart` | pip | runtime | 3 | 2 high, 1 medium | `==0.0.12` | `>=0.0.26` |
| `cryptography` | pip | runtime | 3 | 1 high, 2 low | `==43.0.1` | `==46.0.6` |
| `picomatch` | npm (transitive via Tailwind, vitest, etc.) | runtime (mislabelled — actually build-time only) | 4 | 2 high, 2 medium | resolved through `tailwindcss` | sweeps via bumping direct parents |
| `vite` | npm | development | 4 (1 direct, 3 transitive) | 2 high, 2 medium | `^5.4.0` | latest patched `^5.4.x` |
| `undici` | npm (transitive) | development | 3 | 1 high, 2 medium | — | sweeps via bumping parents |
| `rollup` | npm (transitive of vite) | development | 1 | high | — | sweeps via vite bump |
| `minimatch` | npm (transitive) | development | 1 | high | — | `npm audit fix` |
| `esbuild` | npm (transitive of vite) | development | 1 | medium | — | sweeps via vite bump |
| `pytest` | pip | development | 1 | medium | `==8.3.3` | latest `8.x` |

Total: 27 open alerts.

### Exposure analysis (why 2 of 27 is the honest count)

The per-alert review is in the proposal's "Why" section. Summarising:

- **Reachable in our code**: 2 × `dompurify` (GHSA-v2wj-7wpq-c8vv, GHSA-h8r8-wccr-v5f2) — both apply to default-config `sanitize()`, which we call at exactly one site (`TaskOutputModal.vue`), fed by LLM-generated task output.
- **Mitigated by our usage**: 3 × `dompurify` (need non-default options we never set); 1 × `python-multipart` (the arbitrary-file-write alert requires non-default parser configuration); 2 × `cryptography` (SECT curve subgroup attack + TLS peer DNS name constraints — neither primitive is in our call graph).
- **Mitigated by privilege**: 2 × `python-multipart` DoS — the only `UploadFile` endpoint is admin-auth-gated (`/api/voice/transcribe`).
- **Build-time only, never ships**: 4 × `picomatch` (via Tailwind's `chokidar`/`fast-glob` + vitest), all of `vite`/`rollup`/`esbuild`/`undici`/`minimatch` dev alerts.

### Upstream constraints

- The `dompurify` bump can only be consumed by this repo once `@errand-ai/ui-components@0.6.0` is published to npm. That release is tracked by the `bump-dompurify` OpenSpec change in `errand-ai/errand-component-library`.
- FastAPI 0.115 requires `python-multipart>=0.0.7` only; the current `==0.0.12` pin is tighter than necessary.
- `cryptography` 43→46 crosses three major versions; changelog review (v44 through v46) confirms no API surface change affecting our usage of `Fernet`, `Ed25519PrivateKey`, or `serialization`.

### Sequencing

- This change is blocked on `fix-codeql-security-alerts` landing (per project convention of one change at a time).
- This change is blocked on `@errand-ai/ui-components@0.6.0` being published to npm (out-of-repo, tracked in the component library's `bump-dompurify` change).
- The Renovate config in `errand-ai/.github` is a separate PR against a separate repo and lands independently; it is not blocked by this change and this change is not blocked by it.

## Goals / Non-Goals

**Goals:**

- Drive the GitHub Dependabot dashboard for this repo to 0 open alerts.
- Replace Dependabot with Renovate (centrally configured in `errand-ai/.github`) as the dependency-update automation for all org repos.
- Document exposure per alert so future reviewers can see which alerts this repo was actually vulnerable to.
- Keep the change to the minimum set of version bumps needed to close all alerts — no incidental refactoring, no sanitizer-posture review, no `python-multipart` removal.

**Non-Goals:**

- Tighten the `dompurify` sanitizer configuration (explicit allow-lists, `SAFE_FOR_TEMPLATES`, etc.). Defaults are adequate once patched; a posture review is a separate change.
- Remove `python-multipart` or replace `UploadFile` in the transcription endpoint.
- Replace `cryptography` with another library.
- Pin the Renovate config in this repo. The org default-repo mechanism is intentional.
- Enable Renovate auto-merge. Initial posture is PRs for all updates, human-review required.

## Decisions

### Decision 1: Rely on `@errand-ai/ui-components@0.6.0` for the dompurify fix, rather than npm overrides

npm overrides in `frontend/package.json` could force `dompurify` to `3.4.0` transitively without waiting for a new `@errand-ai/ui-components` release. We reject this approach because:

- The consuming code path (`DOMPurify.sanitize(raw)`) lives *inside* `@errand-ai/ui-components`. An override in this repo would patch the resolution but the component library's own tests, published artefact, and Dependabot dashboard would still show the vulnerable version.
- Overrides drift silently from the library's declared range and produce a maintenance footgun when the library is next updated.
- The `bump-dompurify` change in the component library is small and sequences in parallel with `fix-codeql-security-alerts` here, so the wait is brief.

### Decision 2: Bump `python-multipart` to a floor range (`>=0.0.26`), not an exact pin

The current `==0.0.12` is over-pinned. FastAPI 0.115 already specifies `>=0.0.7`. Moving to `>=0.0.26` keeps the CVE fix as a floor but lets FastAPI's own range carry future updates (including whatever Renovate later bumps to via the new `errand-ai/.github` policy). Alternatives rejected:

- **Keep exact pin, bump to `==0.0.26`**: unnecessarily constrains future patch flow; Renovate would have to keep re-opening bumps.
- **Remove the line entirely and let FastAPI pull it**: works, but makes the CVE floor implicit; a future FastAPI relaxation could silently regress us below `0.0.26`.

### Decision 3: Pin `cryptography` exactly at `46.0.6`, not a floor

We use an exact pin (`==46.0.6`) for `cryptography` because:

- The wheel build embeds a specific OpenSSL version; "what runs in prod" is version-sensitive.
- `cryptography`'s track record includes occasional runtime-visible changes inside major versions (deprecation warnings, minimum OpenSSL bumps). An exact pin keeps our production behaviour reproducible and forces Renovate to surface every bump for review.

Alternatives rejected:

- **Floor `>=46.0.6`**: too loose for a runtime security library; Renovate will still open PRs either way, so we lose nothing by being exact.
- **Range `~=46.0`**: surfaces patch flow automatically but hides the OpenSSL rev embedded in the wheel. Not worth the ambiguity.

### Decision 4: Bump `vite` to latest `^5.4.x`, do not jump to 6.x

Vite 6 is a feature release with config-surface changes (notably around `resolve.conditions` and some plugin API). The alerts are all fixed in `5.4.x` patches, so staying on 5.x closes the CVEs with zero config churn. Moving to 6 would trigger dev-environment validation work we don't need to bundle in a security patch change. Renovate will open the 5→6 PR in its own time.

### Decision 5: Sweep the `picomatch` alerts by bumping Tailwind, not by adding an override

`picomatch` reaches `package-lock.json` through `tailwindcss → chokidar → readdirp → picomatch` and `tailwindcss → fast-glob → micromatch → picomatch`. Bumping `tailwindcss` pulls in parent chokidar/fast-glob versions that ship with patched `picomatch`. Alternatives rejected:

- **npm override forcing `picomatch@^4.x` everywhere**: works but creates friction if a sibling tool pins to `picomatch@^2.x`. The tailwind bump is the natural upgrade path.
- **Leave alerts open because picomatch is build-time only**: does not close the Dependabot dashboard; fails the goal of zero open alerts.

### Decision 6: Keep the `bump-dompurify` consumer-side upgrade in *this* change, not a separate one

Bundling the `@errand-ai/ui-components` bump here (rather than a separate "frontend-only-deps" change) keeps the security-patch story coherent: one PR in this repo closes all its Dependabot alerts. Splitting would triple ceremony for no isolation benefit — the pip bumps and the npm bump do not interact.

### Decision 7: Renovate config lives in `errand-ai/.github`, not in this repo

Per user direction. The org default-repo pattern means every repo in the org inherits the config without per-repo drift. Implementation of the config file is tracked outside OpenSpec (it's a single JSON file in a repo that doesn't use OpenSpec; imposing OpenSpec ceremony there is overhead for no benefit).

### Decision 8: Initial Renovate posture is PRs-for-all-updates, no auto-merge

Per user direction. Rationale: we are switching automation tooling at the same time as closing 27 alerts. Starting with full human review means we notice any Renovate-specific behaviour we were not expecting (grouping rules, weird schedule interactions, dashboard issues). After a few weeks of operating experience we can loosen toward auto-merge-on-CI-green for patch-level updates, which typically have the best signal-to-noise ratio.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `cryptography` 43→46 introduces a runtime-visible change we missed in the changelog review | Run the full backend test suite in CI; smoke-test `Fernet` round-trip and `Ed25519` signing on a dev deployment before merging. The changelog review for v44/45/46 showed no API surface changes affecting our call sites, but a smoke test is cheap. |
| `python-multipart` 0.0.12 → 0.0.26 changes FastAPI upload behaviour in an edge case | Run the transcription endpoint integration test; manually upload a voice file via the dev UI. FastAPI's own suite targets a range including 0.0.26, so the integration is already exercised upstream. |
| `@errand-ai/ui-components@0.6.0` not yet published when this change is ready to merge | This is a hard sequencing dependency. Tasks explicitly gate the frontend `package.json` bump on the library release being live on npm. If the library change slips, we can merge the pip bumps alone and follow up with a second PR for the frontend. |
| Tailwind bump pulls in a new CSS compilation behaviour | Run `npm run build` in the frontend and diff the output CSS against a baseline (the existing snapshot tests should catch utility-class regressions). Consider a screenshot-based smoke test of the Kanban board. |
| Renovate starts opening too many PRs on day one and swamps reviewers | The central `.github` config can (and should) enable grouping rules (e.g. group minor+patch npm bumps into weekly PRs). This is in scope for whoever authors the Renovate config — not this change — but we flag the expected volume in the task list. |
| Dependabot and Renovate both open PRs during the transition | Disable Dependabot version-updates in the repo UI as soon as Renovate's first PR lands. Leave Dependabot security-updates on until we have evidence Renovate's `vulnerabilityAlerts` behaviour is adequate (follow-on, not part of this change). |

## Migration Plan

1. **Precondition**: `fix-codeql-security-alerts` is merged to main in this repo.
2. **Precondition**: `@errand-ai/ui-components@0.6.0` is live on the npm registry (handled by the `bump-dompurify` change in the component library).
3. **Precondition (optional for parallel work)**: A Renovate config PR is open against `errand-ai/.github`. This change does not require that PR to be merged first — the two sequences are independent.
4. Branch from `main`, bump the `VERSION` file (patch bump unless the cryptography update trips something unexpected, in which case the escalation path is a minor bump and a narrower change).
5. Apply the pip manifest changes in `errand/requirements.txt` and `errand/requirements-test.txt`.
6. Recreate the venv locally: `/opt/homebrew/bin/python3.12 -m venv errand/.venv && errand/.venv/bin/pip install -r errand/requirements.txt -r errand/requirements-test.txt`. Run the backend test suite.
7. Apply the npm manifest changes in `frontend/package.json`. Run `npm install` to regenerate the lockfile. Run `npm audit` and triage any remaining transitives (expected: zero or near-zero).
8. Run `npm run test` and `npm run build` in `frontend/`. Run `docker compose -f testing/docker-compose.yml up --build` from repo root and click through task creation, task output modal, voice transcription.
9. Push the branch, open the PR. Confirm CI green.
10. Merge. After lockfile resolves on `main`, verify Dependabot dashboard shows 0 open alerts.
11. In parallel: once the `errand-ai/.github` Renovate PR lands and Renovate starts opening PRs, disable Dependabot version-updates in this repo's GitHub settings.

### Rollback

If `cryptography 46.0.6` causes a runtime incident post-merge:

- Revert the `errand/requirements.txt` line to `cryptography==43.0.1`, re-publish the image, ArgoCD redeploys.
- `cryptography` Dependabot alerts reopen; address in a smaller change with a different target version (e.g. stop at 45.x if 46 proves unstable for us, accepting that one alert remains open until a working path to 46+ is found).
- Other bumps (`python-multipart`, `pytest`, `vite`, `@errand-ai/ui-components`) are independent and do not need to be rolled back if only `cryptography` fails.

## Open Questions

- **Does `python-multipart 0.0.26` change the default upload size limit?** The changelog hints at new DoS mitigations that may cap preamble/epilogue sizes. If it does, the transcription endpoint's allowed payload shape may narrow. Verified in the smoke test during implementation; callout for reviewers to confirm.
- **Timeline for the Renovate PR in `errand-ai/.github`?** Not strictly part of this change but affects the "Dependabot off" timing. Nominally coordinated with the person who owns that repo.
