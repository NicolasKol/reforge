FROM python:3.11-slim

# Install system dependencies (git, gcc, clang, cmake, make, readelf)
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    clang \
    cmake \
    make \
    autoconf \
    automake \
    libtool \
    pkg-config \
    binutils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Note: Debian Bookworm (Python 3.11-slim base) provides:
# - GCC 12.2.0
# - Clang 14.0.6
# These are the default versions and sufficient for reproducible builds

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create workspace directory for builds
RUN mkdir -p /tmp/reforge_builds

EXPOSE 8080

# Run worker (not FastAPI)
CMD ["python", "worker.py"]