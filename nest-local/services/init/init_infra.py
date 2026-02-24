#!/usr/bin/env python3
"""Create DynamoDB table and S3 bucket if they do not exist. Run once after dynamodb and minio are up."""
import json
import os
import sys
import time

import boto3
from botocore.config import Config

# #region agent log
def _debug_log(message, data=None, hypothesis_id=None):
    line = json.dumps({"sessionId": "4f46c5", "message": message, "data": data or {}, "hypothesisId": hypothesis_id, "location": "init_infra.py", "timestamp": time.time() * 1000}) + "\n"
    try:
        with open("/debug-logs/debug-4f46c5.log", "a") as f:
            f.write(line)
    except Exception:
        print(line.strip(), file=sys.stderr)
# #endregion

DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb:8000")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "nest-results")
TABLE_NAME = os.environ.get("TABLE_NAME", "nest_jobs")
AWS_ACCESS = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

boto_config = Config(signature_version="s3v4")

def main():
    # #region agent log
    _debug_log("init main() started", {"DYNAMODB_ENDPOINT": DYNAMODB_ENDPOINT, "S3_ENDPOINT": S3_ENDPOINT}, "H4,H5")
    # #endregion
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
        # #region agent log
        _debug_log("DynamoDB unreachable after 30 attempts", {}, "H2")
        # #endregion
        print("DynamoDB not reachable", file=sys.stderr)
        sys.exit(1)

    # #region agent log
    _debug_log("DynamoDB connected", {}, "H2")
    # #endregion
    try:
        dd.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # #region agent log
        _debug_log("create_table succeeded", {"table": TABLE_NAME}, "H2,H5")
        # #endregion
        print(f"Created table {TABLE_NAME}")
    except dd.exceptions.ResourceInUseException:
        # #region agent log
        _debug_log("table already exists", {"table": TABLE_NAME}, "H2,H5")
        # #endregion
        print(f"Table {TABLE_NAME} already exists")

    skip_s3 = os.environ.get("SKIP_S3_INIT", "").strip().lower() in ("1", "true", "yes")
    if skip_s3:
        # #region agent log
        _debug_log("skip_s3 true, returning", {}, "H1,H5")
        # #endregion
        print("SKIP_S3_INIT set: skipping S3/bucket creation (e.g. using Digital Ocean Spaces)")
        return

    # #region agent log
    _debug_log("S3 loop starting", {"attempts_max": 30}, "H2")
    # #endregion
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
                # #region agent log
                _debug_log("bucket already exists, returning", {"bucket": S3_BUCKET}, "H1,H5")
                # #endregion
                print(f"Bucket {S3_BUCKET} already exists")
                return
            s3.create_bucket(Bucket=S3_BUCKET)
            # #region agent log
            _debug_log("bucket created, returning", {"bucket": S3_BUCKET}, "H1,H5")
            # #endregion
            print(f"Created bucket {S3_BUCKET}")
            return
        except Exception as e:
            # #region agent log
            _debug_log("S3 attempt failed", {"attempt": attempt + 1, "error": str(e)}, "H2")
            # #endregion
            print(e, file=sys.stderr)
            time.sleep(2)
    # #region agent log
    _debug_log("S3 unreachable after 30 attempts", {}, "H2")
    # #endregion
    print("S3/MinIO not reachable or bucket creation failed", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
    # #region agent log
    _debug_log("main() returned, about to os._exit(0)", {}, "H1,H3,H5")
    # #endregion
    # os._exit(0) terminates immediately; sys.exit(0) can hang because boto3 connection pool threads keep the process alive.
    os._exit(0)
