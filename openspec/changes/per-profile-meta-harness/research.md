## Research scope and evidence standard

Access date for all upstream sources below: **2026-10-03 UTC** (live `date -u` read). This is documentation/source research, not external harness execution certification. V = verified in official documentation/source retrieved during this review; U = unknown or not established by retrieved evidence; N = explicitly absent/inapplicable. V does NOT mean supported in Errand, security-audited, legally approved or tested on a runtime. Research-only candidates are not selectable until adapter implementation/conformance approval. Some documentation extractions were abbreviated and one retry hit HTTP 429; unknown fields are retained rather than filled from marketing or skill examples. Source inventory records exact requested URLs, extraction provenance, access timestamp and evidence snapshots under `sources/`; the numbered bibliography is generated from `source-ledger.json`.

## Repository / ownership evidence

Repository discovered at `/opt/data/errand-ai`, remote `https://github.com/errand-ai/errand-ai`. The original main worktree was not used for edits (its HEAD was `0fb40781b08b855c204e3cae30996175235dfeeb` and contained unrelated work). Isolated authoring worktree: `/opt/data/profiles/errand-analyst/cache/scratch/errand-meta-harness`, branch `openspec/per-profile-meta-harness`, created from freshly fetched remote default `main` at **`8a833d6e73d6910f838f96e0059ae6209a156c91`**. Remote symbolic HEAD and SHA were read back; no existing source/change files are modified by this proposal.

All following source links are immutable base links:

