## Why

Errand's Twitter/X integration is currently write-only — agents can post tweets but cannot read, engage, or measure performance. Meanwhile, RSS feeds are a common source of content that agents could process (daily digests, tweet generation from articles), but there's no tool for fetching them. Adding RSS feed reading and expanding the Twitter toolset enables content-driven workflows: discover content via RSS, publish via Twitter, then track what resonates via analytics.

## What Changes

- **New MCP tool `read_rss_feed`**: Fetches and parses RSS/Atom feeds, returning structured item data (title, link, published date, summary). Composable with existing `read_url` for full article retrieval.
- **New MCP tool `reply_to_tweet`**: Posts a reply to an existing tweet by ID, enabling threaded conversations and multi-part tweet threads.
- **New MCP tool `like_tweet`**: Likes a tweet by ID.
- **New MCP tool `retweet`**: Retweets a tweet by ID.
- **New MCP tool `get_tweet_metrics`**: Retrieves public, non-public, and organic metrics for a tweet (impressions, likes, retweets, clicks, engagements).
- **New MCP tool `get_my_recent_tweets`**: Fetches the authenticated user's recent tweets with full metrics, enabling performance analysis.
- **New MCP tool `search_tweets`**: Searches recent tweets (last 7 days) by query. Requires X API Basic tier.
- **New Python dependency `feedparser`**: For RSS/Atom feed parsing in `read_rss_feed`.
- **Expanded `TwitterPlatform` class**: New methods for reply, like, retweet, metrics retrieval, timeline fetch, and search — all using existing tweepy library and credential flow.
- **Documentation**: Markdown source document covering all new tools, usage patterns, and example workflows — to be used as source material for updating external docs site and blog content.

## Capabilities

### New Capabilities

- `rss-feed-tool`: MCP tool for on-demand RSS/Atom feed fetching and parsing
- `twitter-engagement-tools`: MCP tools for replying, liking, and retweeting
- `twitter-analytics-tools`: MCP tools for retrieving tweet metrics and recent tweet history
- `twitter-search-tool`: MCP tool for searching recent tweets by query
- `tools-documentation`: Markdown documentation source covering new tools, workflows, and examples

### Modified Capabilities

- `twitter-posting`: Adding reply capability (via `in_reply_to_tweet_id`) to existing tweet creation flow
- `platform-abstraction`: Extending `TwitterPlatform` with new methods beyond `post()`

## Impact

- **Backend** (`errand/platforms/twitter.py`): New methods on `TwitterPlatform` for engagement, analytics, search
- **Backend** (`errand/mcp_server.py`): 7 new MCP tool definitions following existing patterns
- **Dependencies** (`errand/requirements.txt`): Add `feedparser` package
- **X API tier**: `search_tweets` requires Basic tier ($100/mo); all other tools work on Free tier
- **X app permissions**: Existing Read+Write permissions sufficient for all new tools
- **No database changes**: No new models or migrations required
- **No frontend changes**: Tools are backend-only, exposed via MCP
