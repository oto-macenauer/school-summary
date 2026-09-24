# syntax=docker/dockerfile:1

# ---- Build: resolve the locked dependencies into a self-contained venv ----
FROM ghcr.io/astral-sh/uv:0.12.5-python3.14-trixie-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Dependencies first so app changes don't invalidate the layer
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# ---- Runtime: plain Python, no uv/build tooling, non-root ----
FROM python:3.14-slim-trixie AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DATA_DIR=/app/app_data \
    HOME=/tmp

# Pick up security fixes released since the base image was built, then
# create the unprivileged user. The app data dir is its only writable path.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid "${APP_GID}" app \
    && useradd --system --uid "${APP_UID}" --gid app --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir -p /app/app_data \
    && chown app:app /app/app_data

WORKDIR /app

# Code and venv stay root-owned: the process can read but not modify them
COPY --from=build /opt/venv /opt/venv
COPY app/ ./app/

USER app:app

EXPOSE 8000
VOLUME ["/app/app_data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
