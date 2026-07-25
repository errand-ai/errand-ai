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

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRYPOINT = os.path.join(os.path.dirname(HERE), "entrypoint.sh")


def _make_exec(path, body):
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_entrypoint(tmp_path, env_overrides=None):
    """Run entrypoint.sh with stubbed rclone/python3; return the rclone argv list."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    args_file = tmp_path / "rclone.args"
    # Stub rclone: record argv (one per line) and exit 0.
    _make_exec(str(bindir / "rclone"), f'#!/bin/sh\nprintf "%s\\n" "$@" > "{args_file}"\n')
    # Stub python3: the reconcile step is a no-op here (tested separately).
    _make_exec(str(bindir / "python3"), "#!/bin/sh\nexit 0\n")

    conf_ro = tmp_path / "rclone.conf"
    conf_ro.write_text("[gdrive]\ntype = drive\n")

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
    assert result.returncode == 0, result.stderr
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
