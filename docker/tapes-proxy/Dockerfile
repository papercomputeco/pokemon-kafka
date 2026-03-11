FROM debian:bookworm-slim
ARG TARGETOS=linux
ARG TARGETARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "https://download.tapes.dev/latest/${TARGETOS}/${TARGETARCH}/tapes" -o /usr/local/bin/tapes \
    && chmod +x /usr/local/bin/tapes
ENTRYPOINT ["tapes"]
