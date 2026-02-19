## Requirements

### Requirement: SSH keypair generation on first backend start

The backend SHALL generate an Ed25519 SSH keypair during the lifespan startup if no `ssh_private_key` setting exists in the database. The keypair SHALL be generated using the `cryptography` library. The private key SHALL be stored in the `settings` table with key `ssh_private_key` in PEM format (OpenSSH format). The public key SHALL be stored with key `ssh_public_key` in OpenSSH format (e.g. `ssh-ed25519 AAAA... errand`). The key comment SHALL be `errand`.

#### Scenario: First start generates keypair

- **WHEN** the backend starts and no `ssh_private_key` setting exists
- **THEN** an Ed25519 keypair is generated, both keys are stored in the settings table, and a log message "Generated new SSH keypair" is emitted

#### Scenario: Subsequent start skips generation

- **WHEN** the backend starts and `ssh_private_key` already exists in the settings table
- **THEN** no new keypair is generated

### Requirement: Default git SSH hosts on first backend start

The backend SHALL create a `git_ssh_hosts` setting during the lifespan startup if it does not already exist. The default value SHALL be `["github.com", "bitbucket.org"]`.

#### Scenario: First start creates default hosts

- **WHEN** the backend starts and no `git_ssh_hosts` setting exists
- **THEN** the setting is created with value `["github.com", "bitbucket.org"]`

#### Scenario: Existing hosts preserved on start

- **WHEN** the backend starts and `git_ssh_hosts` already exists with value `["github.com"]`
- **THEN** the setting is not modified

### Requirement: Private key excluded from settings API response

The `GET /api/settings` endpoint SHALL exclude the `ssh_private_key` entry from its response. All other settings (including `ssh_public_key` and `git_ssh_hosts`) SHALL be returned normally.

#### Scenario: Settings response excludes private key

- **WHEN** an admin requests `GET /api/settings`
- **THEN** the response includes `ssh_public_key` and `git_ssh_hosts` but does NOT include `ssh_private_key`

### Requirement: Regenerate SSH keypair endpoint

The backend SHALL expose `POST /api/settings/regenerate-ssh-key` requiring the `admin` role. The endpoint SHALL generate a new Ed25519 keypair, replace both `ssh_private_key` and `ssh_public_key` in the settings table, and return the new public key as `{"ssh_public_key": "<new-public-key>"}`.

#### Scenario: Regenerate SSH keypair

- **WHEN** an admin sends `POST /api/settings/regenerate-ssh-key`
- **THEN** a new keypair is generated, both keys are updated in the settings table, and the response contains the new public key

#### Scenario: Non-admin user rejected

- **WHEN** a non-admin user sends `POST /api/settings/regenerate-ssh-key`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

#### Scenario: Old key invalidated after regeneration

- **WHEN** an admin regenerates the SSH keypair
- **THEN** the previous private key is no longer stored and any git hosts configured with the old public key will reject connections using the new key
