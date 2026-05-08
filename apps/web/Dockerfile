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

# Install actionctl for dispatch and session reads
COPY vendor/actionq-0.1.0-py3-none-any.whl /tmp/actionq-0.1.0-py3-none-any.whl
RUN apk add --no-cache python3 py3-pip && \
    pip3 install --break-system-packages "psycopg[binary]" && \
    pip3 install --break-system-packages --no-deps /tmp/actionq-0.1.0-py3-none-any.whl && \
    rm /tmp/actionq-0.1.0-py3-none-any.whl

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node
EXPOSE 3000
CMD ["node", "server.js"]
