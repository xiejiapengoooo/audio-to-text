FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/root

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .

ENTRYPOINT []

USER root

EXPOSE 7860

CMD ["uv", "run", "app.py"]
