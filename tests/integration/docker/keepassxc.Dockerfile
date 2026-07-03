# KeePassXC running headless under Xvfb, exposed to a browser via noVNC.
#
# Build:
#   docker build \
#     --build-arg KPXC_VERSION=2.7.9 \  # optional; defaults to latest from the official PPA
#     -f tests/integration/docker/keepassxc.Dockerfile \
#     -t kpxc-test-keepassxc tests/integration/docker
#
# The image runs as a non-root user `kpxc` (uid 1000) so the Browser Integration
# socket it creates at $XDG_RUNTIME_DIR is reachable by the sibling client
# container (which runs as the same uid and mounts the same named volume).

FROM debian:bookworm-slim

ARG KPXC_VERSION=
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg software-properties-common \
        xvfb x11vnc fluxbox novnc websockify \
        supervisor \
        dbus-x11 \
        xdotool \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Install KeePassXC from the official PPA (works on Debian via the deb repo).
RUN install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL "https://keepassxc.org/keepassxc_release.key" \
       | gpg --dearmor -o /etc/apt/keyrings/keepassxc.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/keepassxc.gpg] http://ppa.launchpad.net/phoerious/keepassxc/ubuntu jammy main" \
       > /etc/apt/sources.list.d/keepassxc.list \
    && apt-get update \
    && if [ -n "$KPXC_VERSION" ]; then \
         apt-get install -y --no-install-recommends "keepassxc=${KPXC_VERSION}*"; \
       else \
         apt-get install -y --no-install-recommends keepassxc; \
       fi \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash kpxc \
    && mkdir -p /run/user/1000 \
    && chown kpxc:kpxc /run/user/1000 \
    && chmod 0700 /run/user/1000

COPY supervisord.conf /etc/supervisor/conf.d/kpxc.conf
COPY entrypoint-keepassxc.sh /usr/local/bin/entrypoint-keepassxc.sh
RUN chmod +x /usr/local/bin/entrypoint-keepassxc.sh

ENV DISPLAY=:1 \
    XDG_RUNTIME_DIR=/run/user/1000 \
    HOME=/home/kpxc \
    USER=kpxc

EXPOSE 6080

HEALTHCHECK --interval=3s --timeout=2s --start-period=20s --retries=20 \
    CMD test -S "$XDG_RUNTIME_DIR/org.keepassxc.KeePassXC.BrowserServer" || exit 1

USER kpxc
WORKDIR /home/kpxc

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/kpxc.conf", "-n"]
