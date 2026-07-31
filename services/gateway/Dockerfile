FROM node:20.19.4-alpine@sha256:df02558528d3d3d0d621f112e232611aecfee7cbc654f6b375765f72bb262799 AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.11.15-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3

WORKDIR /app

COPY services/gateway/requirements.lock ./service-requirements.lock
COPY shared/requirements.lock ./shared-requirements.lock
RUN pip install --no-cache-dir --require-hashes \
    -r service-requirements.lock -r shared-requirements.lock

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir --no-deps /shared/

COPY services/gateway/app/ ./app/

# Copy built frontend assets for static serving
COPY --from=frontend-builder /frontend/dist/ ./static/

# Copy embeddable widget files (not part of the Vite build)
COPY frontend/widget/ ./static/

RUN useradd --create-home --uid 10001 hedge && chown -R hedge:hedge /app
USER 10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
