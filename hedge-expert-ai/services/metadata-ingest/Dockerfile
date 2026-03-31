FROM python:3.11-slim

WORKDIR /app

COPY services/metadata-ingest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/metadata-ingest/app/ ./app/

EXPOSE 8004

# Run both FastAPI and Celery worker+beat in one container (small-scale deployment)
CMD ["sh", "-c", "celery -A app.celery_app:celery_app worker --beat --loglevel=info --concurrency=1 & uvicorn app.main:app --host 0.0.0.0 --port 8004"]
