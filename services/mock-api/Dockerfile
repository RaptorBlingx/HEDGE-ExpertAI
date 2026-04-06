FROM python:3.11-slim

WORKDIR /app

COPY services/mock-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mock-api/app/ ./app/

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
