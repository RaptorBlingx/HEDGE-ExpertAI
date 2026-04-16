FROM rasa/rasa:3.6.20

WORKDIR /app

COPY services/rasa/ /app/

USER root
RUN chown -R 1001:1001 /app
USER 1001

RUN rasa train nlu --config config.yml --nlu data/nlu.yml --out models

EXPOSE 5005

CMD ["run", "--enable-api", "--cors", "*", "--model", "/app/models", "--port", "5005"]