## 1. Task Runner Image

- [x] 1.1 Update `task-runner/Dockerfile` to add a second builder stage that installs `git` and `openssh-client`, then copy the git and ssh binaries with required shared libraries into the distroless final image
- [x] 1.2 Create `/home/nonroot/.ssh` directory (permissions 700, owned by UID 65532) in the Dockerfile
- [x] 1.3 Verify the image builds and `git --version` / `ssh -V` work inside the container

## 2. SSH Keypair Generation (Backend)

- [x] 2.1 Add `cryptography` to `backend/requirements.txt` (already present: cryptography==43.0.1)
- [x] 2.2 Add SSH keypair generation helper function (Ed25519, OpenSSH format, comment `content-manager`)
- [x] 2.3 Add keypair generation to backend lifespan startup — generate and store `ssh_private_key` + `ssh_public_key` if not present
- [x] 2.4 Add default `git_ssh_hosts` setting initialization (`["github.com", "bitbucket.org"]`) to lifespan startup
- [x] 2.5 Write backend tests for keypair generation (first start generates, subsequent start skips)

## 3. Settings API Changes (Backend)

- [x] 3.1 Modify `GET /api/settings` to exclude `ssh_private_key` from the response
- [x] 3.2 Add `POST /api/settings/regenerate-ssh-key` endpoint (admin-only, generates new keypair, returns public key)
- [x] 3.3 Write backend tests for private key exclusion and regenerate endpoint

## 4. Worker SSH Injection

- [x] 4.1 Update worker to read `ssh_private_key` and `git_ssh_hosts` settings from the database alongside existing settings
- [x] 4.2 Add SSH config generation function — produces per-host SSH config entries from the hosts list
- [x] 4.3 Add `put_archive()` call to inject `~/.ssh/id_rsa.agent` (permissions 600) and `~/.ssh/config` (permissions 644) into the container at `/home/nonroot/.ssh/`
- [x] 4.4 Skip SSH injection when `ssh_private_key` is not present or empty
- [x] 4.5 Write worker tests for SSH credential injection (with key, without key, empty hosts)

## 5. Settings UI (Frontend)

- [x] 5.1 Add "Git SSH Key" section to the Settings page (after MCP API Key section)
- [x] 5.2 Display SSH public key in a read-only monospace code block with "Copy" button and deploy key help text
- [x] 5.3 Add "Regenerate" button with confirmation dialog calling `POST /api/settings/regenerate-ssh-key`
- [x] 5.4 Add editable git SSH hosts list with add/remove controls and "Save" button
- [x] 5.5 Handle edge cases: no key exists message, duplicate host prevention, empty hostname prevention
- [x] 5.6 Write frontend tests for the Git SSH Key section

## 6. Integration Verification

- [x] 6.1 Run full test suite (backend + frontend) and ensure all existing tests still pass
- [x] 6.2 Build task runner image locally and verify git clone works over HTTPS for a public repo
- [x] 6.3 Build task runner image locally and verify git clone works over SSH when credentials are injected
- [x] 6.4 Verify git push works over SSH when deploy key has write access
