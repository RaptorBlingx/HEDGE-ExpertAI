FROM python:3.11-slim

WORKDIR /app

COPY services/chat-intent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/chat-intent/app/ ./app/

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
