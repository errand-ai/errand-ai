## 1. Branch and version

- [x] 1.1 Create branch `bundle-hindsight-runtime` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` (minor — a new published image and changed compose defaults)

## 2. Report the upstream gap

Do this first; if upstream accepts it, section 3 becomes a much smaller change.

- [x] 2.1 Open an issue on `vectorize-io/hindsight` noting that the slim image ships `onnxruntime`, `tokenizers`, `huggingface_hub` and `OnnxEmbeddings`, but that `OnnxEmbeddings.initialize()` cannot run because `transformers` is absent
- [x] 2.2 Record the issue URL in `design.md` under Open Questions

## 3. Derived image

- [x] 3.1 Choose and pin the exact upstream slim tag; record why that tag in `design.md`
- [x] 3.2 Add `Dockerfile.hindsight` deriving from the pinned tag and installing `transformers` and `flashrank` into `/app/api/.venv` with `uv`
- [x] 3.3 Bake the `intfloat/multilingual-e5-small` ONNX graph plus tokenizer, and the FlashRank `ms-marco-MiniLM-L-12-v2` model, into the image at the paths the runtime resolves
- [x] 3.4 Add a build-time assertion that imports the ONNX provider, initialises it, and checks the reported dimension is 384 — failing the build otherwise
- [x] 3.5 Verify no `torch` or `sentence-transformers` is present in the built image
- [x] 3.6 Confirm the image starts with no network access and an empty cache volume, and that both providers initialise

## 4. CI and dependency tracking

- [x] 4.1 Add the image to the CI build/publish workflow alongside the existing two images
- [x] 4.2 Add a Renovate rule tracking the pinned upstream base tag so a bump arrives as a reviewable PR
- [x] 4.3 Confirm the build fails, rather than publishing, when the assertion in 3.4 does not hold

## 5. Single database

- [x] 5.1 Write a failing test asserting that alembic's migrations touch only the `public` schema
- [x] 5.2 Set `HINDSIGHT_API_DATABASE_SCHEMA=hindsight` and point Hindsight's connection string at the errand database in both compose files
- [x] 5.3 Remove `CREATE DATABASE hindsight` from `deploy/init-databases.sh`
- [x] 5.4 Ensure the `vector` extension is installed in the errand database before Hindsight first connects
- [x] 5.5 Verify a fresh `docker compose up` produces one database with `public` and `hindsight` schemas, and that memory operations work end to end

## 6. Control Plane opt-in

- [x] 6.1 Move the Control Plane into its own compose service behind a profile, following the `workspace-gateway` profile pattern
- [x] 6.2 Remove the unconditional `9999:9999` publication from both compose files
- [x] 6.3 Wire the Control Plane's API URL and bearer from the same values the API service uses
- [x] 6.4 Verify a default `docker compose up` starts no Control Plane, and that selecting the profile starts a working one

## 7. Volume ownership

- [x] 7.1 Write a failing test or scripted check that a first-run bring-up of `deploy/docker-compose.yml` with empty volumes does not raise `PermissionError`
- [x] 7.2 Add the chown initialisation step to `deploy/docker-compose.yml` covering both the data and cache directories
- [x] 7.3 Confirm `testing/docker-compose.yml` covers both directories as well

## 8. Server-generated MCP bearer

- [x] 8.1 Write failing tests: a token is generated when none is configured; generation is idempotent across restarts; an operator-supplied token is never overwritten; the generated value is masked by `GET /api/settings`
- [x] 8.2 Generate and persist the bearer when a Hindsight URL is configured and no token is resolved from env or settings
- [x] 8.3 Pass the resolved token to the Hindsight service as `HINDSIGHT_API_TENANT_API_KEY` (with `HINDSIGHT_API_TENANT_EXTENSION` set to the built-in API-key extension) and to the Control Plane as `HINDSIGHT_CP_DATAPLANE_API_KEY`, in both compose files
- [x] 8.4 Confirm the Hindsight MCP endpoint rejects an unauthenticated request and accepts the injected bearer

## 9. Switch the compose files to the derived image

- [x] 9.1 Replace the Hindsight image in both compose files with the published derived image
- [x] 9.2 Remove any embeddings or reranker environment variables now covered by the image defaults
- [x] 9.3 Run a full `docker compose -f testing/docker-compose.yml up --build` and exercise a task that retains and recalls

## 10. Documentation

- [x] 10.1 Update `CLAUDE.md` where it describes Hindsight configuration, including the corrected image sizes and RAM figures
- [x] 10.2 Document that the Control Plane is opt-in and how to start it

## 11. Archive

- [x] 11.1 Run the full errand test suite
- [x] 11.2 `openspec archive bundle-hindsight-runtime -y` and commit the result in this PR

## Post-merge notes

- The derived image's first published build is what the compose files reference; confirm the tag resolves after the merge build completes.
- If the upstream issue from section 2 is accepted in a later release, revisit whether the derived image can be dropped in favour of stock slim.
- Re-verify the redeployed build after archiving, since archiving produces a new image tag.
