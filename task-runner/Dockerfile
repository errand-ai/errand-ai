FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

FROM debian:bookworm-slim AS git-builder
ARG GH_VERSION=2.67.0
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    ca-certificates \
    busybox \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*
# Download gh CLI (static Go binary — no shared library staging needed)
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${TARGETARCH}.tar.gz" \
    | tar xz -C /tmp && cp "/tmp/gh_${GH_VERSION}_linux_${TARGETARCH}/bin/gh" /usr/local/bin/gh
# Create .ssh directory with correct permissions (preserved by COPY --from)
RUN mkdir -p /home/nonroot/.ssh && chmod 700 /home/nonroot/.ssh
# Stage shared libraries needed by git, ssh, and busybox into an arch-independent
# path. ldd lists all .so dependencies; we copy them preserving the full directory
# structure so the dynamic linker finds them regardless of architecture.
# We exclude libraries already present in the distroless base image to avoid
# glibc version conflicts.
RUN mkdir -p /staged-libs && \
    echo "libc.so libdl.so libm.so libpthread.so librt.so libresolv.so libz.so libexpat.so libgcc_s.so libnsl.so libutil.so libcrypt.so liblzma.so libtirpc.so libtinfo.so libncursesw.so libreadline.so libhistory.so libbz2.so libcom_err.so libkeyutils.so" > /tmp/skip_libs && \
    for bin in /usr/bin/git /usr/bin/ssh /usr/bin/ssh-keygen /usr/bin/ssh-keyscan /usr/lib/git-core/git-remote-https /bin/busybox /usr/bin/curl /usr/bin/jq; do \
      ldd "$bin" 2>/dev/null | awk '/ => \// {print $3}' | while read lib; do \
        basename=$(basename "$lib" | sed 's/\.so.*/.so/') ; \
        if ! grep -qw "$basename" /tmp/skip_libs; then \
          mkdir -p "/staged-libs$(dirname "$lib")" && \
          cp -L "$lib" "/staged-libs$lib" 2>/dev/null || true ; \
        fi ; \
      done ; \
    done

FROM node:22-bookworm-slim AS node-builder
RUN npm install -g @fission-ai/openspec@latest
# Resolve the openspec entry point for the wrapper script
RUN OPENSPEC_ENTRY=$(readlink -f /usr/local/bin/openspec) && \
    echo "#!/bin/sh" > /usr/local/bin/openspec-sh && \
    echo "exec /usr/local/bin/node $OPENSPEC_ENTRY \"\$@\"" >> /usr/local/bin/openspec-sh && \
    chmod +x /usr/local/bin/openspec-sh

FROM gcr.io/distroless/python3-debian12:nonroot
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY main.py /app/main.py
COPY tool_registry.py /app/tool_registry.py

# Copy shared libraries first (needed by all binaries below)
COPY --from=git-builder /staged-libs/ /
COPY --from=git-builder /etc/ssl/certs /etc/ssl/certs

# Copy git binary and its dependencies
COPY --from=git-builder /usr/bin/git /usr/bin/git
COPY --from=git-builder /usr/lib/git-core /usr/lib/git-core
COPY --from=git-builder /usr/share/git-core /usr/share/git-core

# Copy ssh client binaries
COPY --from=git-builder /usr/bin/ssh /usr/bin/ssh
COPY --from=git-builder /usr/bin/ssh-keygen /usr/bin/ssh-keygen
COPY --from=git-builder /usr/bin/ssh-keyscan /usr/bin/ssh-keyscan

# Copy curl binary (for HTTP requests in tasks)
COPY --from=git-builder /usr/bin/curl /usr/bin/curl

# Copy jq binary (for JSON processing in tasks)
COPY --from=git-builder /usr/bin/jq /usr/bin/jq

# Copy gh CLI binary (static Go binary)
COPY --from=git-builder /usr/local/bin/gh /usr/local/bin/gh

# Copy node binary and openspec CLI from node-builder
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=node-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-builder /usr/local/bin/openspec-sh /usr/local/bin/openspec

# Copy busybox and create shell symlinks (provides /bin/sh, cat, ls, grep, etc.)
# Libraries must be copied before this step so busybox can execute.
# Distroless nonroot image defaults to UID 65532; switch to root to write /bin.
COPY --from=git-builder /bin/busybox /bin/busybox
USER root
RUN ["/bin/busybox", "sh", "-c", "/bin/busybox --install -s /bin"]
USER nonroot

# Copy .ssh directory (permissions 700 preserved from git-builder)
COPY --from=git-builder --chown=65532:65532 /home/nonroot/.ssh /home/nonroot/.ssh

ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
WORKDIR /workspace
ENTRYPOINT ["python3", "/app/main.py"]
