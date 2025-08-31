# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl sqlite3 && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

# Copy just files needed for deps layer
COPY pyproject.toml uv.lock* ./

# 1) Compile requirements (no hashes to keep things simple after we split torch out)
RUN uv pip compile pyproject.toml -o /tmp/requirements.txt

# 2) Install CPU-only torch/torchvision first (no CUDA)
RUN uv pip install --system \
    --index-url https://download.pytorch.org/whl/cpu \
    --no-deps \
    torch==2.8.0 torchvision==0.23.0

# 3) Install the rest, excluding torch/torchvision from the compiled file
RUN grep -vE '^(torch|torchvision)== ' /tmp/requirements.txt > /tmp/req-no-torch.txt && \
    uv pip install --system -r /tmp/req-no-torch.txt

# Copy app
COPY . .

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && \
    rm -rf /var/lib/apt/lists/*

# Bring in deps + app
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

# Ensure imports find your src module
EXPOSE 8000

# Run server
CMD ["uvicorn","google_oauth2_server:app","--host","0.0.0.0","--port","8000"]