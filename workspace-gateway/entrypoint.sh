#!/bin/sh
# Entrypoint for the shared-workspace gateway container.
#
# Runs `rclone serve nfs` against a single designated Google Drive or OneDrive
# folder, exposing it over NFSv3 for task containers to mount. The rclone remote
# type (drive/onedrive) is the ONLY provider-specific configuration; everything
# here is provider-agnostic.
#
# Flags are the spike-validated baseline (design §D8 Spike Results):
#   --vfs-cache-mode full   : cache reads, queue writes (survives restart via PVC)
#   --cache-dir             : persistent cache dir (a PVC in prod) so pending
#                             write-backs survive a crash/restart (finding 1.3)
#   --poll-interval         : change-notification polling for live human edits
#   --drive-skip-gdocs      : never expose Google-native Docs/Sheets/Slides
#   --rc on localhost       : the token-refresher pushes fresh tokens via rc;
#                             NOT reachable outside the pod
#
# The rclone config is copied from the (read-only) mounted secret to a WRITABLE
# path, because `rclone rc config/update` (used by the refresher) persists to the
# config file and a read-only mount makes it fail (finding F4).
#
# Environment:
#   WORKSPACE_REMOTE          rclone remote name defined in the config (required)
#   WORKSPACE_FOLDER          folder within the remote to serve (default: root)
#   WORKSPACE_RCLONE_CONF     path to the mounted (read-only) rclone.conf
#                             (default: /config-ro/rclone.conf)
#   WORKSPACE_CONFIG_RW       writable path the read-only config is copied to,
#                             so `rclone rc config/update` can persist
#                             (default: /config-rw/rclone.conf)
#   WORKSPACE_ADDR            NFS listen address (default: :2049)
#   WORKSPACE_POLL_INTERVAL   change poll interval (default: 15s)
#   WORKSPACE_DIR_CACHE_TIME  dir-cache lifetime, decoupled from polling to keep
#                             metadata off the provider API (default: 5m; F5)
#   WORKSPACE_CACHE_DIR       VFS cache dir (default: /cache)
#   WORKSPACE_CACHE_MAX_SIZE  VFS cache max size (default: 5G)
#   WORKSPACE_RC_ADDR         rc bind address (default: 127.0.0.1:5572)
#   VFS_WRITE_BACK            delay after last modification before a completed
#                             write uploads (default: 1s). Set explicitly and
#                             short rather than relying on rclone's implicit 5s
#                             default, to bound the window in which a completed
#                             write can be lost before it reaches the cloud.
#   VFS_TRANSFERS             concurrent write-back uploads (--transfers, default: 4)
#   LOW_LEVEL_RETRIES         per-chunk low-level retries (--low-level-retries,
#                             default: 10) — keeps a transient provider error in a
#                             retrying state instead of dropping the write.
#   RETRIES                   whole-operation retries (--retries, default: 3)
#   WORKSPACE_EXTRA_FLAGS     optional extra rclone flags
set -eu

REMOTE="${WORKSPACE_REMOTE:?WORKSPACE_REMOTE is required}"
FOLDER="${WORKSPACE_FOLDER:-}"
CONF_RO="${WORKSPACE_RCLONE_CONF:-/config-ro/rclone.conf}"
CONF_RW="${WORKSPACE_CONFIG_RW:-/config-rw/rclone.conf}"
ADDR="${WORKSPACE_ADDR:-:2049}"
POLL="${WORKSPACE_POLL_INTERVAL:-15s}"
# Directory-cache lifetime is decoupled from the poll interval on purpose: change
# polling (--poll-interval) already invalidates cached entries when the cloud
# changes, so a *long* dir-cache-time keeps metadata (readdir/stat) served from
# cache instead of hitting the provider API — mitigating quota pressure (design.md
# finding F5). Keep polling short; keep dir cache long.
DIR_CACHE_TIME="${WORKSPACE_DIR_CACHE_TIME:-5m}"
CACHE_DIR="${WORKSPACE_CACHE_DIR:-/cache}"
CACHE_MAX="${WORKSPACE_CACHE_MAX_SIZE:-5G}"
RC_ADDR="${WORKSPACE_RC_ADDR:-127.0.0.1:5572}"
# Write-back / upload-resilience tuning. Explicit short write-back uploads a
# completed write promptly after close(); the retry flags keep a transient
# provider error progressing (retrying) instead of silently dropping the write
# (see the "Write-back upload with persistent cache" capability).
VFS_WRITE_BACK="${VFS_WRITE_BACK:-1s}"
VFS_TRANSFERS="${VFS_TRANSFERS:-4}"
LOW_LEVEL_RETRIES="${LOW_LEVEL_RETRIES:-10}"
RETRIES="${RETRIES:-3}"

