FROM python:3.11-slim

WORKDIR /app

COPY services/expert-recommend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/expert-recommend/app/ ./app/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
