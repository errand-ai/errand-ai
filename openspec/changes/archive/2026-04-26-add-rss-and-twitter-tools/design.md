## Context

Errand's Twitter/X integration currently supports a single operation: posting tweets via `TwitterPlatform.post()` and the `post_tweet` MCP tool. The platform uses tweepy's `Client` class (Twitter API v2) with OAuth 1.0a user-context authentication (consumer key/secret + access token/secret). Credentials are loaded via `load_credentials("twitter", session)` with env var fallback.

The existing `read_url` and `web_search` MCP tools demonstrate the pattern for content retrieval tools — no platform dependency, always available, return JSON strings.

The email poller shows the pattern for content ingestion (IMAP → task creation), but this change focuses on on-demand tools only — background RSS polling is a future phase.

## Goals / Non-Goals

**Goals:**
- Add an `read_rss_feed` MCP tool for on-demand RSS/Atom feed parsing
- Expand Twitter tools to support engagement (reply, like, retweet), analytics (metrics, timeline), and discovery (search)
- Follow existing patterns: platform registry for Twitter, standalone for RSS
- All new tools work with the existing credential flow — no new secrets or config needed
- Create documentation source material for external docs site and blog

**Non-Goals:**
- Background RSS feed polling / TaskGenerator(type="rss") — future phase
- RSS feed deduplication / state tracking — not needed for on-demand tool
- `follow_user` tool — deprioritised, lower impact
- `post_thread` high-level tool — `reply_to_tweet` composes to achieve this
- Changes to the frontend UI
- New database models or migrations
- Media upload / image attachment on tweets

## Decisions

### Decision 1: RSS tool is standalone, not platform-based

The `read_rss_feed` tool follows the `read_url` pattern — a standalone HTTP fetch tool with no platform dependency. It does not require credentials, is always available, and returns structured JSON.

**Why not a platform?** RSS feeds are public HTTP resources. There's no credential flow, no write operations, no platform-specific state. Making it a platform would add abstraction without value. The `read_url` tool established this pattern already.

**Alternative considered:** Creating an `RSSPlatform` class — rejected as over-abstraction for a stateless HTTP GET.

### Decision 2: Twitter tools added as methods on TwitterPlatform, exposed as individual MCP tools

New Twitter operations (reply, like, retweet, metrics, timeline, search) are added as methods on `TwitterPlatform` in `errand/platforms/twitter.py`. Each gets a corresponding MCP tool in `errand/mcp_server.py` following the `post_tweet` pattern.

**Why on TwitterPlatform?** Keeps the credential loading path consistent — all Twitter operations go through `load_credentials("twitter", session)` with env var fallback. The platform registry provides the entry point.

**Why not extend the Platform base class?** Operations like `like()`, `retweet()`, and `get_metrics()` are Twitter-specific concepts. Adding them to the abstract base class would force empty implementations on every other platform. Instead, these are concrete methods on `TwitterPlatform` only.

**Alternative considered:** A separate `TwitterClient` utility class — rejected because it would bypass the platform registry and duplicate credential loading logic.

### Decision 3: Use feedparser library for RSS parsing

The `read_rss_feed` tool uses the `feedparser` Python library for RSS/Atom parsing. It handles RSS 0.9x, 1.0, 2.0, Atom 0.3, and Atom 1.0 feeds, normalises date formats, and handles encoding edge cases.

**Why feedparser?** It's the de facto standard Python RSS library (mature, well-tested, handles real-world feed quirks). The alternative — manual XML parsing with `lxml` or `xml.etree` — would require reimplementing feed format detection, date normalisation, and encoding handling.

### Decision 4: Tweet metrics return all three metric categories

`get_tweet_metrics` requests `public_metrics`, `non_public_metrics`, and `organic_metrics` via tweepy's `tweet_fields` parameter. For the authenticated user's own tweets, all three are returned. For other users' tweets, only `public_metrics` is available — the tool returns what's available without erroring.

**Why all three?** Non-public metrics (URL clicks, profile clicks, engagements) are the most actionable for content strategy. Organic metrics help distinguish promoted vs organic performance. Requesting all and returning what's available is simpler than requiring the caller to specify.

### Decision 5: search_tweets documents Basic tier requirement

The `search_tweets` tool uses tweepy's `search_recent_tweets()` which requires X API Basic tier ($100/mo). The tool handles the case where the API returns a 403 (insufficient tier) gracefully with a clear error message.

**Why include it?** Search enables discovery workflows that make the other engagement tools (like, reply) much more useful. Without search, the agent can only interact with tweets it already has IDs for.

### Decision 6: Documentation as markdown source file

A single markdown document (`docs/rss-and-twitter-tools.md`) serves as the canonical source for all external documentation. It covers tool reference, example workflows, and configuration. This file is then used as source material for:
- Updating the errand-sh docs site (`Integrations/twitter.mdx`)
- Writing a blog post
- Social media announcements

**Why a single source?** Prevents drift between documentation targets. Write once in the project, adapt for each channel externally.

## Risks / Trade-offs

**X API rate limits** → All new tools are subject to Twitter's rate limits (varies by endpoint and tier). Tools return the Twitter error message directly, which includes rate limit info. No client-side rate limiting is implemented — the agent handles retries via its own reasoning. If rate limiting becomes a problem, a shared rate limiter could be added later.

**Non-public metrics 30-day window** → Twitter only provides non-public and organic metrics for tweets from the last 30 days. The tool returns whatever metrics are available — older tweets only get public metrics. The tool does not error, it simply returns fewer fields.

**search_tweets tier gating** → If the user's X developer account is on Free tier, `search_tweets` will fail with a 403. The error message should clearly indicate this is a tier issue, not a credential issue. This is documented in the tool's docstring and in the documentation source file.

**feedparser dependency** → Adding a new Python dependency. feedparser is mature (2002+), pure Python, no transitive dependencies. Low risk. Pin to a specific version in requirements.txt.

**Tweepy method availability** → All methods used (`like()`, `retweet()`, `search_recent_tweets()`, `get_users_tweets()`) are stable tweepy v2 Client methods. No experimental or deprecated APIs.
