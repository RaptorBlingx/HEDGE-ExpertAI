FROM python:3.11-slim

WORKDIR /app

# CPU-only PyTorch MUST be installed BEFORE sentence-transformers
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY services/discovery-ranking/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir sentence-transformers

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/discovery-ranking/app/ ./app/

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