- [TaskProfile model](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/errand/models.py#L201): per-profile model/provider/MCP/skill/workspace fields; no implemented harness selector. Existing profile CRUD integration is [task_profile_routes.py](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/errand/task_profile_routes.py); MCP profile operations are in [mcp_server.py](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/errand/mcp_server.py). The existing result callback is in [errand/main.py](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/errand/main.py#L3306), with runner output writing at [main.py L2280](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/task-runner/main.py#L2280). The canonical [submit-result-tool](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/specs/submit-result-tool/spec.md) is native in-process, last-call-wins, with completed/needs_input result and string-array questions plus builtin text fallback/nudge. The proposed external result MCP bridge is new integration work; it does not exist at base.
- [TaskManager](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/errand/task_manager.py): profile resolution (`_resolve_profile` near L904), image/runtime startup, global concurrency/advisory locks near L1147, event forwarding (`_live_log_message` near L1124), and output/result collection near L2175. Capability selection must enter before container launch, not at provider lookup.
- [Runtime interface](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/errand/container_runtime.py) and [runner](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/task-runner/main.py): runtime isolation and SDK loop are distinct boundaries. [Dockerfile](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/task-runner/Dockerfile) is a multi-stage distroless runner, not a universally compatible vendor CLI base.
- Canonical specs reviewed: [task-profile-model](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/specs/task-profile-model/spec.md), [task-profile-worker-resolution](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/specs/task-profile-worker-resolution/spec.md), [task-runner-agent](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/specs/task-runner-agent/spec.md), [structured-task-events](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/specs/structured-task-events/spec.md). Additive deltas below preserve the builtin requirements, not replace them with vendor semantics.
- UI ownership evidence: [TaskProfilesPage.vue](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/frontend/src/pages/settings/TaskProfilesPage.vue) imports `TaskProfileListCard` from `@errand-ai/ui-components`; [KanbanBoard.vue](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/frontend/src/components/KanbanBoard.vue) imports `TaskLogViewer`. A change only to local wrappers cannot implement the selector/log behavior.
- Formal owner [CODEOWNERS](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/.github/CODEOWNERS): `* rob.coward@devops-consultants.co.uk`. Component assignments in proposal.md are coordination assignments, not invented formal owners.

## Existing Claude change and branch-only audit

[Current proposal](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/changes/claude-task-runner/proposal.md) and [design/spike](https://github.com/errand-ai/errand-ai/blob/8a833d6e73d6910f838f96e0059ae6209a156c91/openspec/changes/claude-task-runner/design.md) propose headless `claude -p`, per-profile container_image, stored `setup-token`, MCP config translation, skill bridging and restricted runtimes. `openspec list --json` reports active with **0/59** tasks complete; that establishes checklist status, not implementation support.

GitHub REST read of [PR #234](https://github.com/errand-ai/errand-ai/pull/234) confirmed `state: closed`, `merged: true`, merged 2026-07-28T20:50:58Z; head **`64a423aedf1e6f514ce573694158954fe20c7fad`**, merge **`dbd17b0457b30ec343ad0f4fdce5257237e306cd`**. Fetching `refs/pull/234/head` and comparing its Claude directory to base returned no directory diff. Its remote branch `revise-claude-task-runner-change` is gone. At inspection, open PRs were #268, #262, #258, #249, #248, #247, #226, #209, #204 and #197 (dependency updates); none is a Claude harness proposal. This corrects the premise of an open PR without denying the still-active OpenSpec change.

Read-only all-remote-ref Claude-directory comparison after fetch found older copies on:

| Remote branch | Head SHA | Claude directory tree |
|---|---|---|
| fix-cloud-308-redirect-following | 5fd2bf83bf6bee974a5c4adb3958ba35845ee310 | b536dabd24fb7c46ee59371449e95224e03f89f8 |
| fix-dependabot-alerts | 06d82be872c56290165fba2fd022e776cdb4c1b8 | b536dabd24fb7c46ee59371449e95224e03f89f8 |
| shared-cloud-workspace | aa28e3c27fd30bd8dba50cba08f48bdd08a7e2cd | b536dabd24fb7c46ee59371449e95224e03f89f8 |
| task-runner-empty-response-handling | f927ac0b619b5f7720147f2a7bddcca023fb1573 | b536dabd24fb7c46ee59371449e95224e03f89f8 |

Base directory tree: `6d4201e2bc2b9da66f60ae437bbb0e15c08ed742`. The old proposal was explicitly inspected: Node.js image, broad CLI failure fallback, home settings MCP config and OAuth token collection. Main's spike revision adds real Bash/native binaries, narrow post-tool fallback prohibition, HTTP discriminator/registration validation and updated event transformation (12 files, 804 insertions/303 deletions relative to old directory). These are older copies, not a newer unreviewed implementation to import. No remote Claude-named branch was returned by `git ls-remote origin '*claude*'`. Full audit is at this access date; newly created branches require renewed review.

Active existing changes at base: claude-task-runner; context-accounting-correctness; context-ceiling-research; context-usage-observability; memory-status-panel; migrate-mcp-sdk-v2; scope-shared-workspace-access; security-anyio-upgrade-v4-14-2; streaming-voice-transcription. MCP v2, workspace access and context/event changes overlap integration surfaces. Depend on their approved API/security contracts if they land first; do not import their unmerged implementation or rewrite them here.

Relationship recommendation: **supersede old Claude architecture with explicit approval**, not silently extend image auto-detection; preserve spike findings and side-effect caution. The old premise of collecting users' subscription credentials conflicts with current official third-party credential restrictions.[3] New proposal has no implementation dependency on old unchecked tasks and changes no files under that change.

## Harness versus model/provider and ambiguous names

A harness owns the agent loop, tools, context/session management and execution protocol. A model/provider serves inference; an OpenAI-compatible API does not establish those harness capabilities. DeepSeek's API docs describe inference and separately link a real DeepSeek Harness developer preview; thus both identities exist today and must stay separate.[11][12][13]

Microsoft Phi-4 is a model whose model card does not define an external Errand harness.[17]

“phi” could be a typo for Pi, whose official README explicitly calls it an extensible agent harness; the retrieved badlogic/pi-mono URLs redirect to earendil-works/pi and current package is `@earendil-works/pi-coding-agent`.[25]

Do not silently treat `phi` as `pi` or advertise a Phi CLI adapter.

## Capability matrix (upstream evidence, NOT Errand support)

### Control, events, sessions and tools

| Candidate | Headless / API or control protocol | Events / structured result | Session / resume | Tools / MCP |
|---|---|---|---|---|
| Builtin Errand | V: current container + Python SDK loop | V: current stderr events/output contract | U: no external-native resume contract claimed | V: existing native tools and profile MCP resolution |
| Claude Code | V: `-p`, CLI/Agent SDK; non-TTY; bare mode | V: JSON/stream-json + JSON schema; normalized result still required | V: explicit session-id/resume; isolated transcript needed | V: native tools; `--mcp-config`, strict MCP config; server discovery must be checked [1][2] |
| Codex | V: `codex exec --json`; SDK; app-server JSON-RPC stdio alternative | V: JSONL thread/turn/item events; output schema; app-server notifications | V: exec resume or thread/resume; explicit id, no last-session shortcut | V: MCP status/tool interfaces in app-server; dynamicTools experimental [6][7][37] |
| Pi (not Phi) | V: print/JSON, JSONL RPC, TypeScript SDK | V: RPC lifecycle/tool events and final assistant messages; U: native Errand schema guarantee | V: explicit session operations and RPC state; qualification required | V: native filesystem/bash tools and current native MCP; old “no MCP” assumptions are stale [14][15][25] |
| DeepSeek Harness | V: Python SDK over bundled dsh JSON-RPC; distinct Web/ACP compositions | V: SDK final_response and JSONL logs; U: all streaming/usage schema guarantees across profiles | V: explicit session_id and isolated dsh_home; continued durable conversation | V: pluggable tool profiles; U: exact Errand-required MCP transport/catalog behavior in sdk-minimal [12][27] |
| Hermes | V: programmatic library, ACP stdio, TUI gateway JSON-RPC, OpenAI-compatible API | V: ACP message/tool events and API final response; U: schema-guaranteed Errand result/per-turn usage for selected route | V: ACP new/load/resume/fork, API previous_response_id chain | V: full native toolset; MCP docs show stdio/HTTP; forwarding route requires qualification [22][23][38] |
| OpenCode | V: `run`, `serve` HTTP API; ACP also documented | V: event/API surfaces; U: exact versioned JSON result+usage shape until full protocol fixture | V: CLI explicit session/continue/fork | V: local/remote MCP; native tools [19][28][30] |
| Gemini CLI / Antigravity | V: Gemini `-p`, JSON/stream-json; N: old consumer access continuity cannot be assumed | V: init/message/tool_use/tool_result/error/result, token/latency stats | U here: exact supported resume/cancel route for chosen successor | V: Gemini MCP documentation; U: parity in successor [20][21] |
| Microsoft Phi / DeepSeek API alone | N: not harness automation protocols | N: inference responses != harness result/events | N: no harness sessions implied | N: inference capability does not establish native tools/MCP [11][17] |

### Safety, authentication, platforms and accounting

| Candidate | Approvals / cancellation | Auth / licensing | Platform/container constraints | Usage / cost and qualification |
|---|---|---|---|---|
| Claude Code | V: allow/deny tool controls, unattended no-prompts mode, SIGTERM behavior; V docs include background-task exit caveats.[1][2] | V: proprietary binary under Anthropic terms; authorized API/cloud initial path; N: third-party collection/storage of Claude.ai tokens.[3] | V: supported OS requirements; repo spike proves extra Bash/native binary needs; U: each new image/runtime tuple.[4] | V: reported/estimated usage and total_cost_usd; resumed cumulative totals/subagents/crash zeros require careful scope; no zero-cost claim.[5] |
| Codex | V: sandbox/approval policies; app-server approval requests + turn/interrupt; CLI process-tree teardown still needed.[7][9] | V: account or API-key auth documented; Apache-2.0 source; service terms separate.[8][10] | U: nested-container sandbox on target runtime; do not auto-bypass; app-server websocket expressly experimental/unsupported.[7] | V: tokenUsage/turn usage; U: authoritative dollar charge/subscription quota per attempt.[7] |
| Pi | N: per-tool built-in approval guarantee or built-in sandbox; V: RPC abort, extension responses are not containment | V: providers via API/subscription login; MIT harness; service terms separate | V: Node >=22.19, macOS/Linux/Windows installers; entire process+extensions need outer isolation | V: session/message statistics in RPC; U: authoritative invoice/quota; later adapter only [14][16][25] |
| DeepSeek Harness | V: per-session ask/never and approval outcomes; U: selected SDK composition's cancellation contract.[26] | V: MIT per SAFETY; provider API credential; no subscription inference.[13][27] | V: Python >=3.10, native wheel targets Linux x64/arm64, macOS >=14 arm64, Windows x64; SDK launch no system Node; sdk-minimal danger-full-access.[12] | U: authoritative standardized cost/usage across profiles. N: production/security-audited status; developer preview.[13] |
| Hermes | V: ACP permission requests and session cancel; U: API abort semantics for selected deployment.[22][23] | V: upstream MIT license; configured provider/backend credentials; U: individual provider account/service entitlement.[18][35] | V: upstream Linux/macOS/Windows support; U: exact minimum runtime/image tuple; isolate all tools, HOME/config and sessions.[24][36] | U: normalized usage/cost completeness for chosen protocol; OpenAI-compatible API does not prove identical accounting.[18][22] |
| OpenCode | V: allow/ask/deny policies; U here: exact versioned abort endpoint acknowledgment/cleanup guarantee.[29] | V: MIT upstream license; provider auth plus server basic auth; no service entitlement inferred.[28][31] | U: exact native dependencies and Docker/Apple/K8s containment tuple | U: pin v1/v2 API and test event/usage shapes; research-only.[19] |
| Gemini / Antigravity | V: Gemini policy docs; U: successor cancel/approval behavior | V: Gemini Apache-2.0; Google auth/API/Vertex modes; consumer access transition materially affects eligibility.[21][32][34] | U: chosen product runtime/container release tuple | V: Gemini stats; U: successor costs/quota and parity; Google announced consumer cutoff 2026-06-18.[20][21][33] |

## Load-bearing official observations

- Claude legal: “developers may not collect, store, or intermediate Claude.ai credentials or session tokens”; direct end-user sign-in to the unmodified binary is discussed separately. This is a product/auth qualification issue, not solved by a disclaimer or local runtime allowlist.[3]
- Claude SDK usage: resumed calls include session's earlier spend; summing those result totals double-counts. Crash result totals may be zeroed; subagent usage is not represented identically by every usage field. Cost is an estimate, not billing proof.[5]
- Codex app-server: documented stdio JSONL JSON-RPC omits the jsonrpc header; notifications include turn/completed and tokenUsage; thread/resume and turn/interrupt are explicit. The fetched docs warn “WebSocket transport is experimental and unsupported” and some APIs execute outside the sandbox. This proposal prefers exec first and does not expose host-control APIs to tasks.[7]
- Pi security: “Pi can read, change, and execute files with the permissions of the account that started it, and it does not ask for approval before every tool call.” The working directory is not a security boundary; extensions also run with process permissions.[16]
- DeepSeek SAFETY: “It has not undergone a security audit and must not be treated as secure or production-ready.” sdk-minimal has persistent shell and session persistence but lacks normal telemetry/compaction/settings and pins danger-full-access; full web/sdk profiles are different compositions.[12][13]
- Hermes programmatic docs describe distinct ACP, TUI gateway and OpenAI-compatible API protocols; ACP docs list new/load/resume/fork/cancel and permissions. Do not advertise the API as an interchangeable generic model endpoint with guaranteed tool/usage schemas.[18][22][23]
- OpenCode legacy docs and current v2 API coexist. Registry must pin one vendor release/protocol rather than combine old endpoint assumptions with v2; run/serve and MCP are real, production qualification remains open.[19][28][30]
- Google official transition announcement says Gemini CLI will stop serving consumers on 2026-06-18 and successor Antigravity will not have 1:1 parity out of the gate. Existing Gemini headless docs remain evidence of that CLI's protocol, not of continuing consumer access or successor equivalence.[20][21]

## Feasibility and release recommendation

Feasible as a meta-harness with a narrow adapter contract and per-profile persistence. Preserve builtin as default and first qualification target; qualify Claude Code API/cloud headless next and Codex exec independently, using pinned derived images and brokered tool permissions. This is not feasible safely as “choose any installed binary/image and fallback to builtin.” Native protocols are heterogeneous; MCP standardizes tool access, not full harness lifecycle. ACP may reduce future client work but does not erase platform/permission/result differences.

Pi is a credible later adapter if user intended it; Phi alone is not. Hermes and OpenCode are real candidates needing protocol/licensing/image tests. A real DeepSeek Harness now exists, but explicit upstream security-preview warnings make production support premature; keep model/provider use separate. Reassess Gemini vs Antigravity before allocating an adapter. No external harness has been run or conformance-tested in this proposal-only execution. Unknowns and future acceptance work are explicit in design.md/tasks.md.

## Source reproducibility

`source-ledger.json` fixes numeric URL identities. `sources/inventory.json` records original requested URL, UTC access timestamp, retrieved title, snapshot file and whether abbreviated extraction may omit details. Snapshots contain only retrieved official documentation excerpts, not fabricated full pages; use exact URL to revisit. Current source branches/docs are mutable, so release qualification must fetch pinned vendor code/licenses/protocol schemas again. Repo source SHAs above are immutable. No private credentials or user session data are included.

## Sources

[1] https://code.claude.com/docs/en/headless
[2] https://code.claude.com/docs/en/cli-reference
[3] https://code.claude.com/docs/en/legal-and-compliance
[4] https://code.claude.com/docs/en/setup
[5] https://code.claude.com/docs/en/agent-sdk/cost-tracking
[6] https://developers.openai.com/codex/noninteractive
[7] https://developers.openai.com/codex/app-server
[8] https://developers.openai.com/codex/auth
[9] https://learn.chatgpt.com/docs/agent-approvals-security
[10] https://raw.githubusercontent.com/openai/codex/main/LICENSE
[11] https://api-docs.deepseek.com
[12] https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk
[13] https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/SAFETY.md
[14] https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/rpc.md
[15] https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/mcp.md
[16] https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/security.md
[17] https://huggingface.co/microsoft/phi-4
[18] https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
[19] https://opencode.ai/v2/docs/api
[20] https://geminicli.com/docs/cli/headless
[21] https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli
[22] https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
[23] https://hermes-agent.nousresearch.com/docs/developer-guide/acp-internals
[24] https://hermes-agent.nousresearch.com/docs/reference/cli-commands
[25] https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/README.md
[26] https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/approval
[27] https://deepseek-harness.github.io/deepseek-harness/en/guide/providers
[28] https://opencode.ai/docs/cli
[29] https://opencode.ai/docs/permissions
[30] https://opencode.ai/docs/mcp-servers
[31] https://raw.githubusercontent.com/anomalyco/opencode/dev/LICENSE
[32] https://geminicli.com/docs/get-started/authentication
[33] https://geminicli.com/docs/resources/quota-and-pricing
[34] https://raw.githubusercontent.com/google-gemini/gemini-cli/main/LICENSE
[35] https://raw.githubusercontent.com/NousResearch/hermes-agent/main/LICENSE
[36] https://raw.githubusercontent.com/NousResearch/hermes-agent/main/README.md
[37] https://learn.chatgpt.com/docs/non-interactive-mode
[38] https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
