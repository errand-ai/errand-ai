## Context

Nine npm advisories and four pip advisories are open against this repository, spread across eight Renovate PRs plus five packages no PR covers. The work itself is trivial — run a command, edit four manifests. Everything interesting about this change is in what gets bundled with what, and in not overstating what the fixes buy.

Two facts shape the approach:

- **Only two of the thirteen packages ship.** `marked` and `dompurify` are runtime dependencies of `@errand-ai/ui-components`; the other seven npm packages are devDependencies and the pip ones are either test-only or unreached code paths. A change that treats all thirteen as equally urgent is miscalibrated in the direction that wastes review attention.
- **`address-security-review-findings` is in flight and touches the login flow.** Its own tasks note that a regression there is a lockout. That change and this one address the same programme of work, which is precisely why they must not share a deploy.

## Goals / Non-Goals

**Goals:**

- Every advisory `npm audit` and Dependabot currently report is closed, not just the ones Renovate opened a PR for.
- One lockfile diff rather than four serialised rebases.
- The two packages that actually render user-visible output are verified in a browser, not only by a green test run.
- The reasoning for each Renovate PR closed as superseded is written down, including the one that fixes nothing.

**Non-Goals:**

- Any application source change. If this change touches a `.py` or `.vue` file, something has gone wrong.
- Major version bumps. `jsdom` v30, `pinia` v4, `typescript` v7 are separate decisions.
- Python 3.13 → 3.14 and the rest of #204.
- Converting `errand/requirements.txt` from ranges to pins.

## Decisions

**Use `npm audit fix`, not four cherry-picked version bumps.** Renovate's four npm PRs each pin one package and rebuild the lockfile around it; applied in sequence they produce four conflicting diffs and still leave five advisories open. `npm audit fix` resolves all nine in one lockfile pass. The alternative — merging the Renovate PRs and then running audit for the remainder — costs four CI cycles to arrive at the same tree.

The check that makes this safe: `npm audit --json` reports `fixAvailable: true` as a plain boolean for all nine, not as an object carrying `isSemVerMajor`. That is npm's own statement that no fix requires a breaking upgrade, which is why `--force` is neither needed nor permitted here. If a future run reports an object instead, stop and reassess rather than reaching for `--force`.

**Close #221 rather than merge it, and say why.** The mcp advisories are server-side DoS in the Streamable HTTP transport. `evals/requirements.txt` is a pure MCP client. Merging it would clear a Dependabot alert while fixing nothing, and would leave a reader believing the mcp exposure had been dealt with. The version bump is still taken — a 26-minor drift is worth closing on its own terms — but the reason recorded is drift, not vulnerability. This is the same discipline `address-security-review-findings` applies to the false positives in its source report: an unexplained fix is as misleading as an unexplained omission.

**Do not pin `mcp[http]` while leaving sixteen other ranges untouched.** The instinct is right and the scope is wrong. Pinning one range because an advisory happened to point at it produces a `requirements.txt` that is neither consistently pinned nor consistently ranged, and invites the next reader to assume the pinned ones were pinned for a reason. Either the file is pinned or it is not; that is a real trade-off (reproducibility against automatic transitive patching on rebuild) and it needs its own change.

**Verify `marked` and `dompurify` by looking at rendered output.** The frontend suite has 267 tests and `TaskOutputModalXssRegression.test.ts` guards the sanitiser seam specifically, but neither proves that ordinary task output still *renders the same* after a tokenizer change. `marked` 18.0.1 → 18.0.11 changes how the block tokenizer handles whitespace it previously mishandled; that is exactly the class of change that alters real output subtly and passes every assertion. Note the delta is ten patch releases, not the single one the superseded Renovate PR proposed — `npm audit fix` resolves to current, not to a floor. A green suite is necessary and not sufficient here.

