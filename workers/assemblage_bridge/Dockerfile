FROM python:3.11-slim

LABEL maintainer="Reforge"
LABEL description="Assemblage Bridge - HTTP API for n8n to Assemblage integration"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for data persistence
RUN mkdir -p /files/binaries /files/assemblage_bridge

# Environment defaults
ENV ASSEMBLAGE_BRIDGE_PORT=8090
ENV ASSEMBLAGE_LOCAL_OUT_DIR=/files/binaries
ENV ASSEMBLAGE_DB_PATH=/files/assemblage_bridge/jobs.db

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${ASSEMBLAGE_BRIDGE_PORT}/health || exit 1

# Expose port
EXPOSE 8090

# Run the application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
