FROM python:3.11.15-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3

WORKDIR /app

COPY services/mock-api/requirements.lock ./service-requirements.lock
COPY shared/requirements.lock ./shared-requirements.lock
RUN pip install --no-cache-dir --require-hashes \
    -r service-requirements.lock -r shared-requirements.lock

COPY shared/ /shared/
RUN pip install --no-cache-dir --no-deps /shared/

COPY services/mock-api/app/ ./app/

RUN useradd --create-home --uid 10001 hedge && chown -R hedge:hedge /app
USER 10001

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
