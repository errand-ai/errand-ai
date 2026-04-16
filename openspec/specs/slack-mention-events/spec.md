## MODIFIED Requirements

### Requirement: Extracted event processing function
The Slack event processing logic SHALL be extracted from the `POST /slack/events` route handler into a standalone async function that can be called from both the HTTP route and the cloud webhook dispatcher.

#### Scenario: HTTP route calls extracted function
- **WHEN** a Slack event arrives at `POST /slack/events` and passes signature verification
- **THEN** the route handler SHALL call the extracted `process_slack_event(body: bytes)` function
- **THEN** behavior SHALL be identical to the existing implementation (url_verification handling, app_mention processing, duplicate detection)

#### Scenario: Cloud dispatcher calls extracted function
- **WHEN** a Slack events webhook is received via the cloud WebSocket relay
- **THEN** the cloud dispatcher SHALL call `process_slack_event(body: bytes)` directly
- **THEN** signature verification SHALL NOT be performed (already done by errand-cloud)
- **THEN** url_verification events SHALL be ignored (already handled by errand-cloud)

#### Scenario: Function signature
- **WHEN** `process_slack_event` is called
- **THEN** it SHALL accept `body: bytes` as its primary parameter
- **THEN** it SHALL return a JSON-serializable response dict (for HTTP route use) or None (for cloud dispatch where no HTTP response is needed)

### Requirement: Bot-mention stripping resilient to pathological inputs
The regular expression that strips a bot-mention prefix from Slack message text SHALL run in time linear in the input length, even for pathological or adversarially-crafted inputs. The expression SHALL reflect Slack's actual mention syntax (`<@USERID>` or `<@USERID|label>`, where `|` is a field separator that cannot appear inside the label) so that its character classes are unambiguous.

#### Scenario: Regex matches canonical Slack mention
- **WHEN** the bot-mention regex is applied to `<@U01ABCDEFGH> hello`
- **THEN** the match SHALL consume `<@U01ABCDEFGH> ` and `hello` remains after stripping

#### Scenario: Regex matches mention with label
- **WHEN** the bot-mention regex is applied to `<@U01ABCDEFGH|errand-bot> hello`
- **THEN** the match SHALL consume `<@U01ABCDEFGH|errand-bot> ` and `hello` remains after stripping

#### Scenario: Pathological input does not trigger super-linear backtracking
- **WHEN** the bot-mention regex is applied to an input consisting of many repetitions of `<@0|` with no terminating `>` (e.g. `("<@0|" * 10000)`)
- **THEN** the regex operation SHALL complete well within a fixed wall-clock budget (e.g., 200 ms) on a standard CI runner, demonstrating the absence of catastrophic backtracking

#### Scenario: Label may not contain a pipe
- **WHEN** the bot-mention regex is applied to `<@U01|ab|cd>` (a malformed label containing a pipe)
- **THEN** the regex SHALL NOT match as a single canonical mention; the behaviour SHALL be consistent with Slack's actual mention format where `|` is a field separator
