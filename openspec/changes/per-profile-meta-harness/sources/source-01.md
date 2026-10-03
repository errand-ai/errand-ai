Requested official URL: https://code.claude.com/docs/en/headless
Accessed UTC: 2026-10-03T14:54:19.196860+00:00
Title: Run Claude Code programmatically
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# Run Claude Code programmatically
> Use the Agent SDK to run Claude Code programmatically from the CLI, Python, or TypeScript.
The [Agent SDK](/docs/en/agent-sdk/overview) gives you the same tools, agent loop, and context management that power Claude Code. It's available as a CLI for scripts and CI/CD, or as [Python](/docs/en/agent-sdk/python) and [TypeScript](/docs/en/agent-sdk/typescript) packages for full programmatic control.
To run Claude Code in non-interactive mode, pass `-p` with your prompt and the [CLI options](/docs/en/cli-reference) you need:
```bash theme={null}
claude -p "Find and fix the bug in auth.py" --allowedTools "Read,Edit,Bash"
```
This page covers using the Agent SDK via the CLI (`claude -p`). For the Python and TypeScript SDK packages with structured outputs, tool approval callbacks, and native message objects, see the [full Agent SDK documentation](/docs/en/agent-sdk/overview).

## Basic usage
Add the `-p` (or `--print`) flag to any `claude` command to run it non-interactively. Not every [CLI option](/docs/en/cli-reference) combines with `-p`. Claude Code rejects `--bg`, and rejects `--cloud` with a task description, with an error naming the conflict; `--cloud` with a session ID and `-p` instead [queues a message into that cloud session](/docs/en/claude-code-on-the-web#send-follow-ups-from-the-cli) and exits. Options you'll combine with `-p` often include:

...

### Start faster with bare mode
Add `--bare` to reduce startup time by skipping auto-discovery of hooks, skills, custom commands, [subagents](/docs/en/sub-agents), installed plugins, MCP servers, auto memory, and CLAUDE.md. Without it, `claude -p` loads the same [context](/docs/en/how-claude-code-works#the-context-window) an interactive session would, including anything configured in the working directory or `~/.claude`.

...

In bare mode, Claude Code never reads OAuth credentials or the system keychain. For the Anthropic API, set `ANTHROPIC_API_KEY` in the environment, with a key created in the [Claude Console](https://platform.claude.com), or supply an `apiKeyHelper` in the `--settings` JSON. Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry continue to read their own provider credentials as usual.

...

| To load | Use |
| System prompt additions | `--append-system-prompt`, `--append-system-prompt-file` |
| Settings | `--settings <file-or-json>` |
| MCP servers | `--mcp-config <file-or-json>` |
| Custom agents | `--agents <json>` |
| A plugin | `--plugin-dir <path>`, `--plugin-url <url>` |

...

### Background tasks at exit
If Claude starts a background [subagent](/docs/en/sub-agents) or workflow, `claude -p` instead stays open until that work completes, because its result is part of the final output.
By default the wait ends after 10 minutes of continuous idle waiting, so a stuck subagent or workflow can't hold the process open indefinitely. At that point Claude Code stops whatever is still running and drops its partial result. To change the limit, set [`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`](/docs/en/env-vars), or set it to `0` to wait without one.
If Claude starts a [Monitor](/docs/en/tools-reference#monitor-tool) watch during a `claude -p` run, Claude Code waits for the watch until it times out or the ten-minute cap ends the wait, whichever comes first. While it waits, Claude keeps responding to what the watch reports. By default, a watch times out five minutes after Claude starts it.

### Stop a run with SIGTERM
If you stop a `claude -p` run with SIGTERM, for example with `kill` or from a process supervisor, Claude Code exits with code 143. Claude Code leaves the turn that was in progress unfinished and records no result for it. To end the turn instead, send SIGINT, or call the Agent SDK's `interrupt()`, before you stop the process.

...

* **Running a command**: Claude Code records the command as killed in the session.
* **Waiting for an answer to a permission prompt**: if you send SIGTERM to the process, Claude Code leaves the prompt unanswered. If your program closes the session through the Agent SDK, the SDK ends Claude Code's input before sending any signal, and Claude Code cancels the prompt as soon as the input ends.

...

### If the working directory is deleted
If the working directory of a `claude -p` or Agent SDK session is deleted mid-session, the session keeps running. When a turn starts while the directory is missing, Claude Code emits a [warning message](/docs/en/agent-sdk/typescript#sdkinformationalmessage) in `stream-json` output, and shell commands fail until the directory exists again.

...

## Examples
### Pipe data through Claude
Non-interactive mode reads stdin, so you can pipe data in and redirect the response out like any other command-line tool.
This example pipes a build log into Claude and writes the explanation to a file:

...

Both figures are [client-side estimates](/docs/en/agent-sdk/cost-tracking) and can differ from your actual bill.

...

### Stream responses
For programmatic streaming with callbacks and message objects, see [Stream responses in real-time](/docs/en/agent-sdk/streaming-output) in the Agent SDK documentation.

...

#### Follow subagent messages
When you enable either option, Claude Code forwards messages from [subagents at every nesting depth](/docs/en/sub-agents#let-subagents-spawn-their-own-subagents), whether each one was spawned with the Agent tool or started as a [forked skill](/docs/en/skills#run-skills-in-a-subagent). Messages of subagents that a forked skill spawns, and of forked skills started inside a subagent or another forked skill, require Claude Code v2.1.275 or later.

...

#### Read session metadata
See [`SDKSystemMessage`](/docs/en/agent-sdk/typescript#sdksystemmessage) for the capability list.

...

### Turn off permission prompts in unattended runs
Pass `--permission-prompts none` when nobody is available to answer permission prompts, for example in a scheduled job. The flag matters most when your run has a permission host: an Agent SDK app with a [`canUseTool` callback](/docs/en/agent-sdk/user-input), or an MCP tool you pass with [`--permission-prompt-tool`](/docs/en/cli-reference#cli-flags). Without the flag, your run waits for that host to answer each permission request.

...

With `--permission-prompts none`, Claude Code removes the tools that need an answer from a person, such as [`AskUserQuestion`](/docs/en/tools-reference#askuserquestion-tool-behavior), so Claude can't call them. Any [MCP elicitation request](/docs/en/mcp#respond-to-mcp-elicitation-requests) that no [`Elicitation` hook](/docs/en/hooks#elicitation) answers is cancelled.

...

## Next steps
* [Agent SDK quickstart](/docs/en/agent-sdk/quickstart): build your first agent with Python or TypeScript
* [CLI reference](/docs/en/cli-reference): all CLI flags and options
* [GitHub Actions](/docs/en/github-actions): use the Agent SDK in GitHub workflows
* [GitLab CI/CD](/docs/en/gitlab-ci-cd): use the Agent SDK in GitLab pipelines
