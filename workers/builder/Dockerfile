FROM python:3.11-slim

# =============================================================================
# builder_synth_v1 — Synthetic ELF Builder
# Profile: linux-x86_64-elf-gcc-c
#
# GCC only. No Clang, no C++, no git builds.
# =============================================================================

# Install system dependencies: GCC toolchain + binutils
RUN apt-get update && apt-get install -y \
    gcc \
    binutils \
    && rm -rf /var/lib/apt/lists/*

# Debian Bookworm (Python 3.11-slim base) provides:
# - GCC 12.2.0
# - binutils 2.40
# These are the pinned versions for builder_synth_v1.

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create workspace directory for builds
RUN mkdir -p /tmp/reforge_builds

# Run worker
CMD ["python", "worker.py"]