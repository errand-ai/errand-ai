## ADDED Requirements

### Requirement: SSH host keys are pinned for known hosts

Where errand connects over SSH to a host it already knows about — the hosts in the `git_ssh_hosts` setting, which defaults to `github.com` and `bitbucket.org` — it SHALL verify the host key against a pinned known-hosts entry rather than accepting whatever key is presented on first contact.

`StrictHostKeyChecking=accept-new` MAY remain for hosts errand has no prior knowledge of, because requiring a pre-seeded key for every user-supplied host would break legitimate cloning. The distinction is between hosts errand ships knowledge of and hosts a user introduces.

This applies wherever SSH is invoked: git operations in the task manager, the plugin marketplace, and the container runtime.

A connection refused because of a host-key mismatch SHALL fail with a message identifying the host and stating that its key did not match the pinned entry, so the failure is not mistaken for a network fault.

#### Scenario: Known host with matching key connects

- **WHEN** a git operation connects to `github.com` and the host key matches the pinned entry
- **THEN** the connection proceeds

#### Scenario: Known host with mismatched key is refused

- **WHEN** a connection to a pinned host presents a key that does not match
- **THEN** the connection is refused and the error identifies the host and the mismatch

#### Scenario: Unknown host still uses first-use acceptance

- **WHEN** a user configures a git remote on a host errand has no pinned key for
- **THEN** the connection uses first-use acceptance rather than failing

#### Scenario: Policy applies across all SSH call sites

- **WHEN** SSH is invoked from the task manager, the plugin marketplace, or the container runtime
- **THEN** the same host-key policy applies in each
