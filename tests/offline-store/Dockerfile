# Disposable developer/test runner, with the existing repository locks and CI tools.
ARG BASE_IMAGE=python:3.11.15-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
FROM ${BASE_IMAGE}
USER root
COPY *.lock /locks/
RUN python -m pip install --no-cache-dir --require-hashes \
    -r /locks/shared.lock -r /locks/chat-intent.lock \
    -r /locks/discovery-ranking.lock -r /locks/expert-recommend.lock \
    -r /locks/metadata-ingest.lock -r /locks/gateway.lock -r /locks/mock-api.lock
RUN python -m pip install --no-cache-dir \
    pytest==8.4.1 pytest-cov==6.2.1 pytest-asyncio==1.1.0 ruff==0.16.1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/repo/shared:/repo
WORKDIR /repo
USER 10001
ENTRYPOINT ["python"]
