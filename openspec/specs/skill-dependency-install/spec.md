## Purpose

Automated installation of skill-declared Python and Node dependencies at task-runner startup, with package managers removed before agent execution.

## Requirements

### Requirement: Entrypoint installs skill-declared Python dependencies
The task-runner container SHALL include an entrypoint shell script (`entrypoint.sh`) that scans `/workspace/skills/*/requirements.txt` before starting the agent. For each `requirements.txt` found, the entrypoint SHALL run pip install with `--no-cache-dir` and `--target /opt/skill-deps/python/` to install the declared packages. After all installations complete, the entrypoint SHALL set `PYTHONPATH` to include `/opt/skill-deps/python/` (prepended to any existing value). The entrypoint SHALL then delete all pip-related files (`/opt/pip-bootstrap/`, any `pip` or `pip-*` directories in site-packages, and any `ensurepip` module directories) before exec'ing into `python3 /app/main.py`.

#### Scenario: Skill with Python dependencies
- **WHEN** a skill at `/workspace/skills/nanobanana/requirements.txt` contains `google-genai\npillow`
- **THEN** the entrypoint installs `google-genai` and `pillow` to `/opt/skill-deps/python/`, sets `PYTHONPATH` to include that path, removes pip, and starts the agent

#### Scenario: Multiple skills with Python dependencies
- **WHEN** skills at `/workspace/skills/skill-a/requirements.txt` and `/workspace/skills/skill-b/requirements.txt` both exist
- **THEN** the entrypoint installs dependencies from both files to the same target directory

#### Scenario: No skills have dependencies
- **WHEN** no `requirements.txt` or `package.json` files exist under `/workspace/skills/`
- **THEN** the entrypoint immediately exec's into `python3 /app/main.py` without invoking pip or npm

### Requirement: Entrypoint installs skill-declared Node dependencies
The task-runner entrypoint SHALL scan `/workspace/skills/*/package.json` before starting the agent. For each `package.json` found, the entrypoint SHALL copy it to a shared install directory at `/opt/skill-deps/node/` and run `npm install --prefix /opt/skill-deps/node/` to install the declared packages. After all installations complete, the entrypoint SHALL set `NODE_PATH` to `/opt/skill-deps/node/node_modules`. The entrypoint SHALL then delete all npm-related files (`/opt/npm-bootstrap/` and any npm cache) before exec'ing into the agent.

#### Scenario: Skill with Node dependencies
- **WHEN** a skill at `/workspace/skills/my-tool/package.json` declares dependencies
- **THEN** the entrypoint installs Node packages to `/opt/skill-deps/node/node_modules/`, sets `NODE_PATH`, removes npm, and starts the agent

#### Scenario: Mixed Python and Node dependencies
- **WHEN** one skill has a `requirements.txt` and another has a `package.json`
- **THEN** the entrypoint installs both Python and Node dependencies, removes both pip and npm, and starts the agent

### Requirement: Package managers are not accessible at agent runtime
After the entrypoint completes dependency installation and before exec'ing into the agent, the entrypoint SHALL remove all package manager binaries and modules from the filesystem. The agent's `execute_command` function SHALL NOT be able to invoke `pip`, `npm`, `python3 -m pip`, `python3 -m ensurepip`, or any equivalent package installation command.

#### Scenario: Agent cannot use pip
- **WHEN** the agent runs `execute_command("pip install requests")`
- **THEN** the command fails with "not found"

#### Scenario: Agent cannot use python -m pip
- **WHEN** the agent runs `execute_command("python3 -m pip install requests")`
- **THEN** the command fails with "No module named pip"

#### Scenario: Agent cannot use ensurepip
- **WHEN** the agent runs `execute_command("python3 -m ensurepip")`
- **THEN** the command fails with "No module named ensurepip"

#### Scenario: Agent cannot use npm
- **WHEN** the agent runs `execute_command("npm install axios")`
- **THEN** the command fails with "not found"

#### Scenario: Installed packages are importable
- **WHEN** pip has installed `pillow` during the entrypoint phase and the agent runs `execute_command("python3 -c 'from PIL import Image; print(Image.__version__)'")`
- **THEN** the command succeeds and prints the Pillow version
