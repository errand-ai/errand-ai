## ADDED Requirements

### Requirement: get_tweet_metrics MCP tool
The MCP server SHALL expose a `get_tweet_metrics` tool that accepts `tweet_id` (str, required). The tool SHALL retrieve the tweet's text, creation date, and all available metrics using `TwitterPlatform.get_metrics()`. The tool SHALL return a JSON string containing `tweet_id`, `text`, `created_at`, and metric objects: `public_metrics` (always present), `non_public_metrics` (present for own tweets within 30 days), and `organic_metrics` (present for own tweets within 30 days). Fields that are unavailable SHALL be omitted from the response rather than set to null.

#### Scenario: Get metrics for own recent tweet
- **WHEN** the agent calls `get_tweet_metrics` with the ID of a tweet posted by the authenticated user within the last 30 days
- **THEN** the tool returns JSON with `public_metrics` (impressions, likes, retweets, replies, quotes, bookmarks), `non_public_metrics` (url_link_clicks, user_profile_clicks, engagements), and `organic_metrics`

#### Scenario: Get metrics for own older tweet
- **WHEN** the agent calls `get_tweet_metrics` with the ID of a tweet posted by the authenticated user more than 30 days ago
- **THEN** the tool returns JSON with only `public_metrics` (non-public and organic metrics are unavailable beyond 30 days)

#### Scenario: Get metrics for another user's tweet
- **WHEN** the agent calls `get_tweet_metrics` with the ID of a tweet posted by a different user
- **THEN** the tool returns JSON with only `public_metrics`

#### Scenario: Tweet not found
- **WHEN** the agent calls `get_tweet_metrics` with a non-existent tweet_id
- **THEN** the tool returns an error message

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `get_tweet_metrics` and no Twitter credentials are available
- **THEN** the tool returns an error: "Twitter API credentials not configured"

### Requirement: get_my_recent_tweets MCP tool
The MCP server SHALL expose a `get_my_recent_tweets` tool that accepts `max_results` (int, optional, default 10, max 100). The tool SHALL retrieve the authenticated user's recent tweets with full metrics using `TwitterPlatform.get_my_tweets()`. The tool SHALL return a JSON string containing an array of tweet objects, each with `tweet_id`, `text`, `created_at`, `public_metrics`, and (where available) `non_public_metrics` and `organic_metrics`.

#### Scenario: Get recent tweets with default limit
- **WHEN** the agent calls `get_my_recent_tweets` with no arguments
- **THEN** the tool returns JSON with up to 10 recent tweets, each including metrics

#### Scenario: Get recent tweets with custom limit
- **WHEN** the agent calls `get_my_recent_tweets` with `max_results=5`
- **THEN** the tool returns JSON with up to 5 recent tweets

#### Scenario: No tweets found
- **WHEN** the agent calls `get_my_recent_tweets` and the authenticated user has no tweets
- **THEN** the tool returns a JSON string with an empty array

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `get_my_recent_tweets` and no Twitter credentials are available
- **THEN** the tool returns an error: "Twitter API credentials not configured"

### Requirement: TwitterPlatform analytics methods
The `TwitterPlatform` class SHALL implement `get_metrics(tweet_id: str, **kwargs)` and `get_my_tweets(max_results: int, **kwargs)` methods. `get_metrics()` SHALL use tweepy to fetch the tweet with `tweet_fields=["public_metrics", "non_public_metrics", "organic_metrics", "created_at", "text"]`. `get_my_tweets()` SHALL use `client.get_users_tweets()` for the authenticated user with the same tweet_fields.

#### Scenario: get_metrics returns full metric set
- **WHEN** `TwitterPlatform.get_metrics()` is called for an own recent tweet
- **THEN** the returned dict includes public_metrics, non_public_metrics, and organic_metrics

#### Scenario: get_my_tweets returns timeline with metrics
- **WHEN** `TwitterPlatform.get_my_tweets()` is called with max_results=10
- **THEN** it returns a list of up to 10 tweet dicts with metrics included
