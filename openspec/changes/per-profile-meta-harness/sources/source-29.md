Requested official URL: https://opencode.ai/docs/permissions
Accessed UTC: 2026-10-03T14:55:12.648741+00:00
Title: Permissions | OpenCode
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# Permissions | OpenCode
URL: https://opencode.ai/docs/permissions

Permissions | OpenCode

# Permissions

Control which actions require approval to run.

OpenCode uses the `permission` config to decide whether a given action should run automatically, prompt you, or be blocked.

As of `v1.1.1`, the legacy `tools` boolean config is deprecated and has been merged into `permission`. The old `tools` config is still supported for backwards compatibility.

## Actions

Each permission rule resolves to one of:

- `"allow"` — run without approval
- `"ask"` — prompt for approval
- `"deny"` — block the action

## Auto mode

Start OpenCode with `--auto` to automatically approve permission requests that are not explicitly denied.

Terminal window

opencode --auto

You can also use auto mode with `opencode run`.

Terminal window

opencode run --auto "Refactor this module"

Explicit `"deny"` rules are still enforced. Auto mode only changes requests that would otherwise ask for approval.

In the TUI, open the command palette and select Enable auto-approve permissions or Disable auto-approve permissions to change modes. When auto mode is active, the prompt displays a muted `auto` indicator next to the current agent.

## Configuration

You can set permissions globally (with `*`), and override specific tools.

opencode.json

{

 "$schema": "https://opencode.ai/config.json",

 "permission": {

 "*": "ask",

 "bash": "allow",

 "edit": "deny"

 }

}

You can also set all permissions at once:

opencode.json

{

 "$schema": "https://opencode.ai/config.json",

 "permission": "allow"

}

## Granular Rules (Object Syntax)

For most permissions, you can use an object to apply different actions based on the tool input.

opencode.json

{

 "$schema": "https://opencode.ai/config.json",

 "permission": {

 "bash": {

 "*": "ask",

 "git *": "allow",

 "npm *": "allow",

 "rm *": "deny",

 "grep *": "allow"

 },

 "edit": {

 "*": "deny",

 "packages/web/src/content/docs/*.mdx": "allow"

 }

 }

}

Rules are evaluated by pattern match, with the last matching rule winning. A common pattern is to put the catch-all `"*"` rule first, and more specific rules after it.

### Wildcards

Permission patterns use simple wildcard matching:

- `*` matches zero or more of any character
- `?` matches exactly one character
- All other characters match literally

### Home Directory Expansion

You can use `~` or `$HOME` at the start of a pattern to reference your home directory. This is particularly useful for `external_directory` rules.

- `~/projects/*` -> `/Users/username/projects/*`
- `$HOME/projects/*` -> `/Users/username/projects/*`
- `~` -> `/Users/username`

### External Directories

Use `external_directory` to allow tool calls that touch paths outside the working directory where OpenCode was started. This applies to any tool that takes a path as input (for example `read`, `edit`, `glob`, `grep`, and many `bash` commands).

Home expansion (like `~/...`) only affects how a pattern is written. It does not make an external path part of the current workspace
