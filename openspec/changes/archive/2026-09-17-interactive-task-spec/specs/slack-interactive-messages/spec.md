## ADDED Requirements

### Requirement: Draft actions dispatched from interactions

The interactions endpoint SHALL dispatch `block_actions` payloads whose `action_id` is `task_spec_submit`, `task_spec_run` or `task_spec_cancel`, with `value` set to the draft id, to the Slack intake adapter (see `task-spec-intake`). It SHALL resolve the clicking user's identity before acting, read `task_spec_submit` answers from the payload's `state.values`, and deliver the resulting message by replacing the original through the payload's `response_url`. It SHALL acknowledge with HTTP 200 immediately in all cases, carrying out the action afterwards, because a classifier call can outlast Slack's three-second acknowledgement window.

#### Scenario: Submit answers
- **WHEN** the draft's owner clicks Submit with answers filled in
- **THEN** the answers are passed to `clarify.answer` keyed by question id, and the original message is replaced with the next questions or the confirm card

#### Scenario: Run from a draft message
- **WHEN** the draft's owner clicks Run or Just run it
- **THEN** the draft is confirmed, and the original message is replaced with the task-created confirmation

#### Scenario: Expired or finished draft
- **WHEN** a draft action targets a draft that is expired, confirmed, or abandoned
- **THEN** the original message is replaced with a notice that the draft is no longer active, and no task is created
