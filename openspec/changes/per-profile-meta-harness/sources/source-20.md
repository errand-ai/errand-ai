Requested official URL: https://geminicli.com/docs/cli/headless
Accessed UTC: 2026-10-03T14:56:47.850315+00:00
Title: Headless mode reference | Gemini CLI
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

Unpaid tier and Google One users: Gemini CLI was replaced by Antigravity
CLI on June 18th, 2026. To learn more, see our [blog post](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli) .
Search
[Feedback](https://github.com/google-gemini/gemini-cli/issues/new?template=website_issue.yml&url=https%3A%2F%2Fgeminicli.com%2Fdocs%2Fcli%2Fheadless%2F) [GitHub GitHub](https://github.com/google-gemini/gemini-cli)
Select theme Dark Light Auto

# Headless mode reference
Copy as Markdown
Headless mode provides a programmatic interface to Gemini CLI, returning
structured text or JSON output without an interactive terminal UI.

## Technical reference
Section titled “Technical reference”
Headless mode is triggered when the CLI is run in a non-TTY environment or when
providing a query with the `-p` (or `--prompt` ) flag.

### Output formats
Section titled “Output formats”
You can specify the output format using the `--output-format` flag.

...

#### Streaming JSON output
* **Event types:**
  + `init` : Session metadata (session ID, model).
  + `message` : User and assistant message chunks.
  + `tool_use` : Tool call requests with arguments.
  + `tool_result` : Output from executed tools.
  + `error` : Non-fatal warnings and system errors.
  + `result` : Final outcome with aggregated statistics and per-model token usage
    breakdowns.

## Exit codes
Section titled “Exit codes”
The CLI returns standard exit codes to indicate the result of the headless
execution:
* `0` : Success.
* `1` : General error or API failure.
* `42` : Input error (invalid prompt or arguments).
* `53` : Turn limit exceeded.

## Next steps
Section titled “Next steps”
* Follow the [Automation tutorial](https://geminicli.com/docs/cli/tutorials/automation) for practical
  scripting examples.
* See the [CLI reference](https://geminicli.com/docs/cli/cli-reference) for all available flags.
Last updated: Mar 10, 2026
This website uses [cookies](https://policies.google.com/technologies/cookies) from Google to deliver and enhance the quality of its services and to analyze
traffic.
I understand.
Google logo Google logo For Developers logo For Developers logo
