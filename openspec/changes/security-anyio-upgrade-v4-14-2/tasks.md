## 1. Approval and release preparation

- [ ] 1.1 Obtain Team Leader approval of this proposal and reconfirm PR #268's current scope/head; verify the approval and current file diff are recorded in the implementing PR.
- [ ] 1.2 Refresh the implementation branch from current main and carry this OpenSpec change into the implementing PR; verify the diff contains these artifacts and does not broaden production dependency changes.
- [ ] 1.3 Choose and commit an unused PATCH release in `VERSION` against current main; verify the selected release is not already published and explicitly resolve the missing-version review concern in PR #268. Do not infer release safety from green prerelease checks.

## 2. Dependency remediation and local verification

- [ ] 2.1 Adopt `anyio==4.14.2` in `evals/requirements-test.txt` from PR #268; verify the dependency diff changes only that pin and preserves pytest/PyYAML and lazy MCP import behavior.
- [ ] 2.2 Create a clean Python 3.13 test environment, install `evals/requirements-test.txt` and check dependency compatibility; verify installation succeeds and `importlib.metadata.version('anyio')` reports `4.14.2`, recording command output in the implementing PR.
- [ ] 2.3 From `evals/`, run `python -m pytest tests/ -v` in that environment without a live MCP client or judge; verify the entire unit suite passes and record the result. These tests check compatibility, not independent reproduction of the upstream security fixes.
- [ ] 2.4 Perform the local build/smoke checks required by `CLAUDE.md` using `docker compose -f testing/docker-compose.yml up --build`; verify services are healthy and record results before committing implementation code.

## 3. Pre-merge verification and archive

- [ ] 3.1 Run `openspec validate security-anyio-upgrade-v4-14-2 --strict --no-interactive` and the documented main-spec guard `openspec validate --specs --no-interactive`; verify this change passes and disclose any unrelated pre-existing main-spec failures with exact output.
- [ ] 3.2 Push the implementation and confirm its exact-head CI tests, images and chart builds and required Kubernetes deployment/smoke checks; verify the deployed build corresponds to that head and record evidence in the PR.
- [ ] 3.3 Request Analyst documentation-impact review after implementation verification; verify a documented no-change decision or a Team Leader-to-Website handoff, without claiming confirmed production exposure.
- [ ] 3.4 After preceding checks pass, mark all checklist tasks complete, archive with `openspec archive security-anyio-upgrade-v4-14-2 -y` on the implementation branch and commit it in the same PR; verify no invented flattened specs are introduced and the archive command succeeds.

## Post-archive pre-merge gate

- Push the archive commit, repeat CI and deployment verification against its exact head, resolve outstanding reviews and record the evidence in the PR. Do not edit the frozen archived checklist to record this gate; repeat it if any subsequent commit changes the head.

## Post-merge notes

- Team Leader merges only the fully verified implementation PR and confirms the main release/deployment; no merge action is authorized by proposal publication.
- Confirm PR #268 is merged or closed as superseded if a separate implementation PR is used.
- Remove the proposal-only remote branch after its artifacts are safely included in the implementation commit range.
