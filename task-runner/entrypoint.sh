#!/bin/sh
set -e

# Skill Dependency Installer
# Scans /workspace/skills/ for requirements.txt (Python) and package.json (Node),
# installs declared dependencies, then removes all package managers before
# starting the agent. The agent never has access to pip, npm, or ensurepip.

PIP_BOOTSTRAP="/opt/pip-bootstrap"
NPM_BOOTSTRAP="/opt/npm-bootstrap"
PYTHON_DEPS="/opt/skill-deps/python"
NODE_DEPS="/opt/skill-deps/node"

installed_python=false
installed_node=false

# --- Python dependencies ---
for req in /workspace/skills/*/requirements.txt; do
  [ -f "$req" ] || continue
  if [ "$installed_python" = false ]; then
    mkdir -p "$PYTHON_DEPS"
    installed_python=true
  fi
  PYTHONPATH="$PIP_BOOTSTRAP" python3 -m pip install \
    --no-cache-dir \
    --target "$PYTHON_DEPS" \
    -r "$req" \
    2>&1
done

# --- Node dependencies ---
for pkg in /workspace/skills/*/package.json; do
  [ -f "$pkg" ] || continue
  if [ "$installed_node" = false ]; then
    mkdir -p "$NODE_DEPS"
    installed_node=true
  fi
  cp "$pkg" "$NODE_DEPS/package.json"
  /usr/local/bin/node "$NPM_BOOTSTRAP/lib/bin/npm-cli.js" install --prefix "$NODE_DEPS" 2>&1
done

# --- Remove all package managers ---
rm -rf "$PIP_BOOTSTRAP" 2>/dev/null || true
rm -rf "$NPM_BOOTSTRAP" 2>/dev/null || true
# Remove pip if it leaked into any site-packages
find / -type d -name "pip" -path "*/site-packages/*" -exec rm -rf {} + 2>/dev/null || true
find / -type d -name "pip-*" -path "*/site-packages/*" -exec rm -rf {} + 2>/dev/null || true
# Remove ensurepip (stdlib module that can recreate pip)
find / -type d -name "ensurepip" -exec rm -rf {} + 2>/dev/null || true

# --- Set environment for installed deps ---
if [ "$installed_python" = true ]; then
  export PYTHONPATH="$PYTHON_DEPS${PYTHONPATH:+:$PYTHONPATH}"
fi
if [ "$installed_node" = true ]; then
  export NODE_PATH="$NODE_DEPS/node_modules${NODE_PATH:+:$NODE_PATH}"
fi

# --- Hand off to agent ---
exec python3 /app/main.py
