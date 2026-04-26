## 1. Dependencies and Setup

- [x] 1.1 Add `feedparser>=6.0,<7` to `errand/requirements.txt`
- [x] 1.2 Install feedparser into the errand venv and verify import works
- [x] 1.3 Bump `VERSION` file (minor version increment — new features, backwards-compatible)

## 2. RSS Feed Tool

- [x] 2.1 Implement `read_rss_feed` MCP tool in `errand/mcp_server.py` — accepts `url`, `max_items` (default 20), `since` (optional ISO 8601). Uses httpx to fetch, feedparser to parse. Returns JSON with `feed` metadata and `items` array (title, link, published, summary). Handles errors (timeout, non-feed content, fetch failure).

## 3. TwitterPlatform Engagement Methods

- [x] 3.1 Add `reply(tweet_id, message, **kwargs)` method to `TwitterPlatform` — uses `client.create_tweet(text=message, in_reply_to_tweet_id=tweet_id)`, returns `PostResult`
- [x] 3.2 Add `like(tweet_id, **kwargs)` method to `TwitterPlatform` — uses `client.like(tweet_id=tweet_id)`, returns bool
- [x] 3.3 Add `retweet(tweet_id, **kwargs)` method to `TwitterPlatform` — uses `client.retweet(tweet_id=tweet_id)`, returns bool

## 4. TwitterPlatform Analytics Methods

- [x] 4.1 Add `get_metrics(tweet_id, **kwargs)` method to `TwitterPlatform` — fetches tweet with `tweet_fields=["public_metrics", "non_public_metrics", "organic_metrics", "created_at", "text"]`, returns dict with available metrics
- [x] 4.2 Add `get_my_tweets(max_results, **kwargs)` method to `TwitterPlatform` — uses `client.get_me()` then `client.get_users_tweets()` with metrics fields, returns list of tweet dicts

## 5. TwitterPlatform Search Method

- [x] 5.1 Override `search(query, **kwargs)` on `TwitterPlatform` — uses `client.search_recent_tweets()` with `tweet_fields`, `expansions=["author_id"]`, `user_fields=["username"]`. Resolves author usernames from expansions. Handles 403 with clear tier-requirement error message.

## 6. Update TwitterPlatform Capabilities

- [x] 6.1 Update `TwitterPlatform.info()` to declare capabilities `{POST, MEDIA, ANALYTICS, SEARCH}`

## 7. MCP Engagement Tools

- [x] 7.1 Implement `reply_to_tweet` MCP tool in `errand/mcp_server.py` — validates message length with `twitter_character_count()`, loads credentials, calls `platform.reply()`, returns reply URL or error
- [x] 7.2 Implement `like_tweet` MCP tool in `errand/mcp_server.py` — loads credentials, calls `platform.like()`, returns success message or error
- [x] 7.3 Implement `retweet` MCP tool in `errand/mcp_server.py` — loads credentials, calls `platform.retweet()`, returns success message or error

## 8. MCP Analytics Tools

- [x] 8.1 Implement `get_tweet_metrics` MCP tool in `errand/mcp_server.py` — loads credentials, calls `platform.get_metrics()`, returns JSON with tweet data and all available metric categories
- [x] 8.2 Implement `get_my_recent_tweets` MCP tool in `errand/mcp_server.py` — loads credentials, calls `platform.get_my_tweets()`, returns JSON array of tweets with metrics

## 9. MCP Search Tool

- [x] 9.1 Implement `search_tweets` MCP tool in `errand/mcp_server.py` — loads credentials, calls `platform.search()`, returns JSON array of tweets with author info and metrics. Catches 403 and returns tier-requirement error.

## 10. Extract Twitter Credential Loading

- [x] 10.1 Extract the Twitter credential loading logic from `post_tweet` into a shared helper function (e.g. `_load_twitter_credentials()`) to avoid duplicating it across 7 tools

## 11. Tests

- [x] 11.1 Write tests for `read_rss_feed` tool — valid RSS feed, valid Atom feed, max_items limiting, since filtering, missing dates, fetch failure, invalid feed content, timeout
- [x] 11.2 Write tests for `reply_to_tweet` tool — successful reply, message too long, missing credentials
- [x] 11.3 Write tests for `like_tweet` tool — successful like, missing credentials
- [x] 11.4 Write tests for `retweet` tool — successful retweet, missing credentials
- [x] 11.5 Write tests for `get_tweet_metrics` tool — own recent tweet (all metrics), older tweet (public only), other user's tweet (public only), missing credentials
- [x] 11.6 Write tests for `get_my_recent_tweets` tool — returns tweets with metrics, empty timeline, missing credentials
- [x] 11.7 Write tests for `search_tweets` tool — results found, no results, 403 tier error, missing credentials
- [x] 11.8 Write tests for TwitterPlatform new methods — reply, like, retweet, get_metrics, get_my_tweets, search

## 12. Documentation

- [x] 12.1 Create `docs/rss-and-twitter-tools.md` — tool reference for all 7 new tools (description, parameters, return format, examples), composite workflow examples (RSS-to-tweet, threaded tweets, analytics review, discovery and engagement), prerequisites and configuration (API tiers, permissions, feedparser dependency)
