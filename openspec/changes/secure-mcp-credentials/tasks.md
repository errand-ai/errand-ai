## 1. Substitution Function

- [x] 1.1 Add `substitute_env_vars(obj, environ=None)` function to `worker.py` that recursively walks dicts/lists and performs regex substitution on string values using `os.environ` (or the provided mapping)
- [x] 1.2 Use regex pattern `\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)` to match both `${VAR}` and `$VAR` syntaxes, leaving unresolved placeholders unchanged

## 2. Integration

- [x] 2.1 Call `substitute_env_vars(mcp_servers)` in `process_task_in_container` immediately before `json.dumps(mcp_servers)` on the `mcp.json` line

## 3. Tests

- [x] 3.1 Add test for `$VAR` syntax substitution (single variable in a string value)
- [x] 3.2 Add test for `${VAR}` syntax substitution
- [x] 3.3 Add test for missing environment variable leaving placeholder unchanged
- [x] 3.4 Add test for nested JSON structures (variables at various depths)
- [x] 3.5 Add test for non-string values (numbers, booleans, nulls) passing through unchanged
- [x] 3.6 Add test for multiple variables in a single string value
- [x] 3.7 Add test for empty/no-variable config passing through unchanged
- [x] 3.8 Run full backend test suite and verify all tests pass
