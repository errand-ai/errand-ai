## MODIFIED Requirements

### Requirement: App mention event handling

The backend SHALL handle Slack `event_callback` payloads with event type `app_mention` at the existing `POST /slack/events` endpoint. The endpoint SHALL verify the Slack request signature using the existing `verify_slack_request` dependency. Upon receiving a valid `app_mention` event, the backend SHALL return HTTP 200 immediately and process the event asynchronously: it SHALL start a clarification draft (see `task-spec-intake`) from the mention text and post the Block Kit draft message in the mention's thread. The task is created only when the mentioning user confirms the draft.

#### Scenario: Valid app_mention creates a task
- **WHEN** Slack sends an `event_callback` with event type `app_mention` and text `<@U12345> Write a blog post`, and the mentioning user clicks Run on the draft message posted in the thread
- **THEN** the endpoint returns HTTP 200, and a task is created from the resolved spec with `created_by` set to the mentioning user's resolved email and a `slack` tag

#### Scenario: Mention with no text after bot ID
- **WHEN** Slack sends an `app_mention` event where the text is only `<@U12345>` with no additional text
- **THEN** no draft or task is created and no message is posted (silently ignored)

#### Scenario: Mention text extraction
- **WHEN** the event text is `<@U12345> Deploy the new version to staging`
- **THEN** the bot mention prefix `<@U12345>` is stripped and the remaining text `Deploy the new version to staging` is trimmed and used as the draft's input

#### Scenario: URL verification still works
- **WHEN** Slack sends a `url_verification` challenge request
- **THEN** the endpoint returns the challenge value (existing behavior preserved)

#### Scenario: Draft message posted in thread
- **WHEN** a valid `app_mention` with text arrives
- **THEN** the draft message is posted with `thread_ts` set to the mention's `ts`, and the draft records the channel and message timestamp
