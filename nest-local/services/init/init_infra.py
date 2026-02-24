#!/usr/bin/env python3
"""Create DynamoDB table and S3 bucket if they do not exist. Run once after dynamodb and minio are up."""
import logging
import os
import sys
import time

import boto3
from botocore.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"init","message":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("init")

DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb:8000")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "nest-results")
TABLE_NAME = os.environ.get("TABLE_NAME", "nest_jobs")
AWS_ACCESS = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

boto_config = Config(signature_version="s3v4")


def main():
    logger.info(f"Starting init with DYNAMODB_ENDPOINT={DYNAMODB_ENDPOINT}, S3_ENDPOINT={S3_ENDPOINT}")

    for attempt in range(30):
        try:
            dd = boto3.client(
                "dynamodb",
                endpoint_url=DYNAMODB_ENDPOINT,
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS,
                aws_secret_access_key=AWS_SECRET,
            )
            dd.list_tables()
            break
        except Exception:
            time.sleep(2)
    else:
        logger.error("DynamoDB not reachable after 30 attempts")
        sys.exit(1)

    logger.info("DynamoDB connected")
    try:
        dd.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        logger.info(f"Created table {TABLE_NAME}")
    except dd.exceptions.ResourceInUseException:
        logger.info(f"Table {TABLE_NAME} already exists")

    skip_s3 = os.environ.get("SKIP_S3_INIT", "").strip().lower() in ("1", "true", "yes")
    if skip_s3:
        logger.info("SKIP_S3_INIT set: skipping S3/bucket creation")
        return

    for attempt in range(30):
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=S3_ENDPOINT,
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS,
                aws_secret_access_key=AWS_SECRET,
                config=boto_config,
            )
            buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
            if S3_BUCKET in buckets:
                logger.info(f"Bucket {S3_BUCKET} already exists")
                return
            s3.create_bucket(Bucket=S3_BUCKET)
            logger.info(f"Created bucket {S3_BUCKET}")
            return
        except Exception as e:
            logger.warning(f"S3 attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    logger.error("S3/MinIO not reachable or bucket creation failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
    os._exit(0)
