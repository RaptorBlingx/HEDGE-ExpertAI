FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10

RUN apk add --no-cache curl openssl

COPY services/nginx/nginx.conf /etc/nginx/nginx.conf
COPY services/nginx/docker-entrypoint.sh /docker-entrypoint.d/40-generate-certs.sh

RUN chmod +x /docker-entrypoint.d/40-generate-certs.sh \
    && mkdir -p /etc/nginx/certs

EXPOSE 80 443
