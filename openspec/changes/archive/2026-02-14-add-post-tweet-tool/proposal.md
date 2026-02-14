## Why

The task runner agent needs the ability to post tweets as part of its task execution (e.g., a "create twitter post" skill). Adding a `post_tweet` MCP tool to the backend server lets the agent publish tweets directly, using Twitter/X API credentials managed as environment variables on the backend service.

## What Changes

- Add a `post_tweet` MCP tool to `backend/mcp_server.py` that accepts a message (max 280 characters) and posts it to Twitter/X via the v2 API
- Twitter API credentials (`TWITTER_BEARER_TOKEN`, `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`) read from environment variables on the backend service
- Add `tweepy` to backend dependencies for Twitter API interaction

## Capabilities

### New Capabilities
- `twitter-posting`: MCP tool for posting tweets via the Twitter/X API

### Modified Capabilities
- `mcp-server-endpoint`: Adding a new tool to the existing MCP server

## Impact

- `backend/mcp_server.py` — new `post_tweet` tool function
- `backend/requirements.txt` — add `tweepy` dependency
- `docker-compose.yml` — add Twitter env vars to backend service
- `helm/content-manager/templates/backend-deployment.yaml` — add Twitter secret env vars
