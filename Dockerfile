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

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
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

# Extract only SANE core and scanimage; other backends are not used.
RUN set -eux; \
    printf '%s\n' \
        'path-exclude=/usr/share/doc/*' \
        'path-include=/usr/share/doc/*/copyright' \
        'path-exclude=/usr/share/man/*' \
        'path-exclude=/usr/share/info/*' \
        'path-exclude=/usr/share/locale/*' \
        > /etc/dpkg/dpkg.cfg.d/01_nodoc; \
    dpkg --add-architecture i386; \
    apt-get update; \
    apt-get install --yes --no-install-recommends \
        csh \
        cups-daemon \
        cups-client \
        cups-filters \
        curl \
        gosu \
        libc6:i386 \
        libgcc-s1:i386 \
        libjpeg62-turbo \
        libxml2 \
        libpng16-16 \
        libstdc++6:i386 \
        libudev1 \
        libusb-0.1-4 \
        libusb-1.0-0 \
        zlib1g:i386; \
    mkdir -p \
        /tmp/cups-packages \
        /tmp/cups-root \
        /tmp/sane-packages \
        /tmp/sane-root; \
    (cd /tmp/cups-packages && \
        apt-get download cups cups-core-drivers); \
    for archive in /tmp/cups-packages/*.deb; do \
        dpkg-deb --extract "$archive" /tmp/cups-root; \
    done; \
    install -D \
        /tmp/cups-root/usr/lib/cups/backend-available/socket \
        /usr/lib/cups/backend/socket; \
    install -D \
        /tmp/cups-root/usr/lib/cups/filter/commandtops \
        /usr/lib/cups/filter/commandtops; \
    install -D \
        /tmp/cups-root/usr/lib/cups/filter/pstops \
        /usr/lib/cups/filter/pstops; \
    (cd /tmp/sane-packages && \
        apt-get download libsane1 libsane-common sane-utils); \
    for archive in /tmp/sane-packages/*.deb; do \
        dpkg-deb --extract "$archive" /tmp/sane-root; \
    done; \
    install -D /tmp/sane-root/usr/bin/scanimage /usr/bin/scanimage; \
    cp -a /tmp/sane-root/usr/lib/x86_64-linux-gnu/libsane.so* \
        /usr/lib/x86_64-linux-gnu/; \
    cp -a /tmp/sane-root/etc/sane.d /etc/; \
    mkdir -p /usr/lib/x86_64-linux-gnu/sane; \
    printf '%s\n' 'brother4' > /etc/sane.d/dll.conf; \
    curl --fail --location --silent --show-error \
        https://download.brother.com/welcome/dlf101533/dcp1610wlpr-3.0.1-1.i386.deb \
        --output /tmp/dcp1610wlpr.deb; \
    curl --fail --location --silent --show-error \
        https://download.brother.com/welcome/dlf101532/dcp1610wcupswrapper-3.0.1-1.i386.deb \
        --output /tmp/dcp1610wcupswrapper.deb; \
    curl --fail --location --silent --show-error \
        https://download.brother.com/welcome/dlf105200/brscan4-0.4.11-1.amd64.deb \
        --output /tmp/brscan4.deb; \
    mkdir -p /etc/udev/rules.d; \
    dpkg --force-all --install \
        /tmp/dcp1610wlpr.deb \
        /tmp/dcp1610wcupswrapper.deb \
        /tmp/brscan4.deb; \
    apt-get purge --yes --auto-remove curl; \
    rm -f /tmp/dcp1610wlpr.deb /tmp/dcp1610wcupswrapper.deb /tmp/brscan4.deb; \
    rm -rf \
        /tmp/cups-packages /tmp/cups-root \
        /tmp/sane-packages /tmp/sane-root; \
    rm -rf /var/lib/apt/lists/*; \
    rm -rf /var/cache/apt/archives/*; \
    rm -rf /usr/share/man/* /usr/share/info/* /usr/share/locale/*; \
    rm -rf /usr/share/cups/doc-root /usr/share/cups/locale \
        /usr/share/cups/templates; \
    useradd --system --create-home --home-dir /home/app --shell /usr/sbin/nologin app; \
    usermod --append --groups lp app; \
    mkdir -p /run/cups /var/spool/cups /app/static/css

COPY --from=python-build /opt/venv /opt/venv
COPY templates ./templates
COPY static/js ./static/js
COPY static/locales ./static/locales
COPY docker ./docker
COPY --from=frontend-build /frontend/dist/app.css ./static/css/app.css
RUN chmod +x /app/docker/start-web.sh

FROM runtime AS scratch-rootfs

COPY docker/build-scratch-rootfs.sh /tmp/build-scratch-rootfs.sh
RUN set -eux; \
    apt-get update; \
    mkdir -p /tmp/busybox-packages /tmp/busybox-root; \
    (cd /tmp/busybox-packages && apt-get download busybox-static); \
    dpkg-deb --extract /tmp/busybox-packages/*.deb /tmp/busybox-root; \
    bash /tmp/build-scratch-rootfs.sh /tmp/busybox-root/bin/busybox; \
    rm -rf /tmp/busybox-packages /tmp/busybox-root \
        /tmp/build-scratch-rootfs.sh /var/lib/apt/lists/*

FROM scratch AS final

COPY --from=scratch-rootfs /rootfs/ /

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ROOT=/app \
    PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    PORT=8080

WORKDIR /app
EXPOSE 8080

CMD ["/opt/venv/bin/supervisord", "--nodaemon", "--configuration", "/app/docker/supervisord.conf"]
