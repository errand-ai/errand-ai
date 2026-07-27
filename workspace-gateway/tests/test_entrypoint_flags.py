"""Tests that the gateway entrypoint renders the write-back reliability flags.

Runs `entrypoint.sh` with stub `rclone` / `python3` on PATH so `exec rclone`
lands in a stub that records its argv instead of starting a real NFS server.
This asserts the mechanism behind:

  * "Task write reaches the cloud" (tasks.md 6.1): a bounded, tunable
    `--vfs-write-back` plus upload retry/backoff flags, and
  * "Write is not dropped between close and upload" (tasks.md 3.1): the
    `--vfs-cache-mode=full` precondition under which rclone never evicts a dirty
    entry, together with `--vfs-cache-max-size` still being set.
"""

import os
import stat
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRYPOINT = os.path.join(os.path.dirname(HERE), "entrypoint.sh")


def _make_exec(path, body):
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# A config the token check accepts: a `token =` line inside the remote's section
# carrying a non-empty access_token. Without one the entrypoint refuses to start
# (see test_missing_token_is_a_fatal_startup_error).
_AUTHORIZED_CONF = (
    "[gdrive]\n"
    "type = drive\n"
    'token = {"access_token":"ya29.stub","token_type":"Bearer","refresh_token":"1//stub"}\n'
)


def _run_entrypoint(tmp_path, env_overrides=None, conf=_AUTHORIZED_CONF, expect_rc=0):
    """Run entrypoint.sh with stubbed rclone/python3; return the rclone argv list."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    args_file = tmp_path / "rclone.args"
    # Stub rclone: record argv (one per line) and exit 0.
    _make_exec(str(bindir / "rclone"), f'#!/bin/sh\nprintf "%s\\n" "$@" > "{args_file}"\n')
    # Stub python3: record argv so the reconcile invocation can be asserted; the
    # reconcile's own behaviour is tested directly in test_cache_reconcile.py.
    reconcile_args = tmp_path / "reconcile.args"
    _make_exec(str(bindir / "python3"), f'#!/bin/sh\nprintf "%s\\n" "$@" > "{reconcile_args}"\nexit 0\n')

    conf_ro = tmp_path / "rclone.conf"
    conf_ro.write_text(conf)

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env.update(
        WORKSPACE_REMOTE="gdrive",
        WORKSPACE_FOLDER="Errand",
        WORKSPACE_RCLONE_CONF=str(conf_ro),
        WORKSPACE_CONFIG_RW=str(tmp_path / "rw.conf"),
        WORKSPACE_CACHE_DIR=str(tmp_path / "cache"),
        WORKSPACE_ADDR=":2049",
    )
    env.update(env_overrides or {})

    result = subprocess.run(["sh", ENTRYPOINT], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == expect_rc, result.stderr
    if expect_rc != 0:
        return result
    return args_file.read_text().splitlines()


def test_default_write_back_and_retry_flags(tmp_path):
    argv = _run_entrypoint(tmp_path)
    assert "serve" in argv and "nfs" in argv
    # Prompt, tunable write-back + upload resilience (defaults).
    assert "--vfs-write-back=1s" in argv
    assert "--transfers=4" in argv
    assert "--low-level-retries=10" in argv
    assert "--retries=3" in argv


def test_cache_mode_full_and_max_size_present(tmp_path):
    # --vfs-cache-mode=full is the precondition for "a dirty entry is never
    # evicted under cache-size pressure"; --vfs-cache-max-size is still applied.
    argv = _run_entrypoint(tmp_path)
    assert "--vfs-cache-mode=full" in argv
    assert any(a.startswith("--vfs-cache-max-size=") for a in argv)


def test_write_back_is_tunable_via_env(tmp_path):
    argv = _run_entrypoint(
        tmp_path,
        {"VFS_WRITE_BACK": "2s", "VFS_TRANSFERS": "8", "LOW_LEVEL_RETRIES": "20", "RETRIES": "5"},
    )
    assert "--vfs-write-back=2s" in argv
    assert "--transfers=8" in argv
    assert "--low-level-retries=20" in argv
    assert "--retries=5" in argv


def test_missing_token_is_a_fatal_startup_error(tmp_path):
    # A config with no usable token must abort startup LOUDLY. Starting anyway
    # lets rclone open its OAuth redirect listener, which holds 127.0.0.1:53682
    # for the process lifetime and makes every refresher `config/update` fail
    # with `bind: address already in use` — token rotation silently never happens.
    result = _run_entrypoint(tmp_path, conf="[gdrive]\ntype = drive\n", expect_rc=1)
    assert "no usable access token" in result.stderr
    assert "53682" in result.stderr
    assert not (tmp_path / "rclone.args").exists()  # never reached `exec rclone`


def test_empty_access_token_is_rejected(tmp_path):
    # A token line present but carrying an empty access_token is just as unusable
    # as no token at all — rclone would still fall through to interactive OAuth.
    conf = '[gdrive]\ntype = drive\ntoken = {"access_token":"","token_type":"Bearer"}\n'
    result = _run_entrypoint(tmp_path, conf=conf, expect_rc=1)
    assert "no usable access token" in result.stderr


def test_token_for_a_different_remote_does_not_satisfy_the_check(tmp_path):
    # The token must belong to the remote actually being served; a token in some
    # other section leaves the served remote unauthorised.
    conf = (
        "[other]\ntype = drive\n"
        'token = {"access_token":"ya29.stub","token_type":"Bearer"}\n'
        "[gdrive]\ntype = drive\n"
    )
    result = _run_entrypoint(tmp_path, conf=conf, expect_rc=1)
    assert "no usable access token" in result.stderr


def test_reconcile_receives_the_serve_target(tmp_path):
    # The reconcile stats the cloud object behind a desynced entry, which needs
    # the serve target (the rc API isn't listening before `rclone serve` starts).
    _run_entrypoint(tmp_path)
    argv = (tmp_path / "reconcile.args").read_text().splitlines()
    assert argv[0].endswith("cache_reconcile.py")
    assert argv[1] == str(tmp_path / "cache")
    assert argv[2] == "gdrive:Errand"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions, so 0000 is still readable")
def test_unreadable_source_config_fails_with_a_diagnostic(tmp_path):
    # The gateway runs as uid 65532 so it shares the refresher's cache-scanning
    # identity. `rclone config` writes 0600 owned by the operator, so a
    # bind-mounted dev config is typically unreadable here. Under `set -eu` a
    # bare `cp` failure would abort into a restart loop with no explanation.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _make_exec(str(bindir / "rclone"), "#!/bin/sh\nexit 0\n")
    _make_exec(str(bindir / "python3"), "#!/bin/sh\nexit 0\n")
    conf_ro = tmp_path / "rclone.conf"
    conf_ro.write_text(_AUTHORIZED_CONF)
    os.chmod(conf_ro, 0o000)

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env.update(
        WORKSPACE_REMOTE="gdrive",
        WORKSPACE_RCLONE_CONF=str(conf_ro),
        WORKSPACE_CONFIG_RW=str(tmp_path / "rw.conf"),
        WORKSPACE_CACHE_DIR=str(tmp_path / "cache"),
    )
    try:
        result = subprocess.run(["sh", ENTRYPOINT], env=env, capture_output=True, text=True, timeout=30)
    finally:
        os.chmod(conf_ro, 0o644)

    assert result.returncode == 1
    assert "cannot read" in result.stderr
    assert "chmod 0644" in result.stderr
