FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --yes && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./

RUN uv pip install --system --frozen --no-deps -r <(uv pip compile pyproject.toml)

COPY . .

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 sqlite3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app

USER nobody
EXPOSE 8000

ENTRYPOINT ["uvicorn"]
CMD ["src.google_oauth2_server:app", "--host", "0.0.0.0", "--port", "8000"]