#!/usr/bin/env python3
"""Create DynamoDB table and S3 bucket if they do not exist. Run once after dynamodb and minio are up."""
import os
import sys
import time

import boto3
from botocore.config import Config

DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb:8000")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "nest-results")
TABLE_NAME = os.environ.get("TABLE_NAME", "nest_jobs")
AWS_ACCESS = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

boto_config = Config(signature_version="s3v4")

def main():
    for _ in range(30):
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
        print("DynamoDB not reachable", file=sys.stderr)
        sys.exit(1)

    try:
        dd.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table {TABLE_NAME}")
    except dd.exceptions.ResourceInUseException:
        print(f"Table {TABLE_NAME} already exists")

    skip_s3 = os.environ.get("SKIP_S3_INIT", "").strip().lower() in ("1", "true", "yes")
    if skip_s3:
        print("SKIP_S3_INIT set: skipping S3/bucket creation (e.g. using Digital Ocean Spaces)")
        return

    for _ in range(30):
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
                print(f"Bucket {S3_BUCKET} already exists")
                return
            s3.create_bucket(Bucket=S3_BUCKET)
            print(f"Created bucket {S3_BUCKET}")
            return
        except Exception as e:
            print(e, file=sys.stderr)
            time.sleep(2)
    print("S3/MinIO not reachable or bucket creation failed", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
