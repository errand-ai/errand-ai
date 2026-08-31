"""Pinned SSH host key tests.

`accept-new` against a seeded known_hosts is the whole policy: pinned hosts
are verified, unpinned hosts keep first-use acceptance. These tests assert
that both halves hold, and that a mismatch is explained rather than surfacing
as an opaque git failure.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

from ssh_known_hosts import (
    PINNED_HOST_KEYS,
    explain_host_key_failure,
    git_ssh_command,
    known_hosts_content,
    unpinned_hosts,
    write_known_hosts,
)


# These two read key material with ssh's own tooling, which is the point — a
# pure-Python fingerprint would not catch a key ssh cannot parse. Skipped
# rather than failed where the binary is absent (minimal images, Windows).
requires_ssh_keygen = pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="ssh-keygen not available"
)

def test_default_hosts_are_pinned():
    assert set(PINNED_HOST_KEYS) == {"github.com", "bitbucket.org"}


def test_known_hosts_content_covers_requested_hosts():
    content = known_hosts_content(["github.com"])
    assert content.startswith("github.com ssh-ed25519 ")
    assert "bitbucket.org" not in content


def test_known_hosts_content_omits_unpinned_hosts():
    """An unpinned host contributes nothing, leaving it on first-use acceptance."""
    assert known_hosts_content(["git.internal.example"]) == ""


def test_unpinned_hosts_identifies_user_supplied_remotes():
    assert unpinned_hosts(["github.com", "git.internal.example"]) == ["git.internal.example"]


@requires_ssh_keygen
def test_pinned_keys_are_wellformed_and_match_published_fingerprints(tmp_path):
    """Guards against a typo in a transcribed key.

    Fingerprints are Atlassian's and GitHub's published values; ssh-keygen
    recomputes them from the key material actually stored in this module.
    """
    path = tmp_path / "known_hosts"
    path.write_text(known_hosts_content())
    out = subprocess.run(
        ["ssh-keygen", "-lf", str(path)], capture_output=True, text=True, check=True
    ).stdout

    for expected in (
        "SHA256:ybgmFkzwOSotHTHLJgHO0QN8L0xErw6vd0VhFA9m3SM",  # bitbucket ED25519
        "SHA256:46OSHA1Rmj8E8ERTC6xkNcmGOw9oFxYr0WF6zWW8l1E",  # bitbucket RSA
        "SHA256:FC73VB6C4OQLSCrjEayhMp9UMxS97caD/Yyi2bhW/J0",  # bitbucket ECDSA
        "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",  # github ED25519
        "SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM",  # github ECDSA
        "SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s",  # github RSA
    ):
        assert expected in out, f"{expected} missing from:\n{out}"

    # The RSA key GitHub rotated away from in March 2023 must not be pinned.
    assert "SHA256:br9IjFspm1vxR3iA35FWE+4VTyz1hYVLIE2t1/CeyWQ" not in out


def test_write_known_hosts_is_private_and_writable():
    path = write_known_hosts(["github.com"])
    try:
        assert oct(os.stat(path).st_mode)[-3:] == "600"
        content = pathlib.Path(path).read_text()
        hosts = {line.split(" ", 1)[0] for line in content.splitlines() if line}
        assert hosts == {"github.com"}
    finally:
        os.unlink(path)


def test_git_ssh_command_pins_and_keeps_accept_new():
    cmd = git_ssh_command("/tmp/k", "/tmp/kh")
    assert "-o UserKnownHostsFile=/tmp/kh" in cmd
    # accept-new refuses a *changed* key while still accepting unknown hosts,
    # which is exactly the required policy.
    assert "-o StrictHostKeyChecking=accept-new" in cmd


# --- mismatch explanation ---


def test_mismatch_on_pinned_host_names_host_and_cause():
    stderr = (
        "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
        "@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @\n"
        "Host key for github.com has changed and you have requested strict checking.\n"
        "Host key verification failed.\n"
    )
    explanation = explain_host_key_failure(stderr)
    assert explanation.startswith("SSH host key verification failed for 'github.com'.")
    assert "not a network fault" in explanation


def test_mismatch_on_unknown_host_still_explained():
    explanation = explain_host_key_failure("Host key verification failed.\n")
    assert explanation is not None
    assert "host key verification failed" in explanation.lower()


def test_ordinary_git_failure_is_not_misreported_as_a_key_problem():
    assert explain_host_key_failure("fatal: repository not found") is None
    assert explain_host_key_failure("") is None


# --- real ssh behaviour: the assumption the whole design rests on ---


@requires_ssh_keygen
@pytest.mark.parametrize("seeded,expect_recorded", [(True, True), (False, False)])
def test_seeding_decides_whether_ssh_already_knows_the_host(
    tmp_path, seeded, expect_recorded
):
    """A seeded known_hosts makes ssh treat the host as already known.

    This asserts the *input* to accept-new's decision, read with ssh's own
    parser (`ssh-keygen -F`), not the decision itself: whether a recorded
    host with a changed key is refused is ssh's behaviour, not errand's, and
    proving it needs a live server. That was verified by hand against
    github.com — pinned key authenticates, tampered key is refused with
    "REMOTE HOST IDENTIFICATION HAS CHANGED", unpinned host still accepted.
    Naming the test for what it checks so the gap is visible.
    """
    known = tmp_path / "known_hosts"
    known.write_text(known_hosts_content(["github.com"]) if seeded else "")
    found = subprocess.run(
        ["ssh-keygen", "-F", "github.com", "-f", str(known)],
        capture_output=True,
        text=True,
    )
    assert (found.returncode == 0) is expect_recorded


def test_unpinned_host_named_in_stderr_is_not_claimed_as_pinned():
    """The host comes from ssh's own wording, so a lookalike is not mislabelled."""
    stderr = (
        "Host key for notgithub.com has changed and you have requested strict checking.\n"
        "Host key verification failed.\n"
    )
    explanation = explain_host_key_failure(stderr)
    assert "'notgithub.com'" in explanation
    assert "errand pins" not in explanation
