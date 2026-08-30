"""Pinned SSH host keys for the hosts errand ships knowledge of.

Every SSH call site used bare `StrictHostKeyChecking=accept-new`: trust on
first use. That accepts whatever key is presented the first time errand
contacts a host, so an attacker in position at exactly that moment can
substitute their own. Not "verification disabled" — but for `github.com` and
`bitbucket.org`, whose keys are published, there is no reason to guess.

The policy is expressed with one option set rather than per-host branching,
because `accept-new` already does exactly what is wanted once a known_hosts
file is seeded:

* host present with a matching key  -> connects
* host present with a *changed* key -> **refused** (accept-new only
  auto-accepts hosts it has never seen; a changed key is still an error)
* host absent                       -> accepted on first use

So seeding known_hosts with pinned entries pins those hosts, while leaving
user-supplied remotes clonable. Requiring a pre-seeded key for every host
would break that workflow, which is why `StrictHostKeyChecking=yes` is not
used here.

Provenance of the keys below, both fetched over TLS from the vendor:

* `github.com` — https://api.github.com/meta (`ssh_keys`)
* `bitbucket.org` — https://bitbucket.org/site/ssh, cross-checked against the
  fingerprints Atlassian publishes in its "Configure SSH" documentation:
  ED25519 SHA256:ybgmFkzwOSotHTHLJgHO0QN8L0xErw6vd0VhFA9m3SM
  RSA     SHA256:46OSHA1Rmj8E8ERTC6xkNcmGOw9oFxYr0WF6zWW8l1E
  ECDSA   SHA256:FC73VB6C4OQLSCrjEayhMp9UMxS97caD/Yyi2bhW/J0

To refresh after a vendor key rotation, re-fetch from those sources and
compare the fingerprints — never from `ssh-keyscan` alone, which is the trust
problem this module exists to remove.
"""

import logging
import os
import re
import tempfile
from collections.abc import Iterable

logger = logging.getLogger(__name__)

PINNED_HOST_KEYS: dict[str, tuple[str, ...]] = {
    "github.com": (
        "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl",
        "github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=",
        "github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=",
    ),
    "bitbucket.org": (
        "bitbucket.org ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIazEu89wgQZ4bqs3d63QSMzYVa0MuJ2e2gKTKqu+UUO",
        "bitbucket.org ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBPIQmuzMBuKdWeF4+a2sjSSpBK0iqitSQ+5BM9KhpexuGt20JpTVM7u5BDZngncgrqDMbWdxMWWOGtZ9UgbqgZE=",
        "bitbucket.org ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDQeJzhupRu0u0cdegZIa8e86EG2qOCsIsD1Xw0xSeiPDlCr7kq97NLmMbpKTX6Esc30NuoqEEHCuc7yWtwp8dI76EEEB1VqY9QJq6vk+aySyboD5QF61I/1WeTwu+deCbgKMGbUijeXhtfbxSxm6JwGrXrhBdofTsbKRUsrN1WoNgUa8uqN1Vx6WAJw1JHPhglEGGHea6QICwJOAr/6mrui/oB7pkaWKHj3z7d1IC4KWLtY47elvjbaTlkN04Kc/5LFEirorGYVbt15kAUlqGM65pk6ZBxtaO3+30LVlORZkxOh+LKL/BvbZ/iRNhItLqNyieoQj/uh/7Iv4uyH/cV/0b4WDSd3DptigWq84lJubb9t/DnZlrJazxyDCulTmKdOR7vs9gMTo+uoIrPSb8ScTtvw65+odKAlBj59dhnVp9zd7QUojOpXlL62Aw56U4oO+FALuevvMjiWeavKhJqlR7i5n9srYcrNV7ttmDw7kf/97P5zauIhxcjX+xHv4M=",
    ),
}


def known_hosts_content(hosts: Iterable[str] | None = None) -> str:
    """known_hosts text pinning `hosts` (all pinned hosts when None).

    Hosts with no pinned key are simply absent, which leaves them on
    first-use acceptance.
    """
    selected = PINNED_HOST_KEYS if hosts is None else {
        h: PINNED_HOST_KEYS[h] for h in dict.fromkeys(hosts) if h in PINNED_HOST_KEYS
    }
    lines = [line for entries in selected.values() for line in entries]
    return "\n".join(lines) + "\n" if lines else ""


def unpinned_hosts(hosts: Iterable[str]) -> list[str]:
    """Hosts errand ships no key for, which stay on first-use acceptance."""
    return [h for h in dict.fromkeys(hosts) if h not in PINNED_HOST_KEYS]


def write_known_hosts(hosts: Iterable[str] | None = None) -> str:
    """Write a known_hosts file for server-side git operations. Returns its path.

    Caller owns the file and must unlink it. It stays writable because
    `accept-new` appends to it when it meets an unpinned host.
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".known_hosts", delete=False
    )
    handle.write(known_hosts_content(hosts))
    handle.close()
    os.chmod(handle.name, 0o600)
    return handle.name


def git_ssh_command(key_path: str, known_hosts_path: str) -> str:
    """The `GIT_SSH_COMMAND` errand uses for authenticated git operations."""
    return (
        f"ssh -i {key_path}"
        f" -o UserKnownHostsFile={known_hosts_path}"
        f" -o StrictHostKeyChecking=accept-new"
    )


_MISMATCH_MARKERS = (
    "REMOTE HOST IDENTIFICATION HAS CHANGED",
    "Host key verification failed",
    "WARNING: POSSIBLE DNS SPOOFING DETECTED",
)

# ssh names the host itself: "Host key for github.com has changed and you have
# requested strict checking." Reading the name out of that is exact — scanning
# stderr for a pinned hostname as a substring would label a failure against
# `notgithub.com` as `github.com`.
_HOST_KEY_CHANGED_RE = re.compile(r"Host key for ([^\s]+) has changed")


def explain_host_key_failure(stderr: str) -> str | None:
    """Return an errand-specific explanation if `stderr` is a host-key refusal.

    Without this the failure reads as a network fault: git surfaces "exit
    status 128" and the operator has no reason to suspect the host key.
    """
    if not stderr or not any(marker in stderr for marker in _MISMATCH_MARKERS):
        return None

    match = _HOST_KEY_CHANGED_RE.search(stderr)
    host = match.group(1) if match else None
    subject = f"'{host}'" if host else "the remote host"

    if host in PINNED_HOST_KEYS:
        detail = (
            f" errand pins the host key for {subject}, so this is not a network "
            f"fault: either the host rotated its key (update PINNED_HOST_KEYS in "
            f"errand/ssh_known_hosts.py from the vendor's published keys) or the "
            f"connection was intercepted."
        )
    else:
        detail = " The key it presented did not match the one previously recorded for it."
    return f"SSH host key verification failed for {subject}.{detail}"
