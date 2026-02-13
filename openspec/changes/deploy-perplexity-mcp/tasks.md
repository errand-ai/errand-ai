## 1. Helm Chart Values

- [x] 1.1 Add `perplexity` section to `helm/content-manager/values.yaml` with defaults: `existingSecret: ""`, `replicaCount: 1`, `image.repository: "mcp/perplexity-ask"`, `image.tag: "latest"`, `image.pullPolicy: "IfNotPresent"`, `service.port: 8000`

## 2. Perplexity Deployment and Service Templates

- [x] 2.1 Create `helm/content-manager/templates/perplexity-deployment.yaml` — Deployment gated by `{{- if .Values.perplexity.existingSecret }}`, using `envFrom.secretRef`, exposing container port 8000, with standard labels and component `perplexity-mcp`
- [x] 2.2 Create `helm/content-manager/templates/perplexity-service.yaml` — Service gated by `{{- if .Values.perplexity.existingSecret }}`, targeting port 8000, selecting the perplexity-mcp component pods

## 3. Worker Deployment Template

- [x] 3.1 Update `helm/content-manager/templates/worker-deployment.yaml` to add `USE_PERPLEXITY` and `PERPLEXITY_URL` env vars on the worker container, conditional on `{{- if .Values.perplexity.existingSecret }}`. Set `PERPLEXITY_URL` to `http://{{ include "content-manager.fullname" . }}-perplexity-mcp:{{ .Values.perplexity.service.port }}/sse`

## 4. Worker Python Code

- [x] 4.1 In `process_task_in_container()` in `backend/worker.py`, before the `mcp.json` line, check `os.environ.get("USE_PERPLEXITY") == "true"` and if so inject `{"perplexity-ask": {"url": "$PERPLEXITY_URL"}}` into `mcp_servers["mcpServers"]` — only if `"perplexity-ask"` is not already present (database value takes precedence)
- [x] 4.2 In `process_task_in_container()`, when `USE_PERPLEXITY` is `"true"`, append a Perplexity usage instruction block to the `system_prompt` string before writing `system_prompt.txt` into the container

## 5. Tests

- [x] 5.1 Add test: when `USE_PERPLEXITY=true` and `PERPLEXITY_URL` is set, `perplexity-ask` entry is injected into `mcp.json` and `$PERPLEXITY_URL` is substituted
- [x] 5.2 Add test: when `USE_PERPLEXITY` is unset/not `"true"`, no `perplexity-ask` entry is injected and system prompt is unchanged
- [x] 5.3 Add test: when database `mcp_servers` already has a `perplexity-ask` key, the database value is preserved (not overwritten by injection)
- [x] 5.4 Add test: when `USE_PERPLEXITY=true`, system prompt has the Perplexity instruction block appended
