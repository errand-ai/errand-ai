# Tweet Character Counting

Validate tweet length using Twitter's actual counting rules (t.co URL shortening: all URLs count as 23 characters regardless of their actual length).

## Requirements

### Requirement: Tweet length validation accounts for t.co URL shortening
The `post_tweet` tool SHALL calculate tweet length by replacing each URL's character count with 23 characters (Twitter's t.co shortened URL length) before comparing against the 280-character limit. URLs are detected by matching `https?://\S+` patterns in the message text.

#### Scenario: Tweet with URL is within limit after t.co adjustment
- **WHEN** a tweet contains body text of 200 characters and a URL of 90 characters (290 total raw characters)
- **THEN** the system SHALL calculate the effective length as 223 characters (200 + 23) and allow the tweet to be posted

#### Scenario: Tweet with URL exceeds limit even after t.co adjustment
- **WHEN** a tweet contains body text of 270 characters and a URL of 50 characters
- **THEN** the system SHALL calculate the effective length as 293 characters (270 + 23) and reject the tweet with an error message showing the effective character count

#### Scenario: Tweet with multiple URLs
- **WHEN** a tweet contains body text of 200 characters and two URLs of 80 characters each (360 total raw characters)
- **THEN** the system SHALL calculate the effective length as 246 characters (200 + 23 + 23) and allow the tweet to be posted

#### Scenario: Tweet without URLs
- **WHEN** a tweet contains only text with no URLs and is 250 characters long
- **THEN** the system SHALL calculate the effective length as 250 characters and allow the tweet to be posted

#### Scenario: Tweet without URLs exceeds limit
- **WHEN** a tweet contains only text with no URLs and is 300 characters long
- **THEN** the system SHALL reject the tweet with an error message showing 300 characters

### Requirement: Error message reports effective character count
When a tweet is rejected for exceeding the character limit, the error message SHALL report the effective character count (after t.co adjustment), not the raw string length.

#### Scenario: Error message shows t.co-adjusted count
- **WHEN** a tweet with body text of 270 characters and a 90-character URL is rejected
- **THEN** the error message SHALL report "got 293 characters" (270 + 23), not "got 360 characters"
