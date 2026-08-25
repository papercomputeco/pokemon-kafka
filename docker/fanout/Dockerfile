# Fan-out snapshot image — the Daytona equivalent of the stereOS image.
#
# Contains: the repo, its Python deps, PyBoy (headless), and the tapes capture
# sidecar. Deliberately does NOT contain the ROM (not ours to redistribute) or
# any credential (a rotated key must not require a rebuild). Both arrive at
# sandbox launch — the ROM by upload, secrets by env injection.
#
# Pinned digest-style tag, never `latest`: Daytona rejects mutable tags, and a
# race is only comparable if every arm ran the same image.
FROM --platform=linux/amd64 python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:/root/.local/bin:${PATH}"

# PyBoy runs with window="null" so no display is needed, but its wheel still
# links against SDL2 and zlib at import time. curl/git are for the sidecar
# install and for reporting the build's provenance.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsdl2-2.0-0 \
        zlib1g \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# uv, pinned — the repo already builds with uv and ships a uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /workspace

# Dependency layer first: lockfile changes far less often than agent code, so
# a source edit reuses this layer instead of resolving the world again.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Source. .dockerignore keeps rom/, frames/, and local run output out.
COPY . /workspace
RUN uv sync --frozen

# Fail the build, not the race, if the emulator can't import. Without this a
# broken image is only discovered N sandboxes into a fan-out.
RUN python -c "from pyboy import PyBoy; print('PyBoy OK')"

# Capture sidecar: the tapes binary, which every sandbox runs as a local proxy
# writing to the ONE central Postgres named at launch. Version and checksum are
# pinned so an arm captured under a different build can't be mistaken for a peer.
ARG TAPES_VERSION=v0.37.0
ARG TAPES_SHA256=64859d0dc9f6175e8b19082bbd5de6449a1bcd31313f773b93712e9d61b2ebff
RUN curl -fsSL -o /usr/local/bin/tapes \
        "https://github.com/papercomputeco/tapes/releases/download/${TAPES_VERSION}/tapes-linux-amd64" \
    && echo "${TAPES_SHA256}  /usr/local/bin/tapes" | sha256sum -c - \
    && chmod +x /usr/local/bin/tapes \
    && tapes --help >/dev/null

# Marks images built by this pipeline so a stray sandbox is traceable to it.
LABEL org.opencontainers.image.source="https://github.com/papercomputeco/pokemon-kafka" \
      com.papercompute.role="fanout-race-arm"

CMD ["sleep", "infinity"]
