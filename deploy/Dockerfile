FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV UV_LINK_MODE=copy

RUN apt-get update \
  && apt-get install -y automake build-essential protobuf-compiler git \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Makefile ./Makefile
COPY app/ ./app
COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --group ops

ENV HOST="0.0.0.0"

CMD ["make", "run-server"]
