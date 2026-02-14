## Decisions

### Decision: Use tweepy library for Twitter API v2
Use the `tweepy` Python library to interact with the Twitter/X API v2. Tweepy handles OAuth 1.0a authentication and provides a clean interface for posting tweets. This avoids writing raw HTTP requests and managing OAuth signatures manually.

### Decision: Credentials via environment variables
Twitter API credentials are passed as environment variables on the backend service:
- `TWITTER_API_KEY` — API key (consumer key)
- `TWITTER_API_SECRET` — API secret (consumer secret)
- `TWITTER_ACCESS_TOKEN` — Access token
- `TWITTER_ACCESS_SECRET` — Access token secret

This follows the same pattern as `OPENAI_API_KEY` and other service credentials. The tool returns an error if credentials are not configured.

### Decision: Tool on the backend MCP server (not the container)
The `post_tweet` tool runs on the backend MCP server, not inside the task runner container. This means:
- Twitter credentials only need to be on the backend service, not passed into containers
- The agent calls the tool via the `content-manager` MCP server (same as `list_skills`/`get_skill`)
- No changes needed to the worker or container configuration

### Decision: Message validation at the tool level
The tool validates the message length (1-280 characters) before calling the Twitter API. Empty messages and messages exceeding 280 characters are rejected with a clear error message, without making an API call.

## Constraints

- Twitter API v2 free tier allows 1,500 tweets per month — no rate limiting implemented in this change, rely on Twitter's API to reject excess posts
- The tool posts plain text tweets only (no media, threads, or replies in this iteration)
