FROM python:3.11.15-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3

WORKDIR /app

# CPU-only PyTorch MUST be installed BEFORE sentence-transformers
RUN pip install --no-cache-dir torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu

COPY services/discovery-ranking/requirements.lock ./service-requirements.lock
COPY shared/requirements.lock ./shared-requirements.lock
RUN pip install --no-cache-dir --require-hashes \
    -r service-requirements.lock -r shared-requirements.lock
RUN pip install --no-cache-dir sentence-transformers==5.0.0

# Copy shared package
COPY shared/ /shared/
RUN pip install --no-cache-dir --no-deps /shared/

COPY services/discovery-ranking/app/ ./app/

RUN useradd --create-home --uid 10001 hedge \
    && mkdir -p /home/hedge/.cache /model-cache \
    && chown -R hedge:hedge /app /home/hedge /model-cache
USER 10001

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