# Copy the config to a writable location so `rclone rc config/update` can persist.
# If an init container already seeded the writable config with a FRESH token
# (Kubernetes), do NOT overwrite it with the (possibly long-expired) Secret copy
# — serving the remote root authenticates at startup, so a stale token here makes
# rclone crash-loop after a pod restart. On compose (no init container) this
# copies from the read-only mount as before.
mkdir -p "$(dirname "$CONF_RW")" "$CACHE_DIR"
if [ ! -f "$CONF_RW" ]; then
  cp "$CONF_RO" "$CONF_RW"
fi
export RCLONE_CONFIG="$CONF_RW"

# Fail fast unless the writable config holds a usable token for this remote.
#
# rclone treats a config without a usable token as "needs authorising" and starts
# its OAuth redirect webserver, which holds 127.0.0.1:53682 for the life of the
# process. Every subsequent refresher `rclone rc config/update` then fails with
# `bind: address already in use`, so token rotation silently never happens — it
# was masked for months by rclone's own internal refresh and would have become an
# outage the first time the refresh token needed rotating. A missing token is a
# fatal startup error, not a degraded start that squats the port.
if ! awk -v remote="$REMOTE" '
      /^\[.*\]$/ { section = substr($0, 2, length($0) - 2); next }
      section == remote && /^[[:space:]]*token[[:space:]]*=/ { print }
    ' "$CONF_RW" | grep -q '"access_token"[[:space:]]*:[[:space:]]*"[^"][^"]*"'; then
  echo "workspace-gateway: FATAL: no usable access token for remote [${REMOTE}] in ${CONF_RW}." >&2
  echo "workspace-gateway: refusing to start — rclone would fall through to an interactive OAuth" >&2
  echo "workspace-gateway: flow and squat 127.0.0.1:53682, breaking refresher config/update." >&2
  echo "workspace-gateway: run the refresher in 'init' mode to seed a fresh token first." >&2
  exit 1
fi

# Never let rclone open the interactive OAuth listener even if something slips
# past the check above: with no browser and no console it can only ever squat the
# port, so failing the operation is strictly better than holding 53682 forever.
export RCLONE_AUTH_NO_OPEN_BROWSER=true

# Build the serve target: REMOTE:FOLDER (or REMOTE: for the whole remote root).
if [ -n "$FOLDER" ]; then
  TARGET="${REMOTE}:${FOLDER}"
else
  TARGET="${REMOTE}:"
fi

# Reconcile faulted dirty cache entries BEFORE serving — never while `rclone
# serve` is running, so repair can't race a live cache. Two faults are handled:
#   * orphaned (dirty meta, no data to upload): the stale meta is cleared so the
#     first serve+poll re-fetches the current cloud object rather than acting on
#     a phantom write or uploading an empty file;
#   * desynced (dirty meta reporting Size 0 while a non-empty data file exists):
#     the metadata is REPAIRED to match the data so the complete content uploads,
#     or the entry is quarantined if the cloud object has moved underneath it.
#     Uploading from that state is what corrupted a user's file on 2026-07-26.
# The serve target is passed so the reconcile can stat the cloud object behind a
# desynced entry (the rc API isn't listening yet — it shells out to rclone).
#
# The script is best-effort and self-contained: it handles its own logic errors
# (returning 0 and logging a structured `cache_reconcile_failed` line), so this
# `||` fires only if the reconcile can't be invoked at all (e.g. python3 or the
# script is missing) — in which case we warn and serve anyway.
python3 /usr/local/bin/cache_reconcile.py "$CACHE_DIR" "$TARGET" || \
  echo "workspace-gateway: could not run cache reconcile (python3/script missing?); continuing to serve" >&2

# Log the identity the cache will be created under. rclone creates its VFS cache
# dirs mode 0700, so the refresher sidecar can only scan them when it runs as the
# SAME uid — a mismatch makes stuck-entry detection silently inert (the
# 2026-07-26 stall). The refresher's startup self-test is the authoritative
# check; this line makes diagnosing a mismatch a one-liner.
echo "workspace-gateway: cache ${CACHE_DIR} owned by uid $(id -u) gid $(id -g)" >&2

echo "workspace-gateway: serving ${TARGET} over NFS at ${ADDR} (poll ${POLL}, write-back ${VFS_WRITE_BACK}, transfers ${VFS_TRANSFERS}, low-level-retries ${LOW_LEVEL_RETRIES}, retries ${RETRIES})" >&2

# shellcheck disable=SC2086
exec rclone serve nfs "$TARGET" \
  --addr="$ADDR" \
  --vfs-cache-mode=full \
  --cache-dir="$CACHE_DIR" \
  --vfs-cache-max-size="$CACHE_MAX" \
  --vfs-write-back="$VFS_WRITE_BACK" \
  --transfers="$VFS_TRANSFERS" \
  --low-level-retries="$LOW_LEVEL_RETRIES" \
  --retries="$RETRIES" \
  --dir-cache-time="$DIR_CACHE_TIME" \
  --poll-interval="$POLL" \
  --drive-skip-gdocs \
  --rc --rc-addr="$RC_ADDR" --rc-no-auth \
  ${WORKSPACE_EXTRA_FLAGS:-} \
  -v
