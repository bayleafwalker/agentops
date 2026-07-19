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

# Install the domain-owned command clients. sprintctl is brought in through a
# named, clean sprintctl source context at image build time; the cockpit only
# invokes its public authority CLI and never implements transition logic.
COPY vendor/actionq-0.1.1-py3-none-any.whl /tmp/actionq-0.1.1-py3-none-any.whl
# Do not copy the source worktree's .git or local .sprintctl state into the
# image. The runner needs only the package metadata and public CLI module.
COPY --from=sprintctl-source pyproject.toml /tmp/sprintctl/
COPY --from=sprintctl-source sprintctl /tmp/sprintctl/sprintctl
RUN apk add --no-cache python3 py3-pip && \
    pip3 install --break-system-packages "psycopg[binary]" && \
    pip3 install --break-system-packages /tmp/actionq-0.1.1-py3-none-any.whl && \
    pip3 install --break-system-packages --no-deps /tmp/sprintctl && \
    rm -rf /tmp/actionq-0.1.1-py3-none-any.whl /tmp/sprintctl

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node
EXPOSE 3000
CMD ["node", "server.js"]
