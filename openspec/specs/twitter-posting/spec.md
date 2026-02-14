## Requirements

### Requirement: post_tweet MCP tool
The backend MCP server SHALL expose a `post_tweet` tool that accepts a `message` parameter (string, 1-280 characters) and posts it as a tweet via the Twitter/X API v2. The tool SHALL return the posted tweet's URL on success or an error message on failure. The tool SHALL require valid MCP API key authentication.

#### Scenario: Post a valid tweet
- **WHEN** the agent calls `post_tweet` with message "Hello from content-manager!"
- **THEN** the tool posts the tweet and returns the tweet URL (e.g., "Tweet posted: https://x.com/user/status/123456")

#### Scenario: Message too long
- **WHEN** the agent calls `post_tweet` with a message exceeding 280 characters
- **THEN** the tool returns an error: "Message exceeds 280 character limit (got N characters)"

#### Scenario: Empty message
- **WHEN** the agent calls `post_tweet` with an empty message
- **THEN** the tool returns an error: "Message cannot be empty"

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `post_tweet` and Twitter API credentials are not set in environment variables
- **THEN** the tool returns an error: "Twitter API credentials not configured"

#### Scenario: Twitter API error
- **WHEN** the agent calls `post_tweet` and the Twitter API returns an error (e.g., rate limit, auth failure)
- **THEN** the tool returns an error message including the Twitter API error details
