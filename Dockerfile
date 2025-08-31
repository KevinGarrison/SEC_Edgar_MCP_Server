FROM python:3.13-slim AS builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./

RUN uv pip compile pyproject.toml -o /tmp/requirements.txt && \
    uv pip install --system -r /tmp/requirements.txt

COPY . .

FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 sqlite3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app

USER nobody
EXPOSE 8000

ENTRYPOINT ["uvicorn"]
CMD ["src.google_oauth2_server:app", "--host", "0.0.0.0", "--port", "8000"]