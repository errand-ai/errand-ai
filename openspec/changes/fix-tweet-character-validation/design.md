## Context

The `post_tweet` MCP tool in `errand/mcp_server.py` validates tweet length with `len(message) > 280`. This is incorrect because Twitter automatically shortens all URLs to 23-character t.co links. A tweet with a 100-character URL only uses 23 characters of the limit for that URL, but our validation counts all 100.

This causes the automated tweet-publisher workflow to reject every tweet containing a URL, even when they're well within Twitter's actual limit.

## Goals / Non-Goals

**Goals:**
- Accurately validate tweet length by accounting for Twitter's t.co URL shortening
- Keep the validation server-side in the `post_tweet` tool (fail fast before hitting the Twitter API)
- Maintain the existing tool interface — no changes to parameters or return format

**Non-Goals:**
- Full Twitter character counting (weighted characters, emoji handling, CJK character weighting) — standard `len()` is sufficient for non-URL text for our use case
- Fetching the current t.co URL length from Twitter's API at runtime — use the well-known constant of 23

## Decisions

**1. Extract a `twitter_character_count(text)` helper function**

Rationale: Keeps the logic testable in isolation without needing to mock the full `post_tweet` pipeline. The function takes the full tweet text, finds URLs via regex, and replaces each URL's length contribution with 23 characters.

Alternative considered: Inline the logic in `post_tweet`. Rejected because it makes testing harder and the logic is non-trivial enough to warrant a named function.

**2. Use regex URL detection, not a URL parsing library**

Pattern: `https?://\S+` — matches `http://` or `https://` followed by non-whitespace characters.

Rationale: This matches Twitter's own URL detection behavior closely enough. Twitter detects URLs by protocol prefix, not by validating domain structure. A full URL parsing library (urllib, validators) would add complexity without improving accuracy for our use case.

**3. Use 23 as the t.co URL length constant**

Twitter's t.co shortened URL length has been 23 characters since 2018 (both http and https URLs). This is a stable, well-documented value. Define it as `TWITTER_TCO_URL_LENGTH = 23` for clarity.

## Risks / Trade-offs

- [Risk] Twitter could change the t.co URL length → Mitigation: This hasn't changed since 2018 and is a single constant to update. The value is also documented in Twitter's API docs.
- [Risk] Regex URL detection doesn't perfectly match Twitter's URL detection → Mitigation: For our use case (Medium article links and similar), `https?://\S+` is sufficient. Edge cases (bare domains like `example.com` without protocol) are not relevant to our tweet drafts.
- [Trade-off] We're not implementing full Twitter weighted character counting → Acceptable because our tweets are English text with standard ASCII, URLs, and emoji. The difference between `len()` and Twitter's weighted counting is negligible for our content.
