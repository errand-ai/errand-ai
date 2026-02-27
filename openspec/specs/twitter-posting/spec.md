## Purpose

MCP tool for posting tweets via the Twitter/X API v2 through the platform abstraction layer.

## Requirements

### Requirement: post_tweet MCP tool
The backend MCP server SHALL expose a `post_tweet` tool that accepts a `message` parameter (string, 1-280 characters) and posts it as a tweet via the Twitter/X API v2. The tool SHALL delegate to `TwitterPlatform.post()` from the platform registry instead of calling the Tweepy API directly. The tool SHALL return the posted tweet's URL on success or an error message on failure. The tool SHALL require valid MCP API key authentication.

#### Scenario: Post a valid tweet
- **WHEN** the agent calls `post_tweet` with message "Hello from errand!"
- **THEN** the tool delegates to `TwitterPlatform.post()` and returns the tweet URL

#### Scenario: Message too long
- **WHEN** the agent calls `post_tweet` with a message exceeding 280 characters
- **THEN** the tool returns an error: "Message exceeds 280 character limit (got N characters)"

#### Scenario: Empty message
- **WHEN** the agent calls `post_tweet` with an empty message
- **THEN** the tool returns an error: "Message cannot be empty"

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `post_tweet` and no Twitter credentials exist in the database or environment variables
- **THEN** the tool returns an error: "Twitter API credentials not configured"

#### Scenario: Twitter API error
- **WHEN** the agent calls `post_tweet` and the Twitter API returns an error
- **THEN** the tool returns an error message including the Twitter API error details

### Requirement: TwitterPlatform class
The system SHALL provide a `TwitterPlatform` class in `backend/platforms/twitter.py` that extends the `Platform` base class. The class SHALL declare capabilities `{POST, MEDIA}`. The `verify_credentials()` method SHALL make a test API call (e.g., `client.get_me()`) to validate the credentials. The `post()` method SHALL create a tweet via the Tweepy `Client`.

#### Scenario: TwitterPlatform info
- **WHEN** `TwitterPlatform.info()` is called
- **THEN** it returns `PlatformInfo` with `id="twitter"`, `label="Twitter/X"`, capabilities `{POST, MEDIA}`, and credential_schema defining `api_key`, `api_secret`, `access_token`, `access_secret`

#### Scenario: Verify valid credentials
- **WHEN** `verify_credentials()` is called with valid Twitter API credentials
- **THEN** it returns `True`

#### Scenario: Verify invalid credentials
- **WHEN** `verify_credentials()` is called with invalid credentials
- **THEN** it returns `False`

### Requirement: Twitter env var fallback
The `TwitterPlatform` SHALL check for encrypted credentials in the database first. If no DB credentials exist, it SHALL fall back to reading `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, and `TWITTER_ACCESS_SECRET` environment variables. This ensures backwards compatibility during migration from env vars to DB credentials.

#### Scenario: DB credentials used when available
- **WHEN** Twitter credentials exist in the PlatformCredential table and env vars are also set
- **THEN** the DB credentials are used (DB takes precedence)

#### Scenario: Env var fallback when no DB credentials
- **WHEN** no Twitter credentials exist in the DB but env vars are set
- **THEN** the env var credentials are used

#### Scenario: Neither DB nor env vars configured
- **WHEN** no Twitter credentials exist in DB and env vars are not set
- **THEN** operations return an error indicating credentials are not configured
