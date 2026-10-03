Requested official URL: https://developers.openai.com/codex/noninteractive
Accessed UTC: 2026-10-03T14:54:19.154416+00:00
Title: Non-interactive mode – Codex | OpenAI Developers
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# Non-interactive mode
Use `codex exec` to run Codex in scripts and CI
Non-interactive mode lets you run Codex from scripts (for example, continuous integration (CI) jobs) without opening the interactive TUI.
You invoke it with `codex exec` .
For flag-level details, see `codex exec` .

...

## Basic usage
While `codex exec` runs, Codex streams progress to `stderr` and prints only the final agent message to `stdout` . This makes it straightforward to redirect or pipe the final result:
```
codex  exec  "generate release notes for the last 10 commits"  |  tee  release-notes.md
```

...

## Make output machine-readable
Item types include agent messages, reasoning, command executions, file changes, MCP tool calls, web searches, and plan updates.
Sample JSON stream (each line is a JSON object):

...

## Authenticate in CI
### Use API key auth (recommended)
* Set `CODEX_API_KEY` as a secret environment variable for the job.
* Keep prompts and tool output in mind: they can include sensitive code or data.
To use a different API key for a single run, set `CODEX_API_KEY` inline:
