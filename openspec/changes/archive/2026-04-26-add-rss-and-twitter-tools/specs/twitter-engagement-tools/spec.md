## ADDED Requirements

### Requirement: reply_to_tweet MCP tool
The MCP server SHALL expose a `reply_to_tweet` tool that accepts `tweet_id` (str, required) and `message` (str, required, 1-280 characters). The tool SHALL post a reply to the specified tweet using `TwitterPlatform.reply()`. The tool SHALL return the reply tweet's URL on success or an error message on failure. Character counting SHALL use the same `twitter_character_count()` function as `post_tweet` to account for t.co URL shortening.

#### Scenario: Reply to a tweet
- **WHEN** the agent calls `reply_to_tweet` with a valid tweet_id and message
- **THEN** the tool posts a reply and returns the reply tweet URL

#### Scenario: Build a thread
- **WHEN** the agent calls `post_tweet` then calls `reply_to_tweet` with the returned tweet's ID
- **THEN** a thread is created with the original tweet and the reply

#### Scenario: Reply message too long
- **WHEN** the agent calls `reply_to_tweet` with a message exceeding 280 characters
- **THEN** the tool returns an error indicating the character limit was exceeded

#### Scenario: Reply to non-existent tweet
- **WHEN** the agent calls `reply_to_tweet` with a tweet_id that does not exist
- **THEN** the tool returns the Twitter API error message

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `reply_to_tweet` and no Twitter credentials are available
- **THEN** the tool returns an error: "Twitter API credentials not configured"

### Requirement: like_tweet MCP tool
The MCP server SHALL expose a `like_tweet` tool that accepts `tweet_id` (str, required). The tool SHALL like the specified tweet using `TwitterPlatform.like()`. The tool SHALL return a success message on success or an error message on failure.

#### Scenario: Like a tweet
- **WHEN** the agent calls `like_tweet` with a valid tweet_id
- **THEN** the tool likes the tweet and returns "Liked tweet <tweet_id>"

#### Scenario: Like an already-liked tweet
- **WHEN** the agent calls `like_tweet` on a tweet already liked by the authenticated user
- **THEN** the tool returns a success message (Twitter API is idempotent for likes)

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `like_tweet` and no Twitter credentials are available
- **THEN** the tool returns an error: "Twitter API credentials not configured"

### Requirement: retweet MCP tool
The MCP server SHALL expose a `retweet` tool that accepts `tweet_id` (str, required). The tool SHALL retweet the specified tweet using `TwitterPlatform.retweet()`. The tool SHALL return a success message on success or an error message on failure.

#### Scenario: Retweet a tweet
- **WHEN** the agent calls `retweet` with a valid tweet_id
- **THEN** the tool retweets the tweet and returns "Retweeted tweet <tweet_id>"

#### Scenario: Retweet an already-retweeted tweet
- **WHEN** the agent calls `retweet` on a tweet already retweeted by the authenticated user
- **THEN** the tool returns the Twitter API error message (Twitter does not allow duplicate retweets)

#### Scenario: Twitter credentials not configured
- **WHEN** the agent calls `retweet` and no Twitter credentials are available
- **THEN** the tool returns an error: "Twitter API credentials not configured"

### Requirement: TwitterPlatform engagement methods
The `TwitterPlatform` class SHALL implement `reply(tweet_id: str, message: str, **kwargs)`, `like(tweet_id: str, **kwargs)`, and `retweet(tweet_id: str, **kwargs)` methods. Each method SHALL accept a `credentials` dict via kwargs and use `tweepy.Client` for the API call. `reply()` SHALL use `create_tweet(text=message, in_reply_to_tweet_id=tweet_id)`. `like()` SHALL use `client.like(tweet_id)`. `retweet()` SHALL use `client.retweet(tweet_id)`.

#### Scenario: reply method creates reply tweet
- **WHEN** `TwitterPlatform.reply()` is called with valid credentials, tweet_id, and message
- **THEN** it calls `client.create_tweet(text=message, in_reply_to_tweet_id=tweet_id)` and returns a `PostResult` with the reply URL

#### Scenario: like method likes tweet
- **WHEN** `TwitterPlatform.like()` is called with valid credentials and tweet_id
- **THEN** it calls `client.like(tweet_id=tweet_id)` and returns True on success

#### Scenario: retweet method retweets
- **WHEN** `TwitterPlatform.retweet()` is called with valid credentials and tweet_id
- **THEN** it calls `client.retweet(tweet_id=tweet_id)` and returns True on success
