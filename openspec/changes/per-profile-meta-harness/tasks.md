## 1. Review gates and coordinated ownership (Team Leader / Analyst)

- [ ] 1.1 Approve explicit supersession of claude-task-runner architecture; reconcile its 0/59 task list without silently editing/archiving it.
- [ ] 1.2 Clarify phi (Pi versus Microsoft Phi); keep ambiguous identity unavailable.
- [ ] 1.3 Obtain legal/security approval for Claude binary distribution, authorized-user API/cloud billing, and no third-party collection of Claude.ai tokens.
- [ ] 1.4 Agree component owners and separate ui-components/optional desktop proposals before their implementation.
- [ ] 1.5 Reconcile MCP v2, workspace-scope and context-accounting/event active changes with freshly reviewed main; avoid importing unrelated changes.
- [ ] 1.6 Ratify credential ownership, runtime tuples, retention/TTL, budget/concurrency and cancellation timeout defaults.

## 2. Persistence, API and compatibility (Backend)

- [ ] 2.1 Add expand/backfill migration for profile harness_id=builtin and non-secret harness_config; define safe guarded downgrade.
- [ ] 2.2 Extend profile CRUD/clone/MCP operations and validate schema, ids, availability, model bindings and principal-authorized references.
- [ ] 2.3 Preserve omitted update fields and legacy clients; sanitize export/import and require destination credential rebinding.
- [ ] 2.4 Implement authenticated harness discovery, disabled-entry reasons and secret-free task attempt provenance/usage reads.
- [ ] 2.5 Add round-trip tests for create/edit/restart/clone/import/MCP and two different profiles; reject null, phi, arbitrary commands/images and raw secrets.
- [ ] 2.6 Verify migration with existing profiles, default/tag resolution and mixed-version workers; prevent old workers claiming external attempts.

## 3. Registry and builtin boundary (Backend / Runner)

- [ ] 3.1 Define typed adapter operations, release manifests, config/capability schemas, errors and immutable attempt snapshot.
- [ ] 3.2 Implement administrator registry and required/optional negotiation; reject unqualified version/runtime/architecture/auth tuples.
- [ ] 3.3 Extract a behavior-preserving builtin adapter without changing SDK compaction/stall/output/tools/provider behavior.
- [ ] 3.4 Golden-test builtin output, stderr events, usage, retry ceilings, result callback/file behavior and all current tool resolution.
- [ ] 3.5 Define external plugin/skill gaps and prohibit implicit project/global executable configuration or runtime installation.

## 4. Isolation and task-scoped tools (Security / Worker / Runner)

- [ ] 4.1 Implement isolated attempt HOME/XDG/vendor state/workspace and qualified non-root resource/filesystem/network containment.
- [ ] 4.2 Implement scoped MCP broker authorization, short-lived task credentials, required-server/catalog handshake and denied admin/eval tools.
- [ ] 4.3 Validate one owner per tool; disable duplicate shell/filesystem/service tools and recursive harness delegation.
- [ ] 4.4 Add encrypted credential-reference lifecycle, minimal injection, subprocess scrubbing, rotation/revocation and redacted audit.
- [ ] 4.5 Attack-test cross-profile HOME/session/workspace access, host sockets, privileged paths, environment leakage, direct denied MCP calls and malicious hooks/extensions.
- [ ] 4.6 Test missing MCP registration, wrong HTTP discriminator, unsupported transport and unauthorized catalog before first model/tool execution.
- [ ] 4.7 Test unattended required approval denial and fail-closed native sandbox initialization; never auto-enable blanket bypass.

## 5. Lifecycle, results, events and accounting (Worker / Runner)

- [ ] 5.1 Implement fenced leases/state transitions, result candidates, current Errand schema validation and one authoritative finalization.
- [ ] 5.2 Test duplicate callback/file result, conflicting candidate, early result followed by failed exit, missing result, malformed JSON and stale worker completion.
- [ ] 5.3 Implement bounded prepare/start/wall/interrupt/kill/cleanup and worker-crash orphan reconciliation; test whole descendant process/container shutdown.
- [ ] 5.4 Implement error taxonomy and side-effect-aware retry budget; suppress replay after native tool/broker mutation or incomplete evidence and disclose manual retry effects.
- [ ] 5.5 Test preflight transient retry, auth/policy/result non-retryable outcomes, quota/backoff bounds and absence of cross-harness fallback.
- [ ] 5.6 Implement normalized legacy-compatible event mapping, native call ids, bounded redacted unknown events, terminal reliability and existing replay exclusions.
- [ ] 5.7 Test concurrent out-of-order tool results, malformed/truncated streams, huge events, redaction and old viewers.
- [ ] 5.8 Implement reported/estimated/unavailable usage with scope/completeness and cumulative-session deduplication; test fork/reset/crash/subagent accounting gaps.
- [ ] 5.9 Implement outcome/latency/capability/retry/cancel/usage-completeness metrics and bounded-label traces; verify RBAC/retention and no secrets/hidden reasoning.
- [ ] 5.10 Implement global/profile/credential concurrency limits and fairness; test no session multiwriter or account-quota oversubscription.

