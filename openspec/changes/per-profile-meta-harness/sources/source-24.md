Requested official URL: https://hermes-agent.nousresearch.com/docs/reference/cli-commands
Accessed UTC: 2026-10-03T14:55:12.468593+00:00
Title: CLI Commands Reference | Hermes Agent
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

* [](https://hermes-agent.nousresearch.com/docs/)
* Reference
* Command Reference
* CLI Commands Reference
On this page

# CLI Commands Reference
Python dependency commands on this page use a [PM-prepared source checkout](https://hermes-agent.nousresearch.com/docs/reference/package-management) .
After a dependency change, reactivate the checkout and restart Hermes.
This page covers the **terminal commands** you run from your shell.
For in-chat slash commands, see [Slash Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands) .

...

## Top-level commands ​
| Command | Purpose |
| `hermes chat` | Interactive or one-shot chat with the agent. |
| `hermes model` | Interactively choose the default provider and model. |
| `hermes moa` | Configure named Mixture of Agents presets selectable from the model picker. |
| `hermes fallback` | Manage fallback providers tried when the primary model errors. |
| `hermes gateway` | Run or manage the messaging gateway service. |
| `hermes proxy` | Local OpenAI-compatible proxy that attaches OAuth provider credentials. See [Subscription Proxy](https://hermes-agent.nousresearch.com/docs/user-guide/features/subscription-proxy) . |
| `hermes egress` | Outbound credential-injection firewall for remote terminal sandboxes (iron-proxy). Disabled by default. See [Egress proxy](https://hermes-agent.nousresearch.com/docs/user-guide/egress/iron-proxy) . |
| `hermes lsp` | Manage Language Server Protocol integration (semantic diagnostics for write_file/patch). |

...

| Command | Purpose |
| `hermes chat` | Interactive or one-shot chat with the agent. |
| `hermes model` | Interactively choose the default provider and model. |
| `hermes moa` | Configure named Mixture of Agents presets selectable from the model picker. |
| `hermes fallback` | Manage fallback providers tried when the primary model errors. |
| `hermes console` | Open the safe Hermes command console. |
| `hermes pairing` | Approve or revoke messaging pairing codes. |
| `hermes skills` | Browse, install, publish, audit, and configure skills. |
| `hermes bundles` | Group several skills under a single `/<name>` slash command. See [Skill Bundles](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) . |
| `hermes curator` | Background skill maintenance — status, run, pause, pin. See [Curator](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator) . |

...

| Command | Purpose |
| `hermes chat` | Interactive or one-shot chat with the agent. |
| `hermes model` | Interactively choose the default provider and model. |
| `hermes moa` | Configure named Mixture of Agents presets selectable from the model picker. |
| `hermes fallback` | Manage fallback providers tried when the primary model errors. |
| `hermes portal` | Nous Portal status, subscription link, and Tool Gateway routing. See [Tool Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-gateway) . |
| `hermes tools` | Configure enabled tools per platform. |
| `hermes computer-use` | Install or check the Computer Use (cua-driver) backend (macOS/Windows/Linux). |
| `hermes pets` | Browse, install, and select [petdex](https://hermes-agent.nousresearch.com/docs/user-guide/features/pets) animated pets shown across the CLI, TUI, and desktop app. Subcommands: `list` , `install` , `select` , `show` , `off` , `scale` , `remove` , `doctor` . |

...

## `hermes model` ​
**`hermes model`** (run from your terminal, outside any Hermes session) is the **full provider setup wizard** . It can add new providers, run OAuth flows, prompt for API keys, and configure endpoints.

...

## `hermes lsp` ​
See [LSP — Semantic Diagnostics](https://hermes-agent.nousresearch.com/docs/user-guide/features/lsp) for
the full guide, supported languages, and configuration knobs.

...

## `hermes portal` ​
```
hermes portal [ status | open | tools ]
```
Inspect Nous Portal auth, Tool Gateway routing, and reach the subscription page. Subcommand-less invocation runs `status` .

...

## `hermes secrets` ​
Pull API keys from an external secret manager at process startup instead of storing them in `~/.hermes/.env` . Currently supports **Bitwarden Secrets Manager** . See the full guide: [Bitwarden integration](https://hermes-agent.nousresearch.com/docs/user-guide/secrets/bitwarden) .

...

## `hermes auth` ​
Manage credential pools for same-provider key rotation. See [Credential Pools](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-pools) for full documentation.

...

## `hermes status` ​
```
hermes status [ --full ] [ --deep ]
```

...

| Option | Description |
| `--full` | Print every section (API keys redacted, auth providers, terminal backend, sessions, ...). `--all` is an alias. |
| `--deep` | Run deeper checks that may take longer. Implies `--full` . |

...

## `hermes cron` ​
the built-in, so cron is never left without a trigger. See the [cron internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals) doc.

...

## `hermes kanban` ​
For the full design — comparison with Cline Kanban / Paperclip / NanoClaw / Gemini Enterprise, eight collaboration patterns, four user stories, concurrency correctness proof — see the [Kanban user guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) .

## `hermes egress` ​
Outbound credential-injection firewall for remote terminal sandboxes. Wraps the [iron-proxy](https://github.com/ironsh/iron-proxy) daemon — a TLS-intercepting proxy that swaps opaque proxy tokens for real upstream API credentials at the network boundary, so sandboxes never hold real keys. Disabled by default; see the full [Egress proxy](https://hermes-agent.nousresearch.com/docs/user-guide/egress/iron-proxy) page for setup + architecture.

...

## `hermes backup` ​
* Unix sockets, devices, and symlinks — a zip cannot hold them; before they were excluded, a stray `gateway.sock` made every full backup report `Backup incomplete` .
* The `hermes-agent` code itself (this is a user-data backup, not a repo snapshot).

### Examples ​
```
hermes backup                           # Full backup to ~/hermes-backup-*.zip hermes backup -o ~/backups/hermes.zip   # Full backup to specific path hermes backup --quick # Quick state-only snapshot hermes backup --quick --label "pre-upgrade" # Quick snapshot with label
```

...

## `hermes checkpoints` ​
### Examples ​
See [Checkpoints and `/rollback`](https://hermes-agent.nousresearch.com/docs/user-guide/checkpoints-and-rollback) for the full architecture and the in-session commands.

...

## `hermes import` ​
### SQLite databases ​
Instead the imported pages are written **into the existing database file** , the same way `/snapshot restore` does it, so every open connection converges on the imported data.

...

## `hermes prompt-size` ​
* **System prompt total** — full assembled prompt (identity, guidance, skills
index, context files, memory, profile, timestamp).
* **Skills index** — the `<available_skills>` block. This is often the largest
single block when many skills are installed.
* **Memory** and **user profile** — your `MEMORY.md` / `USER.md` snapshots.
* **Prompt tiers** — stable / context / volatile, matching how Hermes layers
the prompt for cache-friendliness.

...

## `hermes acp` ​
See [ACP Editor Integration](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp) and [ACP Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/acp-internals) .

...

## `hermes plugins` ​
See [Plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins) and [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins) .

...

## `hermes sessions` ​
| Subcommand | Description |
| `list` | List recent sessions. |
| `repair-prompts` | Report stored system prompts provably degraded by the pre- maintenance-compaction bug. Report-only by default; `--apply` clears verified rows so the next turn rebuilds them, `--json` is machine-readable (and non-interactive when combined with `--apply` ), and an explicit `session_id` is a destructive override that can clear even a healthy prompt. Rows without a readable tools[] pin, or with a memory-only pin, are reported as unverifiable and left unchanged by the scan (a resumed memory-only session re-pins its full tool surface, after which a scan can clear it). Restart a running gateway after `--apply` so repaired rows take effect. See [Sessions → Repair Degraded Stored Prompts](https://hermes-agent.nousresearch.com/docs/user-guide/sessions) . |

...

## `hermes claw` ​
### What gets migrated ​
For the complete config key mapping, SecretRef handling details, and post-migration checklist, see the **[full migration guide](https://hermes-agent.nousresearch.com/docs/guides/migrate-from-openclaw)** .

### Examples ​
```
# Preview what would be migrated hermes claw migrate --dry-run # Full migration (all compatible settings, no secrets) hermes claw migrate --preset full # Full migration including API keys hermes claw migrate --preset full --migrate-secrets # Migrate user data only (no secrets), overwrite conflicts hermes claw migrate --preset user-data --overwrite # Migrate from a custom OpenClaw path hermes claw migrate --source /home/user/old-openclaw
```

...

## `hermes import-agent` ​
Every successful import registers its source in `~/.hermes/import-sync.json` ; `hermes import-agent --sync` then re-imports any registered source whose files changed (a cron-friendly way to keep an imported Claude Code / Codex setup current). See the **[import guide](https://hermes-agent.nousresearch.com/docs/user-guide/import-from-other-agents)** for the full mapping tables.

...

## Maintenance commands ​
| `hermes uninstall [--full] [--gui] [--data] [--dry-run] [--yes]` | Remove owned source-install files. `--gui` selects source-built desktop removal; `--full` also removes data. `--data` removes user data without deleting package-owned code. Sealed installs use their package owner for application removal. `--dry-run` previews the scope; `--yes` skips confirmation. |

...

## See also ​
[Edit this page](https://github.com/NousResearch/hermes-agent/edit/main/website/docs/reference/cli-commands.md)
