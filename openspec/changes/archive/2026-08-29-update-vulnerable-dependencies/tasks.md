## 1. Branch and version

- [x] 1.1 Create branch `update-vulnerable-dependencies` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` — patch. No behaviour of errand's own changes; the one spec delta is a correction to a statement that was already wrong

## 2. npm advisories (largest diff, most verification)

Nine advisories, four of which have a Renovate PR. `npm audit fix` closes all nine in one lockfile pass.

- [x] 2.1 Record the starting state: `cd frontend && npm audit --json` — capture the nine package names and severities so the after-state can be compared against something, not just declared clean
- [x] 2.2 Confirm every advisory reports `fixAvailable: true` as a **plain boolean**, not an object. An object carries `isSemVerMajor` and means a breaking upgrade is required — if any entry is an object, stop and reassess. Do **not** reach for `--force`
- [x] 2.3 Run `npm audit fix` (no `--force`). Expect only `frontend/package-lock.json` to change; `package.json` should be untouched because all four direct packages already carry caret ranges that admit the fixed versions
- [x] 2.4 Re-run `npm audit` and confirm zero remaining advisories
- [x] 2.5 Confirm the resulting versions are at or above what each superseded Renovate PR proposed: `dompurify` ≥ 3.4.13, `marked` ≥ 18.0.2, `postcss` ≥ 8.5.23, `vite` ≥ 7.3.5. A version below any of these means Renovate will simply reopen that PR
- [x] 2.6 Confirm `nanoid` resolves to ≥ 3.3.18 — the `postcss` PR only widened the range to `^3.3.16`, which does not by itself close the advisory
- [x] 2.7 `npm run test` — 267 tests green
- [x] 2.8 `npm run build` — the production bundle still builds. `vite` and `postcss` are build-time, so this is where a bad bump surfaces

## 3. Verify what actually renders

`marked` and `dompurify` are the only two packages here that reach a browser, and the only two whose failure mode is invisible to the test suite. `marked` 18.0.2 changes block-tokenizer whitespace handling; a green suite does not prove existing output still renders the same.

- [x] 3.1 Bring up the stack: `docker compose -f testing/docker-compose.yml up --build`
- [x] 3.2 Open a completed task with rich output — code blocks, tables, lists, tool results — and compare the rendering against the same task before the change. Looking for silently dropped or restructured markup, not errors
- [x] 3.3 Confirm `TaskOutputModalXssRegression.test.ts` still passes and still asserts something meaningful against the new `dompurify`. Thirteen patch releases of a sanitiser can move the ground under a regression test without failing it
- [x] 3.4 Confirm a task log stream renders live without the tab hanging — the `marked` advisory is an OOM, so the failure it guards against looks like a frozen browser, not an exception

## 4. Python advisories

Three manifests, independent of each other and of section 2.

- [x] 4.1 `errand/requirements.txt`: `cryptography==48.0.1` → `==50.0.0`
- [x] 4.2 `workspace-gateway/requirements-test.txt`: `pytest==8.3.4` → `==9.0.3`, `requests==2.32.3` → `==2.33.0`. Note the comment in that file — `refresher.py` imports `requests` at module load and the pin tracks the image's version, so check the refresher image agrees
- [x] 4.3 `evals/requirements.txt`: `mcp==1.2.0` → `==1.28.1`
- [x] 4.4 Backend suite green: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`. This is the meaningful check for `cryptography` — credential encryption (`Fernet`) and Ed25519 key handling are the only paths errand uses
- [x] 4.5 Eval driver tests green (`evals/tests/`) — 26 minor versions of `mcp` is a wide jump for a client, even a well-behaved one
- [x] 4.6 Do **not** touch `mcp[http]>=1.23.2,<2` in `errand/requirements.txt`. The `<2` is load-bearing: mcp 2.0.0 removed `mcp.server.fastmcp`, which `errand/mcp_server.py:15` imports, and its absence broke CI at collection time on 2026-07-28 (bound added in `05c3791`). Narrowing to an exact pin also leaves the file neither pinned nor ranged — 17 of 27 entries are ranges. The SDK's own migration guide says it outright: *"If your package depends on `mcp`, keep a `<2` upper bound until you've migrated."* Nothing in 2.0.1/2.1.1 restores the module — those releases only improve the `ModuleNotFoundError` message. See the open questions in `design.md` and the `migrate-mcp-sdk-v2` change
- [x] 4.7 While in these files, note but do **not** change `task-runner/requirements.txt`: `mcp>=1.0.0` has no upper bound and escaped the same breakage only because `openai-agents` declares `mcp<2,>=1.19.0`. Out of scope here; raise it separately so it is not lost

## 5. Spec correction

- [x] 5.1 Apply the `ci-pipelines` delta: the requirement asserts no `renovate.json` exists in this repository; one has since `d1415d9`. The corrected requirement preserves the intent — policy lives centrally — while describing the minimal root config that extends it
- [x] 5.2 `validate-specs` green in CI

## 6. Ship

- [x] 6.1 Commit, push, open a PR
- [x] 6.2 CI green
- [x] 6.3 Deploy the built artifacts to Kubernetes and confirm the frontend loads and task output renders. Per CLAUDE.md, a green CI build alone is not sufficient
- [x] 6.4 Archive the change and commit the archive **as part of this PR** — the flattened spec and the archived change belong in the same commit range as the code they describe, not in a follow-up PR. Note this re-triggers CI and produces a new image tag, so re-confirm the redeploy afterwards
- [ ] 6.5 Merge, delete branch

## 7. Superseded Renovate PRs

Renovate closes a PR once the base branch already satisfies its target version, and this change meets or exceeds all eight targets — so no manual closing is needed. Recorded rather than actioned.

- [x] 7.1 #230 (dompurify ≥3.4.13 → 3.4.14), #231 (marked ≥18.0.2 → 18.0.11), #232 (postcss ≥8.5.23 → 8.5.26), #233 (vite ≥7.3.5 → 7.3.6) — satisfied by the consolidated `npm audit fix`, which also closed five advisories these PRs did not cover
- [x] 7.2 #240 (cryptography 50.0.0) — taken as-is
- [x] 7.3 #218 (requests 2.33.0), #219 (pytest 9.0.3) — taken as-is. #218 alone would not have fixed the advisory: the vulnerable pin was in `Dockerfile.refresher`, which that PR did not touch
- [x] 7.4 #221 (mcp 1.28.1) — version taken, but it fixed nothing: the CVEs are server-side DoS in the Streamable HTTP transport and `evals/` is a pure MCP client. Auto-closure will not say that, so the reasoning lives here and in the PR body
- [ ] 7.5 After merge, confirm all eight actually closed. One still open means a version landed below what it proposed — check that package rather than closing it by hand
- [x] 7.6 Leave #204, #226, #209, #197 open — out of scope, reasons in the proposal

## 8. Hand off

- [x] 8.1 Confirm `address-security-review-findings` branches from a `main` that already contains this change, so its own login and CORS validation is not confounded by a dependency bump
