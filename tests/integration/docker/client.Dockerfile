# Sibling container that runs the integration test suite against the keepassxc
# container's Browser Integration socket. Runs as the same uid (1000) and
# shares the `kpxc-socket` named volume, so the unix-domain socket KeePassXC
# creates is reachable here without any host-side socket gymnastics — which is
# what makes the setup work the same on Linux, macOS, and Windows.

FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN useradd -m -u 1000 -s /bin/bash kpxc \
    && mkdir -p /run/user/1000 \
    && chown kpxc:kpxc /run/user/1000 \
    && chmod 0700 /run/user/1000

USER kpxc
ENV XDG_RUNTIME_DIR=/run/user/1000 \
    HOME=/home/kpxc \
    PATH=/home/kpxc/.local/bin:$PATH

WORKDIR /workspace

# The repo is bind-mounted by compose; this is just a default for ad-hoc runs.
CMD ["sh", "-c", "uv sync && uv run pytest tests/integration -m integration -v"]
