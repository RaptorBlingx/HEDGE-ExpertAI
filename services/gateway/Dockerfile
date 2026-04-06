FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/gateway/app/ ./app/

# Copy built frontend assets for static serving
COPY --from=frontend-builder /frontend/dist/ ./static/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
