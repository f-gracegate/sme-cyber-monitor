# Production image: a standalone Next.js server, running as a non-root user.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Branding is baked in at build time (see lib/brand.ts).
ARG NEXT_PUBLIC_PRODUCT_NAME
ARG NEXT_PUBLIC_POWERED_BY_NAME
# The /api proxy target is fixed at build time. In production Caddy sends /api straight to the
# backend, so this is only a fallback for running the web container on its own.
ARG API_INTERNAL_URL=http://backend:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npx next build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:3000/login >/dev/null || exit 1
CMD ["node", "server.js"]
