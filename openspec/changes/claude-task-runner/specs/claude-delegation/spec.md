## ADDED Requirements

### Requirement: Claude delegation is attempted once
When the `claude` CLI is present on PATH and `CLAUDE_CODE_OAUTH_TOKEN` is set, the task-runner SHALL execute the task via `claude -p` instead of the standard Python agent loop. Delegation SHALL be attempted at most once per task attempt. When either precondition is absent, the standard agent loop SHALL run directly with no claude attempt and no `claude_fallback` event.

#### Scenario: Claude runs the task
- **WHEN** the container starts with `claude` on PATH and `CLAUDE_CODE_OAUTH_TOKEN` set
- **THEN** the task is executed via `claude -p` and no standard agent loop run occurs

#### Scenario: Claude not on PATH
- **WHEN** the container starts without `claude` on PATH (for example, the default task-runner image)
- **THEN** the standard Python agent loop is used directly and no `claude_fallback` event is emitted

#### Scenario: Token not set
- **WHEN** the container starts with `claude` on PATH but no `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** the standard Python agent loop is used directly and no `claude_fallback` event is emitted

### Requirement: Fallback is restricted to failures before the first tool call
Failure SHALL be determined from the terminal `result` event, NOT from the process exit status — `claude -p` exits 0 even when authentication fails. The task-runner SHALL treat a run as failed when the process produced no `result` event, or when the `result` event has `is_error: true`.

On failure, the task-runner SHALL emit a `claude_fallback` event whose `data` contains `reason` (string), `terminal_reason` (string or null), and `fell_back` (boolean). It SHALL then:

- if no `tool_call` event was emitted during the run, execute the task using the standard Python agent loop with `fell_back: true`;
- otherwise, fail the task with `fell_back: false` and a `TaskRunnerOutput` of `{"status": "failed", "result": "<reason>"}`.

Re-running a task that has already invoked tools risks repeating external side effects (sent mail, posted messages, pushed commits), so a mid-run failure is a task failure rather than a retry.

#### Scenario: Auth failure before any tool call falls back
- **WHEN** the `result` event reports `is_error: true` with `result: "Not logged in · Please run /login"` and no `tool_call` event was emitted
- **THEN** a `claude_fallback` event with `fell_back: true` is emitted and the standard Python agent loop executes the task

#### Scenario: Exit code 0 is not treated as success
- **WHEN** the claude process exits with status 0 but the `result` event has `is_error: true`
- **THEN** the run is treated as failed

#### Scenario: Failure after a tool call fails the task
- **WHEN** the `result` event reports `is_error: true` after at least one `tool_call` event was emitted
- **THEN** a `claude_fallback` event with `fell_back: false` is emitted, the standard agent loop does NOT run, and the task output is `{"status": "failed", "result": "<reason>"}`

#### Scenario: No result event at all
- **WHEN** the claude process terminates without emitting a `result` event and no `tool_call` event was emitted
- **THEN** a `claude_fallback` event with `fell_back: true` is emitted and the standard agent loop executes the task

### Requirement: Claude invocation
The task-runner SHALL invoke the CLI with `subprocess.Popen`, `cwd` set to `/workspace`, and the following arguments:

- `-p <user prompt>` — the task prompt read from `USER_PROMPT_PATH`
- `--output-format stream-json --verbose` — NDJSON event stream on stdout
- `--append-system-prompt <system prompt>` — the contents of `SYSTEM_PROMPT_PATH`
- `--permission-mode bypassPermissions` — the container is the sandbox; there is no interactive user to approve tool calls
- `--disallowedTools <list>` — the excluded-tool deny list (see the tool exclusion requirement)
- `--mcp-config <path> --strict-mcp-config` — the translated MCP config (see `claude-mcp-config`)
- `--effort <level>` — when `REASONING_EFFORT` is set
- `--model <model>` — when the resolved profile names a Claude model

`--include-partial-messages` SHALL NOT be passed: token-level deltas would multiply event volume without changing what the log viewer renders.

#### Scenario: Invocation includes required flags
- **WHEN** the task-runner invokes claude for a task
- **THEN** the argument list includes `-p`, `--output-format stream-json`, `--verbose`, `--append-system-prompt`, `--permission-mode bypassPermissions`, `--disallowedTools`, `--mcp-config`, and `--strict-mcp-config`

#### Scenario: Working directory
- **WHEN** claude is invoked
- **THEN** the subprocess `cwd` is `/workspace`

#### Scenario: Reasoning effort forwarded
- **WHEN** `REASONING_EFFORT=high` is set in the environment
- **THEN** the argument list includes `--effort high`

#### Scenario: Partial messages not requested
- **WHEN** the task-runner invokes claude
- **THEN** the argument list does not include `--include-partial-messages`

### Requirement: Excluded MCP tools are denied
The task-runner SHALL pass every tool in `EXCLUDED_CATALOG_TOOLS` to `--disallowedTools`, namespaced as `mcp__errand__<tool>`, using that set as the single source of truth. These eval and profile-administration tools are withheld from the default agent by the tool catalog, which Claude Code does not use; without an explicit deny list Claude would see all of them through the shared MCP key.

#### Scenario: Deny list covers the excluded set
- **WHEN** the task-runner builds the claude invocation
- **THEN** `--disallowedTools` contains `mcp__errand__clone_task_profile`, `mcp__errand__delete_task_profile`, `mcp__errand__search_tasks`, `mcp__errand__start_eval_run`, `mcp__errand__record_eval_result`, `mcp__errand__finish_eval_run`, and `mcp__errand__get_eval_run`

#### Scenario: Excluded tool call is refused
- **WHEN** the model attempts to call `mcp__errand__delete_task_profile` during a delegated run
- **THEN** the call does not reach the errand MCP server and the attempt is reported on the `result` event's `permission_denials`

### Requirement: Skills bridged into the Claude project directory
Before invoking the CLI, the task-runner SHALL copy each skill directory under `/workspace/skills/` to `/workspace/.claude/skills/<name>/`. Claude Code discovers project skills from `.claude/skills` relative to its working directory; errand installs them at `/workspace/skills/`, where Claude Code does not look. Errand skills already use the `SKILL.md` format with name/description frontmatter, so the bridge is a copy and not a translation.

#### Scenario: Skills bridged
- **WHEN** `/workspace/skills/gws-gmail/SKILL.md` exists and claude is invoked
- **THEN** `/workspace/.claude/skills/gws-gmail/SKILL.md` exists before the CLI starts

#### Scenario: Skill subdirectories preserved
- **WHEN** a skill directory contains `scripts/` and `references/` subdirectories
- **THEN** those subdirectories are present under the bridged skill directory

#### Scenario: No skills installed
- **WHEN** `/workspace/skills/` is absent or empty
- **THEN** the CLI is invoked normally and no `.claude/skills` directory is required

### Requirement: Stream event transformation
The task-runner SHALL read the CLI's stdout as NDJSON and emit errand structured events on stderr according to this mapping:

| Claude event | Errand event |
|---|---|
| `system` with `subtype: "init"` | `agent_start` with `data.agent = "claude"` |
| `assistant` message, `text` content block | `thinking` with `data.text` |
| `assistant` message, `thinking` content block | `reasoning` with `data.text` |
| `assistant` message, `tool_use` content block | `tool_call` with `data.tool` and `data.args` |
| `user` message, `tool_result` content block | `tool_result` with `data.tool`, `data.output`, `data.length` |
| `result` | `agent_end` with `data.output` |
| any other event, including `system` with `subtype: "api_retry"` | `raw` with `data.line` set to the original line |

`tool_result` output SHALL be truncated to 500 characters with the untruncated length in `length`, matching the existing protocol. The tool name for a `tool_result` SHALL be resolved by matching `tool_use_id` against the preceding `tool_use` block.

#### Scenario: Init mapped to agent_start
- **WHEN** the CLI emits `{"type": "system", "subtype": "init", ...}`
- **THEN** stderr contains `{"type": "agent_start", "data": {"agent": "claude"}}`

#### Scenario: Tool use mapped to tool_call
- **WHEN** an `assistant` message contains a `tool_use` block named `Bash` with input `{"command": "ls"}`
- **THEN** stderr contains `{"type": "tool_call", "data": {"tool": "Bash", "args": {"command": "ls"}}}`

#### Scenario: Tool result mapped and attributed
- **WHEN** a `user` message contains a `tool_result` block whose `tool_use_id` matches a preceding `tool_use` named `Bash`
- **THEN** stderr contains a `tool_result` event with `tool` `Bash`, the result text in `output`, and the untruncated length in `length`

#### Scenario: Assistant text mapped to thinking
- **WHEN** an `assistant` message contains a `text` block
- **THEN** stderr contains `{"type": "thinking", "data": {"text": "<text>"}}`

#### Scenario: Result mapped to agent_end
- **WHEN** the CLI emits the terminal `result` event
- **THEN** stderr contains an `agent_end` event whose `data.output` is the resolved TaskRunnerOutput object

#### Scenario: API retry mapped to raw
- **WHEN** the CLI emits `{"type": "system", "subtype": "api_retry", ...}`
- **THEN** stderr contains a `raw` event carrying the original line

#### Scenario: Unknown event mapped to raw
- **WHEN** the CLI emits an event type not in the mapping
- **THEN** stderr contains a `raw` event carrying the original line

#### Scenario: Malformed line does not abort the run
- **WHEN** a stdout line is not valid JSON
- **THEN** a `raw` event carrying the line is emitted and transformation continues

### Requirement: Result delivery reuses the existing output contract
On a successful run the task-runner SHALL construct `TaskRunnerOutput` with `status: "completed"` and `result` taken from the `result` event's `result` field, and SHALL deliver it through the same path as the standard agent loop — written to stdout, to `/output/result.json` via `write_output_file()`, and POSTed via `post_result_callback()`.

If the model called errand's `submit_result` MCP tool during the run, that payload SHALL take precedence, including `status: "needs_input"` with `questions`.

#### Scenario: Result event becomes the task output
- **WHEN** the `result` event carries `result: "The bug was fixed"` and `submit_result` was not called
- **THEN** the delivered output is `{"status": "completed", "result": "The bug was fixed", "questions": []}`

#### Scenario: submit_result takes precedence
- **WHEN** the model called `submit_result` with `status: "needs_input"` and two questions
- **THEN** the delivered output carries `status: "needs_input"` and both questions, not the `result` event text

#### Scenario: Output reaches the callback
- **WHEN** a delegated run completes and `RESULT_CALLBACK_URL` is configured
- **THEN** the output is POSTed to the callback URL exactly as the standard agent loop would

### Requirement: Permission denials are surfaced
When the terminal `result` event contains a non-empty `permission_denials` array, the task-runner SHALL emit an `error` event naming each denied tool. A run in which every tool call was denied otherwise completes with `terminal_reason: "completed"` and exit 0, presenting as a successful task that did no work.

#### Scenario: Denials reported
- **WHEN** the `result` event lists a denial for tool `Bash`
- **THEN** stderr contains an `error` event whose message names `Bash` as denied

#### Scenario: No denials, no error event
- **WHEN** the `result` event has an empty `permission_denials` array
- **THEN** no denial-related `error` event is emitted

### Requirement: Runner safety nets that do not apply are documented
The delegated path does not run the task-runner's agent loop, so the following do not apply: context compaction, the stall guard (`stall_nudge` / `stall_detected`), XML and Harmony tool-call recovery, the file-mutation queue and file tools, per-command timeouts, and the mid-task Google Workspace token refresh built into `execute_command`. The repository SHALL document this parity gap in `task-runner/CUSTOM_IMAGES.md` or an equivalent operator-facing document, and the task-runner SHALL NOT emit stall or compaction events during a delegated run.

Long delegated tasks can therefore exhaust a Google Workspace access token with no recovery, and a looping model is bounded only by Claude Code's own limits.

#### Scenario: No stall events during delegation
- **WHEN** a delegated run repeats an identical tool call many times
- **THEN** no `stall_nudge` or `stall_detected` events are emitted

#### Scenario: Parity gap documented
- **WHEN** an operator reads the custom-images documentation
- **THEN** it lists the runner features unavailable on the claude delegation path
