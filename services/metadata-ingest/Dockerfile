FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/metadata-ingest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/metadata-ingest/app/ ./app/

# Supervisord configuration — restarts Celery or Uvicorn if either crashes
COPY services/metadata-ingest/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8004

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
