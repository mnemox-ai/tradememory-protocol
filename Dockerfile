FROM python:3.11-slim

LABEL maintainer="Mnemox <contact@mnemox.ai>"
LABEL description="TradeMemory Protocol — Persistent memory layer for AI trading agents"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY demo.py .
COPY .env.example .

# Create data directory for SQLite
RUN mkdir -p data

# Expose MCP server port
EXPOSE 8000

# Default: start MCP server
CMD ["python", "-m", "src.tradememory.server"]