## 6. Claude Code adapter qualification (Runner / Security)

- [ ] 6.1 Select exact vendor release/checksum/protocol fixtures and digest-pinned Linux Docker amd64/arm64 derived images with real Bash; review licensing/auth distribution.
- [ ] 6.2 Implement headless CLI adapter with explicit approved config/MCP, structured native result or scoped submit_result candidate and successful terminal validation.
- [ ] 6.3 Record tested auth mode and capabilities; qualify signal/background cleanup, quota/auth errors, stream transformations and estimated usage scopes.
- [ ] 6.4 Exercise real pinned binary smoke/conformance tests inside each proposed tuple; approve only passing tuples, no subscription-token card.
- [ ] 6.5 Verify inactive model aliases are not silently mapped to unsupported Claude models and builtin remains unaffected.

## 7. Codex adapter qualification (Runner / Security)

- [ ] 7.1 Select exact Codex release/license/checksum/image and JSONL/output-schema fixtures; choose exec initial path, not unqualified websocket service.
- [ ] 7.2 Implement and test exec headless adapter, explicit native session references, scoped MCP and supported binding validation.
- [ ] 7.3 Qualify native sandbox or explicitly approved outer sandbox on target container kernels; fail closed on namespace/platform failure.
- [ ] 7.4 Exercise real pinned binary protocol/result/cancel/auth/usage conformance in each enabled tuple and publish evidence.
- [ ] 7.5 Keep app-server approvals/stdin protocol as separately reviewed future route, excluding host-control/experimental APIs from task reach.

## 8. Shared UI and deployment rollout (UI Components / Errand / Desktop)

- [ ] 8.1 Implement separate harness/model controls and credential/capability/availability disclosure in ui-components under its approved proposal.
- [ ] 8.2 Implement native call-id viewer pairing, additive event fallback and honest unavailable usage in shared components.
- [ ] 8.3 Integrate versioned shared package and local wrapper/API tests in Errand; verify old-client omission compatibility.
- [ ] 8.4 Publish registry/image CI qualification with per-runtime/architecture/auth evidence; keep Apple/Kubernetes disabled until independently qualified.
- [ ] 8.5 Roll out expand/readers -> writers -> builtin adapter -> opt-in Claude -> independent Codex; test rollback drains/fences attempts and preserves profile intent.
- [ ] 8.6 If desktop auth/runtime work is enabled, implement only through a separately approved desktop proposal; no implicit host-home mounting.

## 9. Later research-gated adapters and resume (Analyst / Runner)

- [ ] 9.1 Re-research and propose Pi/Hermes/OpenCode adapters with exact license, protocol/image/auth and approval/cost evidence; no phi alias.
- [ ] 9.2 Reassess DeepSeek Harness developer-preview security/maturity and profile composition; do not equate DeepSeek API with harness support.
- [ ] 9.3 Reassess Gemini versus Antigravity consumer/service transition and protocol parity before choosing an adapter.
- [ ] 9.4 Propose and qualify explicit resume storage/TTL/encryption/authorization/version/policy/catalog compatibility and session cost accounting before enabling resume.
- [ ] 9.5 Test cross-tenant/stale/missing sessions and exclusive lease; prohibit implicit last-session recovery or replay guarantees.
- [ ] 9.6 Separately specify future interactive approvals with RBAC, correlated request ids, TTL, cancellation and audit if product needs it.

## 10. Verification and documentation handoff (Analyst / Team Leader)

- [ ] 10.1 Run repository strict OpenSpec validation and full adapter/API/migration/security/UI tests on implementation; publish conformance artifacts per enabled tuple.
- [ ] 10.2 Verify complete acceptance coverage and builtin regression parity before marking implementation complete; proposal validation alone is not runtime evidence.
- [ ] 10.3 After implementation verification, review errand.sh documentation and hand scoped updates through Team Leader to Website agent.
- [ ] 10.4 Document only actually qualified harnesses, separate models/providers, auth limits, unavailable telemetry, migration/rollback and unresolved phi interpretation.

All checklist entries intentionally remain unimplemented. Research and proposal authoring are deliverables of this branch, not completion of implementation tasks.
