import json
import os
import subprocess
import time

import boto3
from botocore.config import Config

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "http://elasticmq:9324/000000000000/nest-jobs")
USE_REAL_AWS = SQS_QUEUE_URL.startswith("https://sqs.")

DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb:8000")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "nest-results")
TABLE_NAME = "nest_jobs"
AWS_ACCESS = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ENGINE_PATH = os.environ.get("ENGINE_PATH", "/app/nest_engine")
ENGINE_TIMEOUT = 20
ERROR_MAX_LEN = 2000

boto_config = Config(signature_version="s3v4")


def _aws_kwargs(service_endpoint=None):
    if USE_REAL_AWS:
        return {"region_name": AWS_REGION}
    return {
        "endpoint_url": service_endpoint,
        "region_name": AWS_REGION,
        "aws_access_key_id": AWS_ACCESS,
        "aws_secret_access_key": AWS_SECRET,
    }


dynamodb = boto3.resource("dynamodb", **_aws_kwargs(DYNAMODB_ENDPOINT))
s3 = boto3.client("s3", config=boto_config, **_aws_kwargs(S3_ENDPOINT))
sqs = boto3.client(
    "sqs",
    **_aws_kwargs(os.environ.get("SQS_ENDPOINT", "http://elasticmq:9324")),
)


def update_job(job_id: str, **kwargs):
    table = dynamodb.Table(TABLE_NAME)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    expr = "SET updated_at = :t"
    values = {":t": now}
    for k, v in kwargs.items():
        key = f":{k}"
        expr += f", #_{k} = {key}"
        values[key] = v
    names = {f"#_{k}": k for k in kwargs}
    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=expr,
        ExpressionAttributeValues=values,
        ExpressionAttributeNames=names,
    )


def process_message(msg):
    body = json.loads(msg["Body"])
    job_id = body["job_id"]
    payload = body["payload"]
    receipt_handle = msg["ReceiptHandle"]

    update_job(job_id, status="RUNNING")
    try:
        result = subprocess.run(
            [ENGINE_PATH],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=ENGINE_TIMEOUT,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", errors="replace").strip()[:ERROR_MAX_LEN]
            update_job(job_id, status="FAILED", error=err)
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            return
        out = result.stdout.decode("utf-8", errors="replace")
        key = f"results/{job_id}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=out.encode(),
            ContentType="application/json",
        )
        update_job(job_id, status="SUCCEEDED", s3_key=key)
    except subprocess.TimeoutExpired:
        update_job(job_id, status="FAILED", error="Engine timeout (20s)"[:ERROR_MAX_LEN])
    except Exception as e:
        update_job(job_id, status="FAILED", error=str(e)[:ERROR_MAX_LEN])
    sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)


def main():
    while True:
        try:
            r = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
            )
            for msg in r.get("Messages", []):
                process_message(msg)
        except Exception as e:
            print(e)
            time.sleep(5)


if __name__ == "__main__":
    main()
