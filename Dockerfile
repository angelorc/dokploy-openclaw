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
    https://github.com/openclaw/openclaw.git .

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

COPY openclaw.json.example /app/openclaw.json.example
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# Ensure consistent paths for both entrypoint and docker exec sessions
ENV HOME=/data
ENV OPENCLAW_STATE_DIR=/data/.openclaw
ENV OPENCLAW_WORKSPACE_DIR=/data/workspace

EXPOSE 18789

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -sf -H "Authorization: Bearer $(cat /data/.openclaw/gateway.token 2>/dev/null)" \
    http://localhost:${OPENCLAW_GATEWAY_PORT:-18789}/healthz || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
