## Why

Errand currently owns one OpenAI Agents SDK execution loop. Choosing a model/provider does not choose an agent harness. Users need a persisted, independent choice per task profile without losing existing behavior, tools, or result semantics. External harnesses can provide their own agent loops, but their protocols, tool ownership, credentials, permission systems, and accounting differ substantially. A generic executable selector or opportunistic CLI detection cannot safely provide this feature.

Repository baseline: fresh remote default `main`, commit `8a833d6e73d6910f838f96e0059ae6209a156c91`, inspected 2026-10-03. See `research.md` for SHA-linked source evidence, active-change/branch audit, official documentation, and capability qualifications.

The active `claude-task-runner` change has 0/59 tasks complete at this baseline. Its revision PR [#234](https://github.com/errand-ai/errand-ai/pull/234) is merged, not currently open; head `64a423aedf1e6f514ce573694158954fe20c7fad`, merge `dbd17b0457b30ec343ad0f4fdce5257237e306cd`. Older branch copies are superseded by that revision. This proposal requests explicit Team Leader approval to **supersede** the Claude-only image-selection, stored subscription-token, implicit delegation/fallback architecture. It reuses that change's spike evidence, MCP registration checks, event mapping lessons and side-effect caution, not an implemented dependency. No existing change is edited or archived here. Until approved, both are proposals and neither authorizes implementation.

## What Changes

- Persist `harness_id` and schema-versioned non-secret harness configuration on each TaskProfile; existing and omitted values resolve to `builtin`. Retain all built-in model/provider resolution, classification, scheduling, tools and output behavior.
- Introduce an administrator-controlled adapter registry with immutable version/image pins, runtime qualification, typed capabilities, and fail-closed negotiation. A model name, image, API endpoint, or installed executable is never a harness identity.
- Separate task orchestration from adapter-owned agent loops. Define isolated lifecycle, task-scoped MCP broker, tool ownership, authoritative results, normalized events, usage and errors, bounded cancellation/retry, and opt-in qualified resume.
- Deliver the built-in adapter first, then qualify Claude Code headless and Codex exec independently. API-key/approved cloud credentials are the initial Claude route; do not collect Claude.ai subscription tokens. No automatic cross-harness fallback.
- Research-gated later adapters: Pi (if that is what “phi” means), Hermes, OpenCode, and the real DeepSeek Harness developer preview. Microsoft Phi and DeepSeek API remain models/providers, not harness entries. Gemini/Antigravity requires separate product-transition qualification.
- Provide capability discovery and selection in profile APIs, MCP profile operations, and shared profile UI, with clear unsupported/unavailable/experimental states, independent model controls and capability-gap warnings.
- Add migration, immutable execution snapshots, observability, conformance tests, rollout gates and rollback that preserves profile intent.

## Capabilities

### New Capabilities
- `harness-registry`: adapter identity, version pins, capabilities and runtime qualification.
- `harness-execution`: lifecycle, cancellation/retry/resume, results, usage, isolation and concurrent attempts.
- `harness-security`: credential scopes, enforceable permissions, MCP brokering and single-owner tools.

### Modified Capabilities
- `task-profile-model`: persisted per-profile harness selection and non-secret configuration.
- `task-profile-worker-resolution`: independent harness resolution and immutable launch snapshots.
- `task-profile-settings-ui`: distinct harness/model selectors and qualification disclosure.
- `structured-task-events`: additive normalized external events with legacy compatibility and honest missing telemetry.

## Impact

Owning repository: `errand-ai/errand-ai`; CODEOWNERS assigns `*` to `rob.coward@devops-consultants.co.uk`. Component assignments below are proposed responsibilities, not claims of separate CODEOWNERS entries:

- Errand Backend/Worker agent: `errand/models.py`, profile CRUD/MCP routes, Alembic, `task_manager.py`, adapter registry, attempt/result persistence, permission broker, `container_runtime.py`, image CI and Helm runtime policy.
- Task Runner agent (Errand component): `task-runner/` built-in boundary, external supervisors, protocol normalization, task-scoped tool integration and conformance fixtures.
- UI Components agent: actual `TaskProfileListCard` and `TaskLogViewer` implementation in `errand-ai/ui-components`, requiring a separate coordinated proposal before implementation. Errand frontend imports those components; local wrapper tests/dependency integration belong here.
- Desktop agent: `errand-ai/errand-desktop` credential provisioning/runtime qualification only if desktop delivery is enabled; separate proposal required, not assumed implemented here.
- Team Leader: decide supersession, security/auth boundaries, release cohorts and cross-repository sequencing.
- Website agent via Team Leader AFTER implementation verification: errand.sh profile selection, harness/model terminology, capability matrix, credential setup, limits and migration/rollback docs. This proposal does not update the website.

No implementation, blanket support promise, arbitrary command/image execution UI, consumer subscription resale, global harness switch, archive or deployment is in this deliverable.
