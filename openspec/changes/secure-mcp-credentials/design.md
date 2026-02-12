## Context

The worker (`worker.py`) reads the `mcp_servers` JSON from the database settings and writes it verbatim as `mcp.json` into the task runner container (line 255: `json.dumps(mcp_servers)`). Currently, any credentials in the MCP config (e.g. API keys in HTTP headers) must be stored as plaintext in the database. The worker process already has access to environment variables from K8s secrets and ConfigMaps, but these are not used when constructing `mcp.json`.

Separately, the worker already reads a `credentials` setting and passes those as container environment variables (lines 214-218). This mechanism provides env vars to the container but does not inject values into the MCP config JSON itself. The two mechanisms serve different purposes and will remain independent.

## Goals / Non-Goals

**Goals:**
- Allow MCP server configurations to contain environment variable placeholders instead of raw secrets
- Perform substitution in the worker before writing `mcp.json`, using the worker process's own `os.environ`
- Support `$VAR` and `${VAR}` syntaxes, consistent with shell conventions
- Leave unresolved placeholders as-is (safe default — avoids breaking configs when a variable is not set)

**Non-Goals:**
- Changing the Settings UI or API — they continue to store whatever JSON the admin enters
- Recursive or nested substitution (e.g. `${$VAR}`) — single-pass only
- Substitution in JSON keys — only string values are processed
- Escaping mechanism (e.g. `$$VAR` to produce a literal `$VAR`) — can be added later if needed
- Encrypting stored settings in the database — orthogonal concern

## Decisions

### 1. Standalone substitution function

**Decision**: Implement a pure function `substitute_env_vars(obj, environ)` that recursively walks a JSON-compatible Python structure (dicts, lists, strings) and performs regex-based substitution on string values.

The function takes the parsed JSON object and a mapping (defaulting to `os.environ`) as arguments. This makes it trivially testable — tests pass a controlled dict instead of modifying `os.environ`.

**Alternative considered**: Using `string.Template` or `os.path.expandvars`. Both are limited — `string.Template` requires `${}` and raises on missing vars, while `os.path.expandvars` only works on strings (not nested structures) and replaces missing vars with empty strings. A custom regex approach gives full control over behaviour.

### 2. Regex pattern for variable references

**Decision**: Use the pattern `\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)` to match both `${VAR_NAME}` and `$VAR_NAME`.

This matches standard shell variable naming (starts with letter or underscore, followed by alphanumerics/underscores). The `${...}` form is checked first to correctly handle cases like `${FOO}bar` where the braces delimit the variable name.

### 3. Missing variables left as-is

**Decision**: If a referenced variable is not found in the environment mapping, the original placeholder text is preserved unchanged (e.g. `$MISSING_VAR` stays as `$MISSING_VAR`).

**Rationale**: This is the safest default. Replacing with an empty string could silently produce broken configs (e.g. `"Bearer "` instead of `"Bearer $KEY"`). Raising an error would block task execution for optional variables. Leaving as-is lets the admin see that substitution didn't happen (the task runner will fail with an auth error, and the logs will show the placeholder).

### 4. Insertion point in worker flow

**Decision**: Call `substitute_env_vars()` on the `mcp_servers` dict immediately before `json.dumps()`, changing line 255 from:
```python
"mcp.json": json.dumps(mcp_servers),
```
to:
```python
"mcp.json": json.dumps(substitute_env_vars(mcp_servers)),
```

This is the narrowest possible change — substitution happens at the last moment before serialisation, and the original `mcp_servers` dict (with placeholders) is not modified.

## Risks / Trade-offs

- **[Placeholder in non-secret values]** If a config value happens to contain a `$` followed by valid identifier characters (e.g. a regex or literal dollar amount), it could be unintentionally substituted. → Unlikely in MCP config (headers, URLs), and the variable must exist in the worker's environment for substitution to occur. Acceptable risk.
- **[No feedback on unresolved placeholders]** Admins won't know substitution failed until the task runner reports an auth error. → The runner logs (captured in `runner_logs`) will show the connection failure, making debugging straightforward. A future enhancement could log a warning in the worker when placeholders go unresolved.
- **[Single-pass substitution]** A substituted value cannot itself contain variable references. → Intentional — recursive substitution adds complexity and security risk (injection) with no clear use case.
