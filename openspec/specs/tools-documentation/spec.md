## ADDED Requirements

### Requirement: Documentation source file
The project SHALL include a markdown file at `docs/rss-and-twitter-tools.md` that serves as the canonical source for all documentation about the new tools. This file SHALL be used as source material for updating the errand-sh docs site and creating blog/social content. The file SHALL NOT be served by the application — it is a project reference document only.

#### Scenario: File exists in project
- **WHEN** the change is implemented
- **THEN** `docs/rss-and-twitter-tools.md` exists in the project root

### Requirement: Documentation covers all new tools
The documentation file SHALL include sections for each new tool: `read_rss_feed`, `reply_to_tweet`, `like_tweet`, `retweet`, `get_tweet_metrics`, `get_my_recent_tweets`, and `search_tweets`. Each tool section SHALL include: tool name, description, parameters (with types and defaults), return format, and at least one usage example.

#### Scenario: All tools documented
- **WHEN** the documentation file is reviewed
- **THEN** every new MCP tool has a section with description, parameters, return format, and example

### Requirement: Documentation covers example workflows
The documentation file SHALL include a section describing composite workflows that combine multiple tools. At minimum: (1) RSS-to-tweet workflow (read feed, read article, post tweet), (2) threaded tweet workflow (post + replies), (3) analytics review workflow (get recent tweets, check metrics), (4) discovery and engagement workflow (search, like, reply).

#### Scenario: Workflow examples present
- **WHEN** the documentation file is reviewed
- **THEN** it contains at least 4 workflow examples showing tools used in combination

### Requirement: Documentation covers prerequisites and configuration
The documentation file SHALL include a section on prerequisites: X API tier requirements (Free vs Basic), required app permissions (Read and Write), and the feedparser dependency. It SHALL note which tools require Basic tier (search_tweets only) and which work on Free tier.

#### Scenario: Prerequisites documented
- **WHEN** the documentation file is reviewed
- **THEN** it clearly states API tier requirements per tool and configuration prerequisites
