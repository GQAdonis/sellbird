# Sellbird container image: the local Docker Compose setup and the hosted
# (Kubernetes) deployment use the same image. See docs/docker.md and
# openspec/changes/cluster-ready-container-image/design.md.
#
# Requires BuildKit (the default builder since Docker 23) for RUN --mount.
# Every input is pinned: the base image by digest, the Claude CLI by version and
# SHA-256 checksum. Bump a pin by editing its ARG and recording the source in
# the design document above.

# python:3.12.16-slim-trixie, multi-arch index digest (Docker Hub, 2026-11-08).
ARG PYTHON_IMAGE=python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
# Claude Code release 2.1.311 ("stable" channel on 2026-11-18); its checksums
# are pinned in the claude-cli stage below.
ARG CLAUDE_CODE_VERSION=2.1.311

# ---------------------------------------------------------------------------
# Stage 1: fetch the Claude CLI native binary and verify it. Nothing from this
# stage reaches the runtime image except the verified binary.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS claude-cli

# The checksums are the platforms.<platform>.checksum values of
# https://downloads.claude.ai/claude-code-releases/2.1.311/manifest.json,
# whose detached signature (manifest.json.sig) verifies against Anthropic's
# release signing key below.
ARG CLAUDE_CODE_VERSION
ARG CLAUDE_CODE_SHA256_LINUX_X64=86dc1fcc69498159eaf15f446613e847010f9036bfbbdffd4c49350be8489ada
ARG CLAUDE_CODE_SHA256_LINUX_ARM64=2e2496c9a8065df93acb0fca2d341f59a6b8777649b2e025ab8c9bcd5eef61f3
# "Anthropic Claude Code Release Signing <security@anthropic.com>", the
# fingerprint published at https://code.claude.com/docs/en/setup.
ARG CLAUDE_CODE_SIGNING_KEY_FPR=31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE
ARG CLAUDE_CODE_RELEASES=https://downloads.claude.ai/claude-code-releases
ARG CLAUDE_CODE_SIGNING_KEY_URL=https://downloads.claude.ai/keys/claude-code.asc
# Set by BuildKit from --platform (amd64 or arm64).
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# The build fails unless:
#   1. the downloaded binary's SHA-256 equals the pinned checksum (sha256sum -c);
#   2. the release manifest is signed by the pinned key (gpg VALIDSIG);
#   3. that signed manifest names the pinned version and lists the same checksum.
# Check 1 alone is the reproducibility guarantee; 2 and 3 prove the pinned value
# came from Anthropic's signed release and was not mistyped.
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) platform=linux-x64; expected="$CLAUDE_CODE_SHA256_LINUX_X64" ;; \
      arm64) platform=linux-arm64; expected="$CLAUDE_CODE_SHA256_LINUX_ARM64" ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    work="$(mktemp -d)"; cd "$work"; \
    base="$CLAUDE_CODE_RELEASES/$CLAUDE_CODE_VERSION"; \
    fetch() { curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$1" "$2"; }; \
    fetch claude "$base/$platform/claude"; \
    echo "$expected  claude" | sha256sum -c -; \
    fetch manifest.json "$base/manifest.json"; \
    fetch manifest.json.sig "$base/manifest.json.sig"; \
    fetch release-key.asc "$CLAUDE_CODE_SIGNING_KEY_URL"; \
    export GNUPGHOME="$work/gnupg"; mkdir -m 0700 "$GNUPGHOME"; \
    gpg --batch --quiet --import release-key.asc; \
    gpg --batch --status-fd 1 --verify manifest.json.sig manifest.json > gpg-status; \
    grep -Eq "^\[GNUPG:\] VALIDSIG [0-9A-F]+ .* ${CLAUDE_CODE_SIGNING_KEY_FPR}\$" gpg-status; \
    python -I -c 'import json, sys; m = json.load(open("manifest.json")); \
assert m.get("version") == sys.argv[1], "manifest version mismatch"; \
assert m["platforms"][sys.argv[2]]["checksum"] == sys.argv[3], "manifest checksum mismatch"' \
      "$CLAUDE_CODE_VERSION" "$platform" "$expected"; \
    install -D -m 0755 claude /out/claude; \
    cd /; rm -rf "$work"

# ---------------------------------------------------------------------------
# Stage 2: the runtime image.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE}

ARG CLAUDE_CODE_VERSION
# OCI metadata. CI passes the real values (--build-arg VCS_REF=$GITHUB_SHA ...).
ARG SELLBIRD_VERSION=0.4.0
ARG VCS_REF=unknown
ARG SOURCE_URL=https://github.com/ethanplusai/sellbird

LABEL org.opencontainers.image.title="sellbird" \
      org.opencontainers.image.description="Sellbird: the open-source outreach platform" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${SELLBIRD_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      dev.sellbird.claude-code.version="${CLAUDE_CODE_VERSION}"

# Writable state lives under /data only (SELLBIRD_HOME), so the root
# filesystem can be mounted read-only. /tmp must be a writable tmpfs at runtime
# (Python temp dirs, the per-call Claude working directory, Chromium); the Claude
# CLI's own config directory is on it too, so nothing the CLI writes survives a
# restart and nothing lands under /data or $HOME. The AI credential is read only
# from CLAUDE_CODE_OAUTH_TOKEN in the environment.
#
# SELLBIRD_CONTAINER=1 marks "inside a container": local mode prints no unlock
# link and `dashboard --url` is refused. Gateway mode is selected only by
# SELLBIRD_DASHBOARD_MODE=gateway at runtime; nothing here selects it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SELLBIRD_HOME=/data \
    SELLBIRD_CONTAINER=1 \
    SELLBIRD_MIGRATIONS_DIR=/app/migrations/postgres \
    SELLBIRD_HEALTHCHECK_PORT=5555 \
    HOME=/home/sellbird \
    TMPDIR=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    CLAUDE_CONFIG_DIR=/tmp/claude \
    DISABLE_AUTOUPDATER=1 \
    DISABLE_UPDATES=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

WORKDIR /app

# Python deps first (cached layer: rebuilds only when requirements or the
# pyproject extras change), then Chromium + its system libraries. The
# `hosted` (PyJWT) and `postgres` (psycopg[binary]) extras are read from
# pyproject.toml so the image can never drift from them; the project itself
# is not installed (the code runs from /app). pyproject.toml is only bind
# mounted for this step: copying it into /app would make /app look like a
# source checkout to sellbird.paths.
COPY requirements.txt .
RUN --mount=type=bind,source=pyproject.toml,target=/tmp/build/pyproject.toml \
    set -eu; \
    python -I -c 'import tomllib; \
extras = tomllib.load(open("/tmp/build/pyproject.toml", "rb"))["project"]["optional-dependencies"]; \
print("\n".join(extras["hosted"] + extras["postgres"]))' > /tmp/extras.txt; \
    pip install --no-cache-dir -r requirements.txt -r /tmp/extras.txt; \
    rm -f /tmp/extras.txt; \
    python -c "import jwt, psycopg; print('hosted and postgres extras ok')"; \
    playwright install --with-deps chromium; \
    rm -rf /var/lib/apt/lists/* /root/.cache

# The verified Claude CLI: root-owned and read-only to the runtime user. No
# installer script runs, so there is no launcher or auto-updater to write to
# $HOME (DISABLE_UPDATES also blocks `claude update`).
COPY --from=claude-cli /out/claude /usr/local/bin/claude

# Match the checkout owner on Linux; remain non-root. The home directory
# exists (some tools expect it) but holds nothing; under a read-only root it
# is read-only too.
ARG SELLBIRD_UID=1000
ARG SELLBIRD_GID=1000
RUN test "$SELLBIRD_UID" -gt 0 && test "$SELLBIRD_GID" -gt 0 \
    && groupadd --gid "$SELLBIRD_GID" sellbird \
    && useradd --create-home --uid "$SELLBIRD_UID" --gid "$SELLBIRD_GID" sellbird \
    && install -d -m 0700 -o sellbird -g sellbird /data \
    && chmod -R a+rX /ms-playwright

# Application code and migrations, root-owned (the runtime user cannot modify
# them). Docker Compose bind-mounts the checkout over /app instead.
COPY sellbird/ sellbird/
COPY migrations/ migrations/
# Shipped defaults: sellbird.home.seed_home copies any missing ones into
# SELLBIRD_HOME (/data) before every command, never overwriting. sys.prefix is
# /usr/local in this base image, so <prefix>/share/sellbird is where
# home.bundled_defaults() looks.
COPY sellbird.yaml /usr/local/share/sellbird/sellbird.yaml
COPY prompts/ /usr/local/share/sellbird/prompts/
COPY skills/ /usr/local/share/sellbird/skills/

USER sellbird

# Fail the build if the CLI is not the pinned version or lacks a flag Sellbird's
# isolation check requires (claude_runtime.check_cli). Its config directory is a
# throwaway so the probe leaves nothing in the image.
RUN set -eu; \
    probe="$(mktemp -d)"; \
    CLAUDE_CONFIG_DIR="$probe" claude --version | grep -q "^${CLAUDE_CODE_VERSION} "; \
    CLAUDE_CONFIG_DIR="$probe" python -c "from sellbird.claude_runtime import check_cli; print(check_cli())"; \
    rm -rf "$probe" /tmp/sellbird-claude-*; \
    test ! -e /home/sellbird/.claude && test ! -e /home/sellbird/.claude.json \
      && test ! -e /home/sellbird/.local

VOLUME ["/data"]
EXPOSE 5555

# Healthy = the dashboard accepts TCP connections. A TCP connect works in both
# modes: gateway mode answers any HTTP request without the public Host with
# 400, so an HTTP check would fail there. Kubernetes ignores HEALTHCHECK; the
# manifests use a tcpSocket probe on the same port. The heartbeat loop is started
# from the dashboard on demand, so database activity is not a liveness signal.
HEALTHCHECK --interval=1m --timeout=10s --start-period=1m --retries=3 \
  CMD python -c "import os, socket; socket.create_connection(('127.0.0.1', int(os.environ.get('SELLBIRD_HEALTHCHECK_PORT', '5555'))), timeout=5).close()"

# WebUI first: `docker run` serves the dashboard; it starts/stops the
# heartbeat loop itself. Any arguments replace the default command, so
# `docker compose run --rm sellbird setup` runs the setup wizard, and the
# hosted Deployment passes `dashboard --host 0.0.0.0` (refused unless
# SELLBIRD_DASHBOARD_MODE=gateway) and the migration Job `storage migrate`.
ENTRYPOINT ["python", "-m", "sellbird"]
CMD ["dashboard"]
