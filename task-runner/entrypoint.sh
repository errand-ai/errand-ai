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
# Merge all skill package.json files into a single combined install so that
# dependencies from every skill are preserved (not overwritten per-skill).
for pkg in /workspace/skills/*/package.json; do
  [ -f "$pkg" ] || continue
  if [ "$installed_node" = false ]; then
    mkdir -p "$NODE_DEPS"
    # Start with an empty combined package.json
    echo '{"dependencies":{}}' > "$NODE_DEPS/package.json"
    installed_node=true
  fi
  # Merge this skill's dependencies into the combined package.json
  /usr/local/bin/node -e "
    const fs = require('fs');
    const combined = JSON.parse(fs.readFileSync('$NODE_DEPS/package.json', 'utf8'));
    const skill = JSON.parse(fs.readFileSync('$pkg', 'utf8'));
    Object.assign(combined.dependencies, skill.dependencies || {});
    fs.writeFileSync('$NODE_DEPS/package.json', JSON.stringify(combined, null, 2));
  "
done
if [ "$installed_node" = true ]; then
  /usr/local/bin/node "$NPM_BOOTSTRAP/lib/bin/npm-cli.js" install --prefix "$NODE_DEPS" 2>&1
fi

# --- Remove all package managers ---
# Staged bootstrap directories
rm -rf "$PIP_BOOTSTRAP"
rm -rf "$NPM_BOOTSTRAP"
# Remove pip/npm from skill-deps in case a skill declared pip or npm as a dependency
rm -rf "$PYTHON_DEPS/pip" "$PYTHON_DEPS"/pip-* 2>/dev/null || true
rm -rf "$NODE_DEPS/node_modules/npm" 2>/dev/null || true
# Remove any residual npm from global node_modules (should already be excluded at build)
rm -rf /usr/local/lib/node_modules/npm 2>/dev/null || true
# Remove pip from base Python site-packages (in case it leaked)
rm -rf /usr/local/lib/python3.11/site-packages/pip /usr/local/lib/python3.11/site-packages/pip-* 2>/dev/null || true
# Remove ensurepip from the Python stdlib
rm -rf /usr/lib/python3.11/ensurepip 2>/dev/null || true
# Clean npm cache
rm -rf /home/nonroot/.npm 2>/dev/null || true

# --- Set environment for installed deps ---
if [ "$installed_python" = true ]; then
  export PYTHONPATH="$PYTHON_DEPS${PYTHONPATH:+:$PYTHONPATH}"
fi
if [ "$installed_node" = true ]; then
  export NODE_PATH="$NODE_DEPS/node_modules${NODE_PATH:+:$NODE_PATH}"
fi

# --- Hand off to agent ---
exec python3 /app/main.py
