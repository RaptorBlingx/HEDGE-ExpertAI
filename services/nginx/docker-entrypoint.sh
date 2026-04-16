#!/bin/sh
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_FILE="${TLS_CERT_PATH:-$CERT_DIR/server.crt}"
KEY_FILE="${TLS_KEY_PATH:-$CERT_DIR/server.key}"
TARGET_CERT="$CERT_DIR/server.crt"
TARGET_KEY="$CERT_DIR/server.key"
SERVER_NAME="${TLS_SERVER_NAME:-localhost}"
DAYS="${TLS_SELF_SIGNED_DAYS:-30}"

mkdir -p "$CERT_DIR"

if [ -n "${TLS_CERT_PATH:-}" ] && [ -n "${TLS_KEY_PATH:-}" ] && [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    if [ "$CERT_FILE" != "$TARGET_CERT" ]; then
        cp "$CERT_FILE" "$TARGET_CERT"
    fi
    if [ "$KEY_FILE" != "$TARGET_KEY" ]; then
        cp "$KEY_FILE" "$TARGET_KEY"
    fi
elif [ ! -f "$TARGET_CERT" ] || [ ! -f "$TARGET_KEY" ]; then
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$TARGET_KEY" \
        -out "$TARGET_CERT" \
        -days "$DAYS" \
        -subj "/CN=$SERVER_NAME"
fi

chmod 600 "$TARGET_KEY"