**Ship as its own PR, ahead of `address-security-review-findings`.** Landing first means the security-review change is developed and deployed against an already-patched dependency set, so its own validation is not confounded. Landing separately means a broken login after that change has one candidate cause. The cost is two deploys instead of one, which is the correct price for that.

**Correct the `ci-pipelines` Renovate scenario in the same change.** The spec asserts no `renovate.json` exists; one has existed since `d1415d9`. Fixing it here rather than filing it separately is justified because this is the change that reads that requirement closely enough to notice, and the correction is three lines. It is the only spec delta in this change.

## Risks / Trade-offs

**`marked` 18.0.11 changes how existing task output renders** → The highest-probability way this change causes visible harm, and the reason the verification step is a browser check rather than a test count. Mitigated by viewing a real task's output — one with code blocks, tables and tool results — before merging.

**`dompurify` 3.4.0 → 3.4.14 tightens sanitisation and strips markup that previously rendered** → Fourteen patch releases of a sanitiser is fourteen opportunities for something legitimate to start being filtered. Same mitigation, same check.

**`cryptography` crosses two majors** → Low risk given errand's usage (`Fernet` in `llm_providers.py`, `Ed25519` in `main.py`), but it is the one pip bump that touches a running code path. The backend suite exercises credential encryption; a green run is meaningful here in a way it is not for the frontend renderers.

**`npm audit fix` rewrites more of the lockfile than four targeted bumps would** → A larger diff to review, and a small chance of an unrelated transitive moving at the same time. Accepted: the diff is mechanical, and the alternative leaves five advisories open.

**Renovate may not auto-close the eight superseded PRs** → Renovate closes a PR once the base branch already satisfies its target version, so no manual closing is needed provided the merged tree is at or above what each proposed. Worth confirming after the merge rather than assuming; a PR still open is the signal that a bump landed below its target.

**Deploying separately doubles the deploy count for one programme of work** → Deliberate. The alternative is a single deploy in which a lockout and a dependency bump are indistinguishable.

## Migration Plan

No schema change, no configuration change, no data migration.

Order within the change: npm first (largest diff, most verification), then the three pip manifests, then the spec correction. The pip bumps are independent of each other and of the npm work.

Order relative to other work: land and deploy before `address-security-review-findings` opens its PR.

Rollback is a version revert. Nothing here is stateful and nothing is one-way.

## Open Questions

- **Should errand adopt a constraints file or lockfile for Python?** This is the open question, and it is not "should we pin `requirements.txt`". On 2026-07-28 three upstream releases broke CI within hours — mcp 2.0.0 removing `mcp.server.fastmcp`, and feedparser 6.0.13 changing its dependencies — because the Docker build resolves fresh on every run against a file where 17 of 27 entries are ranges with few upper bounds. Each was fixed reactively by adding a bound to the one package that broke. A constraints file gives reproducible builds *and* keeps the ranges, so transitive patches still arrive on rebuild rather than only as PRs; per-line pinning gives reproducibility by giving that up. The former looks clearly better and neither has been argued properly. Out of scope here.
- **`task-runner/requirements.txt` declares `mcp>=1.0.0` with no upper bound.** It escaped the 2026-07-28 breakage only because `openai-agents` happens to declare `mcp<2,>=1.19.0`. That is the same defect that took errand down, still live, protected by a third party's constraint rather than its own. Not fixed here because it is neither an advisory nor a Renovate PR, but it is a one-line change and it should not wait for the constraints-file discussion.
- **Should `jsdom` v30 (#226) be taken after all?** `npm audit fix` clears the `undici` cluster within `jsdom@29`, so it is no longer a security question — but it is the reason those advisories appeared, and staying on 29 means they will recur.
- **Is `@errand-ai/ui-components` pinning `dompurify` and `marked` the right ownership?** Both are declared in `frontend/package.json` *and* in the component library's own dependencies. The duplication means a future advisory needs fixing in two repositories, and it is not obvious which one is authoritative.
