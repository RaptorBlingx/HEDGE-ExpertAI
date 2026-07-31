FROM rasa/rasa:3.6.20@sha256:602ecf5b43b18630a323322404a73d3ead2d490c99696985e7b4461001898998

ENV RASA_TELEMETRY_ENABLED=false \
    SQLALCHEMY_SILENCE_UBER_WARNING=1

WORKDIR /app

COPY services/rasa/ /app/

USER root
RUN chown -R 1001:1001 /app
USER 1001

RUN rasa train nlu --config config.yml --nlu data/nlu.yml --out models \
    --fixed-model-name hedge-expertai-nlu-v2

EXPOSE 5005

CMD ["run", "--enable-api", "--cors", "*", "--model", "/app/models", "--port", "5005"]
