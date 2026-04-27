## ADDED Requirements

### Requirement: search_tweets MCP tool
The MCP server SHALL expose a `search_tweets` tool that accepts `query` (str, required) and `max_results` (int, optional, default 10, max 100). The tool SHALL search recent tweets (last 7 days) using `TwitterPlatform.search()`. The tool SHALL return a JSON string containing an array of tweet objects, each with `tweet_id`, `text`, `created_at`, `author_id`, `author_username`, and `public_metrics`. The tool SHALL require X API Basic tier or higher. If the API returns a 403 Forbidden error, the tool SHALL return a clear error message indicating that search requires Basic tier access.

#### Scenario: Search for tweets by keyword
- **WHEN** the agent calls `search_tweets` with query "kubernetes security"
- **THEN** the tool returns JSON with matching tweets from the last 7 days, each with text, author info, and metrics

#### Scenario: Search with max_results limit
- **WHEN** the agent calls `search_tweets` with query "errand" and max_results=5
- **THEN** the tool returns at most 5 matching tweets

#### Scenario: No results found
- **WHEN** the agent calls `search_tweets` with a query that matches no recent tweets
- **THEN** the tool returns a JSON string with an empty array

#### Scenario: Insufficient API tier
- **WHEN** the agent calls `search_tweets` and the X API returns 403 Forbidden
- **THEN** the tool returns an error: "Twitter search requires X API Basic tier or higher. Current credentials do not have search access."

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `search_tweets` and no Twitter credentials are available
- **THEN** the tool returns an error: "Twitter API credentials not configured"

### Requirement: TwitterPlatform search method override
The `TwitterPlatform` class SHALL override the `search(query: str, **kwargs)` method from the Platform base class. The method SHALL use `client.search_recent_tweets(query=query, max_results=max_results, tweet_fields=["created_at", "public_metrics", "text"], expansions=["author_id"], user_fields=["username"])` to search and return results with author usernames resolved from the expansions.

#### Scenario: search returns tweets with author info
- **WHEN** `TwitterPlatform.search()` is called with a query
- **THEN** the returned list includes tweet data with `author_username` resolved from user expansions

#### Scenario: search handles 403 gracefully
- **WHEN** `TwitterPlatform.search()` is called and the API returns 403
- **THEN** a descriptive error is raised indicating the tier requirement
