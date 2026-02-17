## ADDED Requirements

### Requirement: Slack user email resolution
The system SHALL provide a function in `backend/platforms/slack/identity.py` that resolves a Slack `user_id` to an email address by calling the Slack Web API `users.info` method. The function SHALL use the Slack bot token from encrypted credentials. The function SHALL return the email from `response.user.profile.email`. If the email is not available (user has no email, or the bot lacks the `users:read.email` scope), the function SHALL return `None`.

#### Scenario: Resolve user with email
- **WHEN** `resolve_slack_email("U01ABCDEF")` is called and the Slack user has email "rob@example.com"
- **THEN** the function returns "rob@example.com"

#### Scenario: User without email
- **WHEN** `resolve_slack_email("U01ABCDEF")` is called and the Slack user has no email configured
- **THEN** the function returns `None`

#### Scenario: Missing email scope
- **WHEN** `resolve_slack_email("U01ABCDEF")` is called and the bot token lacks `users:read.email` scope
- **THEN** the function returns `None` (graceful degradation, not an error)

### Requirement: Email resolution caching
The system SHALL cache Slack user_id → email mappings in an in-memory dict with a 1-hour TTL. Cache hits SHALL return the email without making a Slack API call. Cache misses SHALL trigger a `users.info` API call, and the result (including `None`) SHALL be cached. The cache SHALL be module-level (per-process).

#### Scenario: Cache hit
- **WHEN** `resolve_slack_email("U01ABCDEF")` is called twice within 1 hour
- **THEN** only one Slack API call is made; the second call returns the cached result

#### Scenario: Cache expiry
- **WHEN** `resolve_slack_email("U01ABCDEF")` is called, then called again after 1 hour
- **THEN** a fresh Slack API call is made for the second call

#### Scenario: None values cached
- **WHEN** a user has no email and `resolve_slack_email` is called twice
- **THEN** only one API call is made; `None` is cached and returned on the second call

### Requirement: Slack command user context
Every slash command handler SHALL resolve the invoking user's email via the cached email resolution function and include it in the handler context. The email SHALL be used to populate `created_by` or `updated_by` on task operations. If email resolution returns `None`, the fallback SHALL be the Slack user_id prefixed with "slack:" (e.g., "slack:U01ABCDEF").

#### Scenario: Command with resolved email
- **WHEN** a Slack user with ID "U01ABCDEF" and email "rob@example.com" issues a command
- **THEN** task operations use "rob@example.com" for audit fields

#### Scenario: Command with unresolved email
- **WHEN** a Slack user with ID "U01ABCDEF" and no resolvable email issues a command
- **THEN** task operations use "slack:U01ABCDEF" for audit fields
