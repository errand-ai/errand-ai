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

# Build the serve target: REMOTE:FOLDER (or REMOTE: for the whole remote root).
if [ -n "$FOLDER" ]; then
  TARGET="${REMOTE}:${FOLDER}"
else
  TARGET="${REMOTE}:"
fi

# Reconcile orphaned dirty cache entries BEFORE serving. An orphaned entry
# (dirty meta with no data to upload) is not a resumable upload — rclone would
# either leave it blocking change-polling or upload an empty file. We clear the
# stale meta so that on the first serve+poll rclone re-fetches the current cloud
# object instead (see "Orphaned dirty entry recovered on restart"). Best-effort:
# a reconcile failure must not stop the gateway from serving.
python3 /usr/local/bin/cache_reconcile.py "$CACHE_DIR" || \
  echo "workspace-gateway: cache reconcile step failed (continuing to serve)" >&2

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
