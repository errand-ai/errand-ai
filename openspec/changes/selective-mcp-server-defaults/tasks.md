## 1. Branch and version

- [x] 1.1 Create branch `selective-mcp-server-defaults` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` from `0.140.0` to `0.141.0` (minor — restores user-facing capability)

## 2. Dependency bump

- [x] 2.1 Change `@errand-ai/ui-components` from `^0.11.0` to `^0.16.0` in `frontend/package.json`
- [x] 2.2 Run `npm install` in `frontend/` and confirm `package-lock.json` resolves `@errand-ai/ui-components` to `0.16.0` from `npm.pkg.github.com`
- [x] 2.3 Confirm no other dependency was moved by the install — the lockfile diff should touch only the `@errand-ai/ui-components` entry and its own transitive deps

## 3. Build and static checks

- [x] 3.1 Run the frontend type check and confirm it is clean — the library's `TaskProfile.model` is now `ModelSetting | null`, so any errand code narrowing that type will surface here
- [x] 3.2 Run `npm run build` in `frontend/` and confirm it succeeds
- [x] 3.3 Run the frontend test suite (`vitest`); `TaskProfilesPage.test.ts` and `SettingsCapabilityGating.test.ts` mount the real library components and are the likeliest to fail
- [x] 3.4 For any failing test, read the failure before editing it — update the assertion only where the library's new behaviour is correct, and do not weaken an assertion to make the suite pass

## 4. Verification — deployment scope

**Deferred to the deployed PR build** (decision taken during apply; run these after task 8.3, not locally). Local verification was attempted and blocked: `/api/litellm/mcp-servers` returned `available: false`, because the seeded `llm_providers` row is typed `provider_type='unknown'` rather than `'litellm'` so `_resolve_litellm_provider()` (`errand/main.py:1409`) never matches it, and the `testing/.env` LiteLLM key is rejected by the proxy with `401 token_not_found_in_db`. Per spec the section is hidden when discovery is unavailable, so there was nothing to toggle.

Assert on persisted values (API response or `settings` row), not on rendered UI state.

- [ ] 4.1 Open Settings > Agent Configuration and confirm the "MCP Servers (via LiteLLM)" section renders a toggle per discovered server, reflecting the current `litellm_mcp_servers` setting
- [ ] 4.2 Enable an additional server, save, and confirm `litellm_mcp_servers` persists as the expected array
- [ ] 4.3 Disable every server, save, and confirm the setting persists as `[]` — not `null`, not an absent key
- [ ] 4.4 Confirm the save request body carries `litellm_mcp_servers` and no other settings key
- [ ] 4.5 Confirm the section is clean on load, becomes dirty on a toggle, and is clean again after a successful save
- [ ] 4.6 Force a save failure and confirm the section stays dirty so the navigation guard still fires — this negative path is the one the original regression passed
- [ ] 4.7 Toggle two servers, discard, and confirm every toggle returns to its loaded state

## 5. Verification — profile scope

**Deferred to the deployed PR build** (decision taken during apply; run these after task 8.3, not locally). These are the highest-value checks in this change — the tri-state encoding is invisible in the UI, so verify each state by its persisted value rather than by what the form shows.

- [ ] 5.1 Open Settings > Task Profiles, edit a profile, and confirm the restored fields render: `match_rules`, `max_turns`, `reasoning_effort`, `include_git_skills`, `enabled_plugins`, `mcp_servers`, `litellm_mcp_servers`, `skill_ids`
- [ ] 5.2 Set MCP servers to "Inherit from default", save, and confirm `mcp_servers` persists as `null`
- [ ] 5.3 Set MCP servers to "None", save, and confirm `mcp_servers` persists as `[]`
- [ ] 5.4 Set MCP servers to "Select specific" with two servers checked, save, and confirm `mcp_servers` persists as those two aliases
- [ ] 5.5 Repeat 5.2–5.4 for `litellm_mcp_servers`
- [ ] 5.6 Reopen each saved profile and confirm the editor reloads the same tri-state it persisted — a round trip in both directions, since an inversion is silent
- [ ] 5.7 Confirm `reasoning_effort` round-trips against the server's `VALID_REASONING_EFFORTS` and `enabled_plugins` against `_validate_enabled_plugins`, both flagged as open questions in design
- [ ] 5.8 Confirm saving the profile modal leaves `shared_workspace_enabled` and `shared_workspace_subpath` untouched — the endpoint applies fields by presence and those belong to a different card
- [ ] 5.9 Create a task against a profile with an explicit MCP selection and confirm the task resolves exactly those servers

## 6. Visual check

**Deferred to the deployed PR build**, alongside groups 4 and 5.

- [ ] 6.1 Walk Settings > Agent Configuration and Settings > Task Profiles for layout regressions from the Tailwind v4 and toolchain versions in the 0.12–0.15 span
- [ ] 6.2 Fix any layout regression that arrives with this bump, or record it as a follow-up if it extends beyond these two pages

## 7. Spec sync

- [ ] 7.1 Confirm the delta in `specs/litellm-mcp-settings-ui/spec.md` matches the behaviour observed in section 4 — correct the spec if the library's real behaviour differs. **Deferred with group 4**: the spec is written from the library's stated behaviour and has not yet been checked against a running instance
- [x] 7.2 Confirm no edit is needed to `task-profile-settings-ui`; this change restores conformance to its existing "List field selection UI" requirement rather than altering it

## 8. Ship

- [ ] 8.1 Commit and push the branch, then open a PR
- [ ] 8.2 Confirm CI builds the images and Helm chart successfully
- [ ] 8.3 Deploy the built artifacts to Kubernetes and confirm pod health and ingress routing
- [ ] 8.4 Run groups 4, 5 and 6 in full against the deployed instance — they were deferred here, so this is their only execution. A green CI build alone does not validate this change, and nothing in it has yet been exercised against a running server
- [ ] 8.5 Merge, then delete the local branch

## 9. Follow-ups noted during apply

Not part of this change — record and move on.

- [ ] 9.1 The `llm_providers` row seeded from `LLM_PROVIDER_0_*` gets `provider_type='unknown'` even when it is plainly LiteLLM (name `LiteLLM`, base URL `litellm.coward.cloud`), which silently disables LiteLLM MCP discovery. Worth investigating separately
- [ ] 9.2 The LiteLLM API key in `testing/.env` is rejected with `401 token_not_found_in_db` and needs rotating for local dev to exercise LiteLLM paths
- [ ] 9.3 CLAUDE.md claims 440 frontend tests; the suite on `main` runs 261 across 28 files. The figure is stale
