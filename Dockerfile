FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY tailwind.config.js ./
COPY assets ./assets
COPY templates ./templates
COPY static/js ./static/js
RUN mkdir -p dist && npm run build
  
FROM python:3.12-slim-bookworm AS python-build

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /build
COPY scanner-app/pyproject.toml scanner-app/uv.lock scanner-app/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY scanner-app/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ROOT=/app \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

RUN set -eux; \
    dpkg --add-architecture i386; \
    apt-get update; \
    apt-get install --yes --no-install-recommends \
        ca-certificates \
        csh \
        cups \
        cups-client \
        cups-filters \
        curl \
        gosu \
        libc6:i386 \
        libgcc-s1:i386 \
        libstdc++6:i386 \
        libusb-0.1-4 \
        libusb-1.0-0 \
        libsane1 \
        sane-utils \
        supervisor \
        zlib1g:i386; \
    curl --fail --location --silent --show-error \
        https://download.brother.com/welcome/dlf101533/dcp1610wlpr-3.0.1-1.i386.deb \
        --output /tmp/dcp1610wlpr.deb; \
    curl --fail --location --silent --show-error \
        https://download.brother.com/welcome/dlf101532/dcp1610wcupswrapper-3.0.1-1.i386.deb \
        --output /tmp/dcp1610wcupswrapper.deb; \
    curl --fail --location --silent --show-error \
        https://download.brother.com/welcome/dlf105200/brscan4-0.4.11-1.amd64.deb \
        --output /tmp/brscan4.deb; \
    dpkg --force-all --install \
        /tmp/dcp1610wlpr.deb \
        /tmp/dcp1610wcupswrapper.deb \
        /tmp/brscan4.deb; \
    apt-get purge --yes --auto-remove curl; \
    rm -f /tmp/dcp1610wlpr.deb /tmp/dcp1610wcupswrapper.deb /tmp/brscan4.deb; \
    rm -rf /var/lib/apt/lists/*; \
    rm -rf /var/cache/apt/archives/*; \
    useradd --system --create-home --home-dir /home/app --shell /usr/sbin/nologin app; \
    usermod --append --groups lp app; \
    mkdir -p /run/cups /var/spool/cups

COPY --from=python-build /opt/venv /opt/venv
COPY templates ./templates
COPY static/js ./static/js
COPY static/locales ./static/locales
COPY docker ./docker
RUN mkdir -p /app/static/css
COPY --from=frontend-build /frontend/dist/app.css ./static/css/app.css
RUN chmod +x /app/docker/start-web.sh

EXPOSE 8080

CMD ["/usr/bin/supervisord", "--nodaemon", "--configuration", "/app/docker/supervisord.conf"]
