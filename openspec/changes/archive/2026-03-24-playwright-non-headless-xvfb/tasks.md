## 1. Docker Compose (errand)

- [x] 1.1 Update `testing/docker-compose.yml` playwright service: override entrypoint with Xvfb + headed MCP server command, add `shm_size: '2gb'`
- [x] 1.2 Update `deploy/docker-compose.yml` playwright service: same entrypoint override and `shm_size: '2gb'`

## 2. Kubernetes / Helm (errand)

- [x] 2.1 Update `helm/errand/values.yaml`: change `memoryLimit` from `512Mi` to `768Mi`
- [x] 2.2 Update `helm/errand/templates/playwright-deployment.yaml`: override command with Xvfb + headed MCP server, add emptyDir volume (`medium: Memory`, `sizeLimit: 2Gi`) mounted at `/dev/shm`

## 3. errand-desktop

- [x] 3.1 Update `ContainerEngine.swift` Docker runtime command override for playwright: replace current args with Xvfb entrypoint shell command, add `--shm-size=2g` to container run flags
- [x] 3.2 Update `ContainerEngine.swift` Apple Containerization runtime command override for playwright: replace current args with Xvfb entrypoint shell command

## 4. Specs and Version

- [x] 4.1 Bump VERSION file
- [x] 4.2 Test locally with `docker compose -f testing/docker-compose.yml up --build` and verify Playwright MCP responds on `/mcp` endpoint

## 5. Delta Spec Sync

- [x] 5.1 Sync `playwright-mcp-image` delta spec to main specs
- [x] 5.2 Sync `playwright-standalone` delta spec to main specs
