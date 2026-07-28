## Context

MCP server selection is configured at two scopes. The deployment scope lives in the `litellm_mcp_servers` setting and decides which LiteLLM-provided servers are enabled by default; the profile scope lives in `task_profiles.mcp_servers` and `task_profiles.litellm_mcp_servers`, each encoding `null` = inherit the deployment default, `[]` = none, `[...]` = an explicit set.

Both scopes are currently unreachable from the UI. Errand's settings pages are thin wrappers — `AgentConfigurationPage.vue` renders `<LitellmMcpCard />` and `TaskProfilesPage.vue` renders `<TaskProfileListCard />`, both imported from `@errand-ai/ui-components`, with `main.ts` supplying a `createDirectApi({ baseUrl: '/api', ... })` adapter. Errand is pinned to `^0.11.0`, which predates the fix for either regression.

The server side is untouched and was never broken. Verified while designing:

- `PUT /api/settings` (`errand/main.py:1315`) is a per-key upsert, so a body of `{ litellm_mcp_servers: [...] }` cannot clobber unrelated settings. `litellm_mcp_servers` is registered with `env_var: None` and is absent from `EXCLUDED_KEYS`, so it is writable rather than silently skipped.
- `PUT /api/task-profiles/{id}` (`errand/main.py:2512`) applies fields by presence — `mcp_servers`, `litellm_mcp_servers` and `skill_ids` are assigned only when the key is in the body. This matches the library's `buildPayload()`, which emits exactly the rendered keys, and is what allows the modal to omit `shared_workspace_*` (owned by a different card) without nulling it.
- `GET /api/skills`, `GET /api/plugins` and `GET /api/worker/defaults` all exist, so the restored option sources resolve.
- The library's `updateTaskProfile` uses `PUT`, matching the route errand serves. No method mismatch.

## Goals / Non-Goals

**Goals:**

- Restore deployment-scoped enable/disable of LiteLLM MCP servers, persisted.
- Restore profile-scoped override of both MCP server lists, including the inherit/none/select tri-state.
- Close the spec gap that let a stubbed save path ship unnoticed.
- Keep the change to a dependency bump — no errand source changes unless verification proves one necessary.

**Non-Goals:**

- No server, schema, migration, endpoint or cloud-proxy change.
- No redesign of the tri-state encoding, which is an established server contract.
- No attempt to duplicate the library's component-level test coverage in errand's suite. Requirement-level coverage of the restored fields belongs to the library (302 tests); errand verifies integration and round-trip.
- Not bumping the other seven fields' behaviour independently — they arrive with the same version and are verified as a set.

## Decisions

**Take the full 0.11.0 → 0.16.0 jump rather than backporting.** The fix exists only in v0.16.0, and the library does not maintain release branches, so a backport would mean publishing a 0.11.x from a five-version-old tree. The intervening versions (0.12.0 Vite 8/Vitest 4 toolchain, 0.13.0 Tailwind v4, 0.14.0 vue-router v5, 0.15.0 marked v18) are mostly the library's own build tooling, and errand's frontend already runs Tailwind v4, vue-router v5, marked v18 and Vitest 4 — so the majors that could have forced coordinated work are already aligned. The residual risk is presentational, not structural, which is cheaper to verify than a backport is to produce.

**Keep the caret range (`^0.16.0`).** Matches the existing convention and every other dependency in `frontend/package.json`. The lockfile pins the exact resolved version for reproducible CI builds, so a caret costs nothing in determinism. Pinning exactly was considered and rejected: it would make this the only pinned dependency for no stated reason.

**Verify by round-trip against a real server, not by reading the library diff.** The tri-state encoding is invisible in the UI — "inherit", "none" and an empty explicit selection look similar on screen but mean different things to task resolution. Reading the diff confirms intent; only a round-trip confirms the wire format. Verification therefore asserts on persisted values (API response or database row), not on rendered UI state.

