## Why

The task runner agents currently cannot interact with git repositories. Many useful tasks — code review, documentation generation, dependency auditing, release management — require cloning, pulling, and pushing to git repos. Adding git support to the task runner unlocks these workflows, with SSH key management enabling full read/write access to private repositories without exposing credentials to the LLM agent.

## What Changes

- Install `git` and `openssh-client` in the task runner container image
- Generate an SSH keypair on backend first start, storing the public and private keys in the database settings table
- Add API endpoints to retrieve the public key and regenerate the keypair
- Add a settings UI section for SSH key management: copy public key, regenerate keypairs, and configure which git hosts use SSH authentication
- Store a configurable list of SSH hosts (defaulting to `["github.com", "bitbucket.org"]`) in the settings table
- Worker uploads the private SSH key and per-host SSH config into each task runner container before starting it

## Capabilities

### New Capabilities
- `git-ssh-keys`: SSH keypair lifecycle — generation on first backend start, storage in the database, API endpoints for public key retrieval and keypair regeneration, and configurable list of git hosts for SSH authentication

### Modified Capabilities
- `task-runner-image`: Add `git` and `openssh-client` packages to the container image
- `task-worker`: Upload private SSH key to `~/.ssh/id_rsa.agent` and generate per-host SSH config inside the task runner container before starting it
- `admin-settings-api`: Add endpoints for SSH public key retrieval and keypair regeneration; store SSH host list setting
- `admin-settings-ui`: Add SSH key management section — display/copy public key, regenerate keypair button with confirmation, and editable list of SSH hosts

## Impact

- **Backend**: New startup logic to generate keypair if not present; new API endpoints under `/api/settings/`
- **Worker**: Additional container setup step (copy SSH key + config via `put_archive()`)
- **Task runner image**: Dockerfile changes to install git and openssh-client; image size will increase
- **Frontend**: New settings section for SSH key management
- **Database**: New settings keys (`ssh_public_key`, `ssh_private_key`, `git_ssh_hosts`) in existing settings table — no migration needed
- **Security**: Private key stored encrypted-at-rest in the database (PostgreSQL); never exposed via API — only the public key is retrievable
