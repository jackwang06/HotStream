# syntax=docker/dockerfile:1

# ── deps: install all deps (incl. dev) for building ──
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ── builder: build the Next.js standalone server + bundle the migration scripts ──
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build && npm run build:scripts

# ── runner: lean runtime image ──
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Next.js standalone output (server.js + traced node_modules) and static assets.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Legacy HTML served by the authenticated route handler (read from cwd/legacy).
COPY --from=builder /app/legacy ./legacy
# Self-contained migration/seed bundles (pg + @next/env inlined; no node_modules needed).
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/entrypoint.sh ./entrypoint.sh

RUN chmod +x ./entrypoint.sh && chown -R nextjs:nodejs /app
USER nextjs
EXPOSE 3000
CMD ["./entrypoint.sh"]