**Add the missing requirement to `litellm-mcp-settings-ui`, and only that one.** The spec's Purpose says "viewing and toggling" but no requirement covers the save path, which is precisely the hole the stubbed `save()` slipped through. `task-profile-settings-ui` already enumerates its side under "List field selection UI" and needs no edit — this change restores conformance to it rather than altering it. Adding requirements for all eight restored profile fields was considered and rejected as redundant: they are already covered there and in the library's specs.

**Fix the model-shape defect in two layers, not one.** Normalising on write alone would fix new saves while leaving every profile already stored with the `model_id`-only shape silently broken until someone re-saves it — and the symptom (`OPENAI_MODEL` missing) gives no hint that re-saving is the remedy. Accepting either key at resolution time repairs those rows with no migration and no operator action. A migration was considered and rejected: it would fix stored rows but not protect against any future client that writes only `model_id`, and the read-side tolerance costs one expression. Mirroring on write is still worth doing on its own, because it makes the stored value self-describing and fixes the reverse direction — a legacy `{provider_id, model}` profile previously opened in the editor with a blank model dropdown, since the card reads `model_id`.

**Treat errand's existing frontend tests as the regression signal.** `TaskProfilesPage.test.ts` and `SettingsCapabilityGating.test.ts` mount the real library components rather than stubs, so a breaking change in the bump surfaces as a test failure rather than a runtime surprise. This is why no new errand-side component tests are proposed.

## Risks / Trade-offs

**Tri-state encoding inverted or mis-mapped, silently stripping a task's tools** → The worst failure here is invisible: a profile that reads "inherit" but persists `[]` would leave tasks with no MCP servers and no error anywhere. Verify all three states at both scopes by inspecting the persisted value, and confirm a task created under an affected profile still resolves the expected servers.

**Five versions of accumulated visual change** → Tailwind v4 and the toolchain moves can shift spacing, borders or card envelopes without breaking a single test. Walk the Agent Configuration and Task Profiles pages after the bump; treat layout regressions as in-scope for this change since they arrive with it.

**A save that fails silently, repeating the original class of bug** → The restored card keeps itself dirty on a failed save so the navigation guard still fires. Verify the negative path explicitly (save against a server that rejects), not just the happy path — the original regression was a save that appeared to work.

**Empty selection persisting as `null` or an omitted key** → Would make "disable the last remaining server" a no-op, which reads as the feature being broken again. The library persists `[]` deliberately; assert on this case specifically rather than assuming it from the diff.

**Frontend tests mount real library components** → A failure may reflect an intentional library change rather than a defect. Read the failure before editing the test; update the wrapper test only where the library's new behaviour is correct, and do not weaken an assertion to make a suite pass.

## Migration Plan

No data migration — the fields, settings rows and endpoints already exist and are already populated. Deployment follows the standard errand flow: bump `VERSION` (minor, restores user-facing capability), branch, verify locally with `docker compose -f testing/docker-compose.yml up --build`, PR, confirm the CI image and Helm chart build, then validate the running deployment on Kubernetes before merge.

Rollback is a dependency revert: restore `^0.11.0` and the prior lockfile entry, rebuild. Because no server, schema or stored data changes, a rollback returns the UI to the current regressed state with no cleanup and no risk to profiles configured while v0.16.0 was deployed — those values remain valid and simply become uneditable again.

## Open Questions

- Whether any of the other six restored profile fields (`match_rules`, `max_turns`, `reasoning_effort`, `include_git_skills`, `enabled_plugins`, `skill_ids`) have drifted from errand's current server validation since the Wave 2 extraction. The endpoint validates `reasoning_effort` against `VALID_REASONING_EFFORTS` and `enabled_plugins` via `_validate_enabled_plugins`; round-trip verification should cover these two rather than assume they still line up.
- Whether the visual delta from Tailwind v4 warrants its own follow-up on pages beyond the two touched here. Deferred until the bump is deployed and the wider settings area can be seen.
