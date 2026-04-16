FROM nginx:1.27-alpine

RUN apk add --no-cache curl openssl

COPY services/nginx/nginx.conf /etc/nginx/nginx.conf
COPY services/nginx/docker-entrypoint.sh /docker-entrypoint.d/40-generate-certs.sh

RUN chmod +x /docker-entrypoint.d/40-generate-certs.sh \
    && mkdir -p /etc/nginx/certs

EXPOSE 80 443