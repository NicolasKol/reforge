FROM python:3.11-slim

WORKDIR /code

# Install system dependencies
# - curl: health checks
# - docker-cli: needed by analyzer_ghidra_decompile to exec into Ghidra container
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
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

# Copy join_dwarf_ts worker package (importable via PYTHONPATH)
COPY workers/join_dwarf_ts/ /code/join_dwarf_ts/

# Copy analyzer_ghidra_decompile worker package (importable via PYTHONPATH)
COPY workers/analyzer_ghidra_decompile/ /code/analyzer_ghidra_decompile/
        
# Copy join_ghidra worker package (importable via PYTHONPATH)
COPY workers/join_oracles_to_ghidra_decompile/ /code/join_oracles_to_ghidra_decompile/

# Copy minimal data/ module (only enums + paths, no pandas-heavy loader)
COPY data/enums.py /code/data/enums.py
COPY data/paths.py /code/data/paths.py
COPY data/noise_lists.py /code/data/noise_lists.py
COPY data/binning.py /code/data/binning.py
COPY data/schema.py /code/data/schema.py
COPY data/loader.py /code/data/loader.py
COPY data/experiments.py /code/data/experiments.py
COPY data/llm_contract.py /code/data/llm_contract.py
COPY data/reporting.py /code/data/reporting.py
COPY data/scoring.py /code/data/scoring.py

# Copy prompt templates
COPY workers/llm/ /code/workers/llm/

RUN echo '"""Minimal data package stub for container."""' > /code/data/__init__.py

ENV PYTHONPATH=/code

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
