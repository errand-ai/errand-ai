## Context

See `proposal.md` for the security motivation, source links and scope. Current main pins AnyIO 4.13.0 in `evals/requirements-test.txt`. CI installs that file from `evals/` and runs `pytest tests/ -v`; the test requirements intentionally omit the lazily imported MCP client. Existing `eval-driver` requirements do not prescribe an AnyIO version or promise application-level TLS/process-pool behavior.

The repository uses the `spec-driven` OpenSpec schema. The installed CLI is 1.13.0, while `CLAUDE.md` mentions 1.1.1 and the main-spec CI validator installs 1.6.0. Proposal validation will report the exact CLI and commands used; no dependency-management tooling changes are part of this proposal.

## Goals / Non-Goals

Goals: remove the reported vulnerable test pin, preserve eval behavior, provide reproducible offline unit-test evidence and resolve release-version safety before merge.

Non-goals: establish or fix production runtime exposure, upgrade unrelated dependencies, exercise live MCP tasks, alter eval semantics or upstream AnyIO implementation.

## Decisions

1. Adopt the exact Renovate target, 4.14.2, rather than an unbounded minimum, an earlier partial update, or local TLS/stderr workarounds. This keeps the narrow remediation reproducible and follows the PR's reported patched release. Assess transitive install changes through clean-environment installation rather than broadening committed pins.
2. Explicitly opt out of delta specs with `skip_specs: true`. This is dependency maintenance of test tooling with unchanged product requirements; adding a security capability would misrepresent the existing product contract. The implementation checklist is the acceptance plan. Do not modify flattened main specs by hand.
3. Treat PR #268 as the implementation source. This authoring task publishes a proposal-only feature branch from main and does not edit Renovate's branch or dependency files. After Team Leader approval, the implementing agent must carry this proposal into the implementing PR, update the dependency and archive there before merge. Do not separately merge a completed active proposal and leave it on main.
4. Resolve release versioning on the implementation branch. CI skips expensive builds for OpenSpec-only diffs, so this proposal does not bump `VERSION`. A dependency diff triggers builds; PR tags append `-pr<PR_NUMBER>.<RUN_NUMBER>` and skip the main-only immutable-tag guard. Therefore green PR checks do not establish that the unchanged main release tag is safe. Rebase on current main and select an unused patch version for the implementation PR; no hard-coded version from the older review comment.
5. Validate eval installation and unit tests in an isolated Python environment matching CI's Python 3.13 and `evals/` working directory. Record `importlib.metadata.version('anyio')`, dependency compatibility and test output. No Errand, judge, API key or live infrastructure is required for these fake-client tests. Upstream TLS/process-pool fixes are not reimplemented or proven by this suite.

## Risks / Trade-offs

- AnyIO 4.14.0/4.14.1 behavior changes accompany 4.14.2 -> run the full eval unit suite, not merely installation or an import check; investigate failures before merge.
- Production also may consume AnyIO indirectly -> do not extrapolate protection from this test pin; any confirmed runtime exposure requires a separately scoped proposal.
- Release-version drift -> refresh main before choosing the patch release and resolve the bot concern explicitly in the implementing PR.
- Older OpenSpec clients may not support the specs opt-out -> verify the actual CLI and preserve validation evidence; do not fabricate delta requirements merely to satisfy an older parser.
- Archiving and implementation pushes create new CI builds -> repeat deployment verification for the final post-archive build where the repository's release workflow requires it.

## Migration Plan

After approval: refresh the selected PR and main, carry these artifacts onto the implementation branch, choose an unused patch release, adopt the exact pin, install cleanly and run the eval suite. Follow repository-required local build and Kubernetes verification gates for the implementing PR. Archive only after all pre-merge tasks are complete, commit the archive in that PR and verify the final build/deployment before merge.

No data migration or user configuration changes. If compatibility fails, stop the merge and investigate; reverting the pin reintroduces the reported vulnerable dependency, so it is an emergency fallback only, with explicit security follow-up. Release reversions must use a new version rather than overwrite published immutable tags. Documentation impact is reviewed by the Analyst after implementation verification, with any website work routed through Team Leader.
