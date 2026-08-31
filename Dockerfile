# Stage 1: Build frontend (runs natively on build platform — output is platform-independent JS/CSS)
FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN --mount=type=secret,id=npm_token \
    if [ -f /run/secrets/npm_token ]; then \
      echo "//npm.pkg.github.com/:_authToken=$(cat /run/secrets/npm_token)" >> .npmrc; \
    fi && \
    npm ci
COPY frontend/ .
RUN npm run build

# Stage 1b: Fetch bundled gws agent skills (platform-independent SKILL.md files)
FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS gws-skills
ARG GWS_VERSION=0.22.5
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Deliberately not `git clone`. This is the same fetch as the task-runner image's
# gws-builder stage and must stay identical to it — two subtly different fetches
# of the same upstream artefact is how one gets fixed and the other rots. An
# unauthenticated clone of this public repo failed four consecutive task-runner
# builds on 2026-08-31 with `could not read Username for 'https://github.com'`;
# build-errand carried the same exposure and was spared only by chance.
RUN --mount=type=secret,id=github_token \
    set -eu; \
    GWS_SRC_URL="https://codeload.github.com/googleworkspace/cli/tar.gz/refs/tags/v${GWS_VERSION}"; \
    if [ -f /run/secrets/github_token ]; then \
      curl -fsSL -H "Authorization: Bearer $(cat /run/secrets/github_token)" \
        -o /tmp/gws-src.tar.gz "${GWS_SRC_URL}"; \
    else \
      curl -fsSL -o /tmp/gws-src.tar.gz "${GWS_SRC_URL}"; \
    fi; \
    mkdir -p /tmp/gws-src /gws-skills; \
    tar xzf /tmp/gws-src.tar.gz -C /tmp/gws-src; \
    # The archive's top-level directory is derived from the tag (cli-0.22.5/).
    # Glob it rather than reconstructing the name, so an upstream change to that
    # convention surfaces as the explicit failure below, not a silent miss.
    GWS_SRC_DIR="$(find /tmp/gws-src -mindepth 1 -maxdepth 1 -type d | head -n1)"; \
    cp -r "${GWS_SRC_DIR}"/skills/gws-* /gws-skills/ 2>/dev/null || true; \
    if [ -z "$(find /gws-skills -mindepth 2 -name SKILL.md -print -quit)" ]; then \
      echo "ERROR: no gws-* skill directory containing a SKILL.md was extracted from ${GWS_SRC_URL}" >&2; \
      exit 1; \
    fi; \
    rm -rf /tmp/gws-src /tmp/gws-src.tar.gz

# Stage 2: Download Python wheels (runs natively, downloads wheels for target platform)
FROM --platform=$BUILDPLATFORM python:3.13 AS build
ARG TARGETPLATFORM
WORKDIR /app
COPY errand/requirements.txt .
RUN <<EOF
  set -e
  case "$TARGETPLATFORM" in
    linux/amd64) ARCH="x86_64" ;;
    linux/arm64) ARCH="aarch64" ;;
    *) echo "Unsupported or unset TARGETPLATFORM: '$TARGETPLATFORM' (expected linux/amd64 or linux/arm64)" >&2; exit 1 ;;
  esac
  # Download packages as binary wheels for the target platform.
  # Accept both the modern (manylinux_2_28) and legacy (manylinux2014 / _2_17) glibc
  # baselines: pip's --platform does not auto-accept older tags, and our pinned deps
  # are split across both (e.g. asyncpg 0.31 is 2_28-only, psycopg2-binary 2.9.12 is
  # 2014-only). The 3.13-slim runtime's glibc (>= 2.28 on current Debian bases)
  # satisfies both manylinux baselines.
  # feedparser was previously excluded here and wheel-built by name, because its
  # old dependency sgmllib3k shipped source-only. feedparser 6.0.13 replaced that
  # with feedparser-sgmllib, which publishes a py3-none-any wheel — so the normal
  # path below now covers it. The hand-maintained exclusion is what broke the
  # build when that dependency changed: --no-deps meant nothing discovered the
  # new name automatically.
  pip download --no-cache-dir \
    --only-binary=:all: \
    --platform "manylinux_2_28_${ARCH}" \
    --platform "manylinux2014_${ARCH}" \
    --python-version 313 \
    --implementation cp \
    --abi cp313 \
    -d /wheels \
    -r requirements.txt
EOF

# Stage 3: Final image (target platform — minimal QEMU usage: apt-get + pip install from local wheels)
FROM python:3.13-slim
ARG APP_VERSION="dev"
ENV APP_VERSION=$APP_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY errand/requirements.txt .
COPY --from=build /wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt && rm -rf /tmp/wheels
COPY errand/ .
COPY VERSION .
COPY --from=frontend-build /frontend/dist ./static/
COPY --from=gws-skills /gws-skills /app/system-skills/gws
COPY system-skills/cloud-storage /app/system-skills/cloud-storage
COPY system-skills/hindsight /app/system-skills/hindsight
COPY system-skills/repo-context /app/system-skills/repo-context
COPY system-skills/binary-files /app/system-skills/binary-files
COPY system-skills/shared-workspace /app/system-skills/shared-workspace
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
