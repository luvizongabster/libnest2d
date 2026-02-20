#!/usr/bin/env bash
set -e

# Create nest-results bucket in MinIO.
# Usage: run after MinIO is up, e.g.:
#   docker compose exec minio sh -c '...' or run a one-off with mc.
#   Or: docker compose run --rm minio-mc /bin/sh -c './init_minio.sh'
# This script expects MinIO to be reachable at MINIO_ENDPOINT (default http://minio:9000).

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ACCESS="${MINIO_ROOT_USER:-minioadmin}"
MINIO_SECRET="${MINIO_ROOT_PASSWORD:-minioadmin}"
BUCKET="${BUCKET:-nest-results}"

if command -v mc >/dev/null 2>&1; then
  mc alias set local "$MINIO_ENDPOINT" "$MINIO_ACCESS" "$MINIO_SECRET"
  mc mb "local/$BUCKET" --ignore-existing
  echo "Bucket $BUCKET ready."
else
  # Fallback: use AWS CLI (pip install awscli; configure endpoint)
  AWS_ACCESS_KEY_ID="$MINIO_ACCESS" AWS_SECRET_ACCESS_KEY="$MINIO_SECRET" \
    aws --endpoint-url="$MINIO_ENDPOINT" s3 mb "s3://$BUCKET" 2>/dev/null || true
  echo "Bucket $BUCKET ready (via AWS CLI)."
fi
