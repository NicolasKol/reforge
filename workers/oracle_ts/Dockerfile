FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/oracle_ts/

ENV PYTHONPATH=/app

CMD ["python", "-m", "pytest", "oracle_ts/tests/", "-v"]
