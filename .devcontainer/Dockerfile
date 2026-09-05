FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The upstream devcontainer base image ships a third-party yarn apt source whose signing
# key periodically expires, which breaks `apt-get update`. These projects do not use yarn,
# so remove that source before updating.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        jq \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

USER vscode
