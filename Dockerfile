# syntax=docker/dockerfile:1.7

### Builder stage: install deps ###
FROM python:3.12-slim AS builder
WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc curl sqlite3 && \
    rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better caching
COPY requirements.txt ./

# 1) Install CPU-only PyTorch first (avoid CUDA)
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      --no-deps \
      torch==2.8.0 torchvision==0.23.0

# 2) Install rest of requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app source
COPY . .

### Runtime stage ###
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.google_oauth2_server:app", "--host", "0.0.0.0", "--port", "8000"]