FROM python:3.11-slim

# Install gcc for test fixture compilation and binutils for readelf
RUN apt-get update && apt-get install -y \
    gcc \
    binutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pytest pytest-cov

# Copy package into /app/oracle_dwarf/ so imports work as oracle_dwarf.*
COPY . /app/oracle_dwarf/

# Make oracle_dwarf importable from /app
ENV PYTHONPATH=/app

# Default: run tests (oracle is served through the central reforge API)
CMD ["python", "-m", "pytest", "oracle_dwarf/tests/", "-v"]
