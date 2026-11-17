Requested official URL: https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli
Accessed UTC: 2026-10-03T15:03:00.172630+00:00
Title: An important update: Transitioning Gemini CLI to Antigravity CLI
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# An important update: Transitioning Gemini CLI to Antigravity CLI


            - Google Developers Blog
URL: https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/
Published: 2026-05-19

An important update: Transitioning Gemini CLI to Antigravity CLI - Google Developers Blog

# An important update: Transitioning Gemini CLI to Antigravity CLI

MAY 19, 2026

 Dmitry Lyalin Group Product Manager

 Taylor Mullen Principal Engineer

When we shipped Gemini CLI last year, our goal was to bring the magic of Gemini directly into your terminal. Along the way, we’ve learned a lot from our community of millions of users, with over 100,000 GitHub stars, 6,000 merged pull requests, and hundreds of contributors, including: you love a good terminal UI, you appreciate that we ship weekly releases, and your workflows have simply outgrown those early days of 2025.

Gemini CLI proved the terminal could be an incredible interface for agentic tasks, but your needs shifted. You now require multiple agents communicating with each other to split up the work and solve complex problems. This means your terminal tools need to share a unified backend with the rest of your workflow.

Listening to your feedback made one thing clear: we can serve you best by pouring our energy into a single product built for today's multi-agent reality. To deliver the single platform you need to build the future, we're unifying our efforts into Google Antigravity, our premier agent-first development platform, which includes a powerful server-side harness and a brand-new terminal experience: Antigravity CLI.

While there won't be 1:1 feature parity right out of the gate, we made sure Antigravity CLI keeps the most critical features of Gemini CLI: Agent Skills, Hooks, Subagents, and Extensions (now as Antigravity plugins). Whether you use Gemini CLI to get quick, grounded answers, scaffold and build out a new coding project, or help provision your cloud infrastructure, you can still do all of that right in Antigravity CLI. And to make your experience better, we focused on the things that matter most to you, like:

- Faster execution: Built in Go, Antigravity CLI is snappier and more responsive.
- Asynchronous workflows: Antigravity CLI orchestrates multiple agents for complex tasks in the background, letting you run large-scale refactors or research several topics without locking up your terminal session.
- Unified architecture: Antigravity CLI shares the same agent harness as Antigravity 2.0, the new Antigravity desktop application, ensuring that all future improvements to core agents are automatically applied wherever you use them.

### Important timeline for Consumers

Starting today, Antigravity CLI is available to everyone.

On June 18, 2026, Gemini CLI and Gemini Code Assist IDE extensions will stop serving requests for Google AI Pro and Ultra, as well as those using it free of charge using Gemini Code Assist for individuals.

We are here to help make the transition to Antigravity CLI and Antigravity 2.0 as smooth as possible. You can get started now with our technical documentation, and we will be releasing video walkthroughs in the coming weeks.

For Gemini Code Assis
