# RSS & Twitter Tools

New MCP tools for content discovery (RSS), Twitter engagement (reply, like, retweet), analytics (metrics, timeline), and search.

## Tools Reference

### read_rss_feed

Fetch and parse an RSS or Atom feed.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | required | Feed URL |
| `max_items` | int | 20 | Maximum items to return |
| `since` | str | null | ISO 8601 datetime — only items after this time |

**Returns:** JSON with `feed` (title, link, description) and `items` array (title, link, published, summary). Items sorted newest first.

```
read_rss_feed("https://blog.example.com/feed.xml", max_items=5)
```

### reply_to_tweet

Reply to a tweet by ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tweet_id` | str | required | ID of tweet to reply to |
| `message` | str | required | Reply text (1-280 chars) |

**Returns:** `"Reply posted: <url>"` on success, error message on failure.

```
reply_to_tweet("1234567890", "Great insight! Here's a follow-up thought.")
```

### like_tweet

Like a tweet by ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tweet_id` | str | required | ID of tweet to like |

**Returns:** Confirmation message or error.

### retweet

Retweet a tweet by ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tweet_id` | str | required | ID of tweet to retweet |

**Returns:** Confirmation message or error.

### get_tweet_metrics

Get metrics for a tweet.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tweet_id` | str | required | ID of the tweet |

**Returns:** JSON with `tweet_id`, `text`, `created_at`, and available metrics:
- `public_metrics` — always present (likes, retweets, replies, quotes, bookmarks, impressions)
- `non_public_metrics` — own tweets within 30 days (URL clicks, profile clicks, engagements)
- `organic_metrics` — own tweets within 30 days

### get_my_recent_tweets

Get the authenticated user's recent tweets with metrics.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_results` | int | 10 | Number of tweets (5-100) |

**Returns:** JSON array of tweets with text, timestamps, and all available metrics.

### search_tweets

Search recent tweets (last 7 days). **Requires X API Basic tier.**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search query |
| `max_results` | int | 10 | Number of results (10-100) |

**Returns:** JSON array of tweets with text, author info, timestamps, and public metrics.

## Example Workflows

### RSS-to-Tweet

1. `read_rss_feed("https://blog.example.com/feed.xml", max_items=3)` — get latest posts
2. `read_url(item.link)` — read full article
3. `post_tweet("New post: {title} {link}")` — share it

### Threaded Tweets

1. `post_tweet("Thread: Why Kubernetes security matters 🧵")` — post the opener
2. `reply_to_tweet(tweet_id, "1/ First, always use RBAC...")` — add thread replies
3. `reply_to_tweet(reply_id, "2/ Second, network policies...")` — chain continues

### Analytics Review

1. `get_my_recent_tweets(max_results=20)` — get recent posts
2. `get_tweet_metrics(top_tweet_id)` — drill into top performer
3. Use metrics to inform content strategy

### Discovery & Engagement

1. `search_tweets("kubernetes security", max_results=10)` — find relevant content
2. `like_tweet(tweet_id)` — engage with good posts
3. `reply_to_tweet(tweet_id, "Great point! We wrote about this...")` — join conversations

## Prerequisites & Configuration

### X API Tier Requirements

| Tool | Free Tier | Basic Tier ($100/mo) |
|------|-----------|---------------------|
| reply_to_tweet | Yes | Yes |
| like_tweet | Yes | Yes |
| retweet | Yes | Yes |
| get_tweet_metrics | Yes | Yes |
| get_my_recent_tweets | Yes | Yes |
| **search_tweets** | **No** | **Yes** |

### Required App Permissions

All tools require **Read and Write** permissions on the X developer app. The existing `post_tweet` configuration is sufficient — no additional permissions needed.

### Dependencies

- **feedparser** (`>=6.0,<7`) — RSS/Atom feed parsing for `read_rss_feed`
- **tweepy** (`>=4.14.0`) — Twitter API v2 client (already installed)
- **httpx** — HTTP client for feed fetching (already installed)

### Credentials

Twitter tools use the existing credential flow:
1. Database credentials via platform registry (`load_credentials("twitter", session)`)
2. Environment variable fallback: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`

RSS feed tool requires no credentials — feeds are public HTTP resources.
