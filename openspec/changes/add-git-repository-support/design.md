## Context

The task runner executes LLM agents inside DinD containers. These containers currently have no git tooling and no way to authenticate with remote repositories. The worker creates containers using a `create → put_archive → start` lifecycle, which gives us a natural injection point for SSH credentials. The backend already auto-generates settings on first start (e.g. MCP API key) and stores them in the `settings` table (JSONB values, text primary key).

The task runner image uses `gcr.io/distroless/python3-debian12:nonroot` as its final stage, which is intentionally minimal — it has no package manager and runs as UID 65532 (nonroot).

## Goals / Non-Goals

**Goals:**

- Task runner agents can clone/pull public git repos over HTTPS
- Task runner agents can clone/pull/push private repos over SSH with automatically managed keys
- Admins can copy the public key to configure GitHub/Bitbucket deploy keys (with write access for push)
- Admins can regenerate the keypair and configure which hosts use SSH
- The private key is never exposed via API

**Non-Goals:**

- Git over HTTPS with credentials (username/password or PAT) — out of scope for now
- Merging branches or creating pull requests — git hosting platform operations are out of scope
- Per-task or per-repo SSH keys — one global keypair for the entire application
- Git LFS support
- Submodule authentication chaining

## Decisions

### Decision 1: Install git in the builder stage and copy the binary

The distroless final image has no package manager. Rather than switching base images, we install `git` and `openssh-client` in the builder stage and copy the required binaries and libraries into the final image. This keeps the image hardened (no shell, no package manager) while adding git capability.

**Alternative considered**: Switch to a non-distroless base (e.g. `python:3.11-slim`). Rejected because it would weaken the security posture and increase attack surface.

**Alternative considered**: Use a separate sidecar container with git. Rejected as unnecessarily complex for a single binary.

### Decision 2: Store SSH keypair as settings in the existing database table

The SSH keypair (public + private) will be stored as two entries in the existing `settings` table: `ssh_public_key` and `ssh_private_key`. The git SSH host list will be stored as `git_ssh_hosts`.

This reuses the existing settings infrastructure — no new tables or migrations needed. The backend lifespan handler already initializes settings on first start (MCP API key, system prompt), so we add keypair generation there.

**Alternative considered**: Store keys in a separate `secrets` table with encryption at the application level. Rejected as premature complexity — the database already provides encryption-at-rest and access control, and we can add application-level encryption later if needed.

### Decision 3: Ed25519 key type

Generate Ed25519 keys rather than RSA. Ed25519 is faster to generate, produces smaller keys, and is supported by all major git hosts (GitHub, GitLab, Bitbucket). Generated using Python's `cryptography` library which is already an indirect dependency.

### Decision 4: Worker injects SSH config via put_archive to ~/.ssh/

The worker already uses `put_archive()` to copy files into the container at `/workspace`. We add a second `put_archive()` call targeting the nonroot user's home directory to inject:

- `~/.ssh/id_rsa.agent` — the private key (permissions 600)
- `~/.ssh/config` — generated SSH config with per-host entries

The SSH config follows the pattern:
```
Host github.com
    IdentityFile ~/.ssh/id_rsa.agent
    User git
    StrictHostKeyChecking accept-new
```

`StrictHostKeyChecking accept-new` is used instead of `no` to auto-accept first-contact host keys without prompting while still detecting MITM on subsequent connections.

The nonroot user's home directory in distroless is `/home/nonroot`.

### Decision 5: API design for SSH key management

Three new API interactions:

1. **`GET /api/settings`** — already returns all settings; will now include `ssh_public_key` and `git_ssh_hosts`. The `ssh_private_key` will be explicitly excluded from the response.
2. **`POST /api/settings/regenerate-ssh-key`** — generates a new keypair, replaces both keys in the database, returns the new public key.
3. **`PUT /api/settings`** — already supports updating arbitrary settings; used for `git_ssh_hosts`.

The private key exclusion is enforced in the GET endpoint, not at the database level — the worker reads the private key directly from the database, bypassing the API.

### Decision 6: Settings page UI section

A new "Git SSH Key" section on the settings page, positioned after the MCP API Key section. Contains:

- Read-only display of the public key with a "Copy" button
- "Regenerate" button with confirmation dialog (warns that existing deploy keys will break)
- Editable list of SSH hosts (default: `["github.com", "bitbucket.org"]`) with add/remove controls and a "Save" button

## Risks / Trade-offs

- **Single keypair for all repos**: If compromised, all private repo access is exposed → Mitigation: regenerate button provides quick rotation; future iteration could add per-repo keys
- **Private key in database**: Accessible to anyone with database access → Mitigation: rely on PostgreSQL access controls and encryption-at-rest; the key is never exposed via API
- **Distroless binary copying**: git and openssh may have unlisted shared library dependencies → Mitigation: test the image build and verify `git clone` works inside the container during development
- **StrictHostKeyChecking accept-new**: First connection to a host auto-accepts the key without verification → Mitigation: acceptable for automated agent use; SSH host key pinning could be added later
