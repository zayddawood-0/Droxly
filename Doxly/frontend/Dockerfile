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
# Patches the base image's own system packages (e.g. libssl/libcrypto CVEs
# fixed upstream since node:22-alpine was published) — roadmap.md Phase 17's
# "hardened... image" objective, not a functional change to the app. Also
# removes the base image's bundled global npm install: the container starts
# via `node server.js` directly (never `npm run`/`npm start`), so npm and
# its own transitive dependencies are dead weight that only exists to be
# flagged by a vulnerability scan — verified via `docker scout cves` that
# every CRITICAL/HIGH finding on the unpatched image traced to
# /usr/local/lib/node_modules/npm, not to anything Doxly's own dependency
# tree or the running server actually executes.
RUN apk upgrade --no-cache \
  && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
  && addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# `npm run build`'s postbuild script (scripts/copy-standalone-assets.mjs)
# already copies public/ and .next/static into .next/standalone — one
# self-contained directory to copy, no separate asset copies to keep in sync.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Liveness check for orchestrators/Compose (roadmap.md Phase 17 — "Compose
# healthchecks finalized"). The marketing page (/) is fully static and never
# depends on the backend BFF, so this reflects the Next.js server's own
# health, not upstream availability. wget is BusyBox's built-in applet in
# this base image — no extra package needed. Targets 127.0.0.1 explicitly,
# not `localhost`: Alpine resolves `localhost` to the IPv6 loopback (::1)
# first, but HOSTNAME=0.0.0.0 above only binds the IPv4 wildcard, so
# `localhost` connection-refuses even though the server is genuinely up
# (verified by running the built image directly — the exact class of bug a
# real container run catches that reading the Dockerfile alone wouldn't).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --spider -q http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
