# syntax=docker/dockerfile:1

# ---- Build the static bundle ----
FROM node:24-alpine AS build

WORKDIR /app

# --ignore-scripts: no dependency install hooks run in the build. The only
# native devDependency (sharp) is used by the icon script, not by the build.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts --no-audit --no-fund

COPY . .
RUN npm run build

# ---- Serve with unprivileged nginx (uid 101, port 8080) ----
FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime

# Pick up Alpine security fixes released since the base image was built
USER root
RUN apk upgrade --no-cache
USER 101

COPY --chown=root:root nginx.conf /etc/nginx/conf.d/default.conf
COPY --chown=root:root security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build --chown=root:root /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]
