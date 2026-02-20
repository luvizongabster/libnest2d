#!/usr/bin/env bash
set -e

# Create DynamoDB table nest_jobs.
# Usage: run after DynamoDB local is up, e.g.:
#   docker compose run --rm awscli dynamodb create-table ...
# Or run this script inside a container that has AWS CLI and can reach dynamodb:8000.

ENDPOINT="${DYNAMODB_ENDPOINT:-http://dynamodb:8000}"
TABLE="${TABLE:-nest_jobs}"

aws dynamodb create-table \
  --endpoint-url="$ENDPOINT" \
  --table-name "$TABLE" \
  --attribute-definitions AttributeName=job_id,AttributeType=S \
  --key-schema AttributeName=job_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --no-cli-pager \
  2>/dev/null || true

echo "Table $TABLE ready."
