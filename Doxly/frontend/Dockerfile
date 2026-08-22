# Doxly frontend — multi-stage build (specs/devops.md §1, skills/devops.md
# "keep the image lean"). Only the `output: "standalone"` runtime bundle and
# its resolved dependencies end up in the final image — no dev dependencies,
# no source maps, no build cache.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Runtime image — non-root, minimal (skills/devops.md: "never bake a secret
# into an image layer"; secrets are injected via environment variables at
# container start, never ARG/ENV baked at build time).
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# `npm run build`'s postbuild script (scripts/copy-standalone-assets.mjs)
# already copies public/ and .next/static into .next/standalone — one
# self-contained directory to copy, no separate asset copies to keep in sync.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
