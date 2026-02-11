FROM python:3.11-slim

WORKDIR /code

# Install system dependencies (gcc/binutils needed by oracle_dwarf tests & pyelftools)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY app/requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir -r /code/requirements.txt

# Copy application code (preserve app/ directory structure)
COPY app/ /code/app/

# Copy oracle_dwarf worker package (importable via PYTHONPATH)
COPY workers/oracle_dwarf/ /code/oracle_dwarf/

# Copy oracle_ts worker package (importable via PYTHONPATH)
COPY workers/oracle_ts/ /code/oracle_ts/

ENV PYTHONPATH=/code

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
