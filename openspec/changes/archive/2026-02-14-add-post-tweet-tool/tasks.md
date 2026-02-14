## 1. Backend — Dependencies

- [x] 1.1 Add `tweepy` to `backend/requirements.txt` and install into the backend venv.

## 2. Backend — MCP Tool

- [x] 2.1 Add `post_tweet` tool to `backend/mcp_server.py`. Accepts a `message` parameter (string). Validates length (1-280 chars). Uses `tweepy` with OAuth 1.0a credentials from env vars (`TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`) to post via Twitter API v2. Returns the tweet URL on success or an error message on failure.

## 3. Configuration

- [x] 3.1 Add Twitter env vars to `docker-compose.yml` on the backend service (with `${VAR:-}` defaults so they're optional).
- [x] 3.2 Add Twitter secret env vars to `helm/content-manager/templates/backend-deployment.yaml` (conditional on a `twitter.existingSecret` value, following the Perplexity pattern).

## 4. Tests

- [x] 4.1 Add backend tests for `post_tweet`: valid tweet (mock tweepy), message too long, empty message, credentials not configured, Twitter API error. Update the tool count assertion test.
