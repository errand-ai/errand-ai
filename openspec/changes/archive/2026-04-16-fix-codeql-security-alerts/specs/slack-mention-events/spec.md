## ADDED Requirements

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
