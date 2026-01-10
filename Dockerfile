FROM python:3.11-slim

WORKDIR /app

# Install git for worktree operations
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source
COPY src/ src/
COPY config/ config/

# Create non-root user
RUN useradd -m -u 1000 agent && \
    mkdir -p /workspaces && \
    chown -R agent:agent /app /workspaces

USER agent

# Expose webhook port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

CMD ["uvicorn", "src.orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
