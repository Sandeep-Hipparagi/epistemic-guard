# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    EPISTEMIC_SEARCH_PROVIDER=duckduckgo

WORKDIR /app

# Install security certificates and curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration and project definitions
COPY pyproject.toml README.md ./
COPY config/ ./config/
COPY src/ ./src/

# Install epistemic-guard package and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Create non-privileged service user
RUN useradd -m -u 1000 epistemicuser && \
    chown -R epistemicuser:epistemicuser /app
USER epistemicuser

# Expose FastAPI REST service port
EXPOSE 8000

# Container health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch uvicorn REST server
CMD ["uvicorn", "epistemic_guard.interfaces.api:app", "--host", "0.0.0.0", "--port", "8000"]
