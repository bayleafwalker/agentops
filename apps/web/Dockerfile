FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ARG SPRINTCTL_REVISION=unknown
LABEL org.opencontainers.image.vendor="agentops" \
      org.opencontainers.image.sprintctl-revision="${SPRINTCTL_REVISION}"

# Install the domain-owned command clients from named, clean source contexts;
# the cockpit invokes their public CLIs and does not receive their Git or local
# authority state.
COPY --from=actionq-source pyproject.toml /tmp/actionq/
COPY --from=actionq-source actionq /tmp/actionq/actionq
COPY --from=sprintctl-source pyproject.toml /tmp/sprintctl/
COPY --from=sprintctl-source sprintctl /tmp/sprintctl/sprintctl
RUN apk add --no-cache python3 py3-pip git && \
    pip3 install --break-system-packages /tmp/actionq && \
    pip3 install --break-system-packages "/tmp/sprintctl[served]" && \
    rm -rf /tmp/actionq /tmp/sprintctl

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
# The completion-alert consumer is an independently invoked bounded poller,
# not part of Next's traced server entrypoint. Keep its source modules in the
# runtime image so Appservice can run it as a least-privilege sidecar from the
# same reviewed artifact.
COPY --from=builder --chown=node:node /app/scripts/completion-alert-consumer.js ./scripts/completion-alert-consumer.js
COPY --from=builder --chown=node:node /app/lib/cockpit ./lib/cockpit

USER node
EXPOSE 3000
CMD ["node", "server.js"]
