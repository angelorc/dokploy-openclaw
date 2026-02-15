# ── Stage 1: Build OpenClaw from source ──────────────────────
FROM node:22-bookworm AS builder

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git python3 make g++ ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

RUN corepack enable

WORKDIR /openclaw

ARG OPENCLAW_GIT_REF=main
RUN git clone --depth 1 --branch "${OPENCLAW_GIT_REF}" \
    https://github.com/nicepkg/openclaw.git .

# Patch: relax workspace protocol version requirements in extensions
RUN set -eux; \
  find ./extensions -name 'package.json' -type f | while read -r f; do \
    sed -i -E 's/"openclaw"[[:space:]]*:[[:space:]]*">=[^"]+"/"openclaw": "*"/g' "$f"; \
    sed -i -E 's/"openclaw"[[:space:]]*:[[:space:]]*"workspace:[^"]+"/"openclaw": "*"/g' "$f"; \
  done

RUN pnpm install --no-frozen-lockfile
RUN pnpm build
ENV OPENCLAW_PREFER_PNPM=1
RUN pnpm ui:install && pnpm ui:build

# ── Stage 2: Slim runtime ───────────────────────────────────
FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /openclaw /opt/openclaw/app

RUN printf '%s\n' '#!/usr/bin/env bash' 'exec node /opt/openclaw/app/openclaw.mjs "$@"' \
    > /usr/local/bin/openclaw \
  && chmod +x /usr/local/bin/openclaw

# Symlinks so ../../ relative paths from dist/ resolve correctly
RUN ln -s /opt/openclaw/app/docs /opt/openclaw/docs \
  && ln -s /opt/openclaw/app/assets /opt/openclaw/assets \
  && ln -s /opt/openclaw/app/package.json /opt/openclaw/package.json

# ── Stage 3: Final image with Caddy + config engine ─────────
FROM runtime

# Install Caddy from official APT repo
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    debian-keyring debian-archive-keyring apt-transport-https gpg \
  && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
  && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list \
  && apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    caddy python3-minimal \
  && rm -rf /var/lib/apt/lists/*

COPY Caddyfile /app/Caddyfile
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh
COPY static/ /app/static/

RUN mkdir -p /app/caddy.d

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8080}/healthz || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
