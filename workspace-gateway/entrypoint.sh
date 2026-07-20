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
#   WORKSPACE_ADDR            NFS listen address (default: :2049)
#   WORKSPACE_POLL_INTERVAL   change poll interval (default: 15s)
#   WORKSPACE_CACHE_DIR       VFS cache dir (default: /cache)
#   WORKSPACE_CACHE_MAX_SIZE  VFS cache max size (default: 5G)
#   WORKSPACE_RC_ADDR         rc bind address (default: 127.0.0.1:5572)
#   WORKSPACE_EXTRA_FLAGS     optional extra rclone flags
set -eu

REMOTE="${WORKSPACE_REMOTE:?WORKSPACE_REMOTE is required}"
FOLDER="${WORKSPACE_FOLDER:-}"
CONF_RO="${WORKSPACE_RCLONE_CONF:-/config-ro/rclone.conf}"
CONF_RW="${WORKSPACE_CONFIG_RW:-/config-rw/rclone.conf}"
ADDR="${WORKSPACE_ADDR:-:2049}"
POLL="${WORKSPACE_POLL_INTERVAL:-15s}"
CACHE_DIR="${WORKSPACE_CACHE_DIR:-/cache}"
CACHE_MAX="${WORKSPACE_CACHE_MAX_SIZE:-5G}"
RC_ADDR="${WORKSPACE_RC_ADDR:-127.0.0.1:5572}"

# Copy the config to a writable location so `rclone rc config/update` can persist.
mkdir -p "$(dirname "$CONF_RW")" "$CACHE_DIR"
cp "$CONF_RO" "$CONF_RW"
export RCLONE_CONFIG="$CONF_RW"

# Build the serve target: REMOTE:FOLDER (or REMOTE: for the whole remote root).
if [ -n "$FOLDER" ]; then
  TARGET="${REMOTE}:${FOLDER}"
else
  TARGET="${REMOTE}:"
fi

echo "workspace-gateway: serving ${TARGET} over NFS at ${ADDR} (poll ${POLL})" >&2

# shellcheck disable=SC2086
exec rclone serve nfs "$TARGET" \
  --addr="$ADDR" \
  --vfs-cache-mode=full \
  --cache-dir="$CACHE_DIR" \
  --vfs-cache-max-size="$CACHE_MAX" \
  --dir-cache-time="$POLL" \
  --poll-interval="$POLL" \
  --drive-skip-gdocs \
  --rc --rc-addr="$RC_ADDR" --rc-no-auth \
  ${WORKSPACE_EXTRA_FLAGS:-} \
  -v
