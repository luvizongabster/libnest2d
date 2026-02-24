import asyncio
import datetime
import json
import os
import uuid
from contextlib import asynccontextmanager

import boto3
from botocore.config import Config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "").strip()
USE_REAL_AWS = bool(SQS_QUEUE_URL)

SQS_ENDPOINT = os.environ.get("SQS_ENDPOINT", "http://elasticmq:9324")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb:8000")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
# S3_PUBLIC_ENDPOINT: public-facing base URL for presigned URLs.
# The internal S3_ENDPOINT (e.g. http://minio:9000) in the presigned URL is replaced
# with this value so the URL is reachable by the client (browser/frontend).
# Example: https://api2.gabster.com.br/s3
S3_PUBLIC_ENDPOINT = os.environ.get("S3_PUBLIC_ENDPOINT", S3_ENDPOINT)
S3_BUCKET = os.environ.get("S3_BUCKET", "nest-results")
AWS_ACCESS = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

QUEUE_NAME = os.environ.get("QUEUE_NAME", "nest-jobs")
TABLE_NAME = os.environ.get("TABLE_NAME", "nest_jobs")
PRESIGNED_EXPIRY = int(os.environ.get("PRESIGNED_EXPIRY", "600"))

boto_config = Config(
    signature_version="s3v4",
    retries={"mode": "standard", "max_attempts": 3},
)


def _aws_kwargs(service_endpoint=None):
    """Kwargs for boto3 client: use IAM role on AWS, else local endpoints + credentials."""
    if USE_REAL_AWS:
        return {"region_name": AWS_REGION}
    return {
        "endpoint_url": service_endpoint,
        "region_name": AWS_REGION,
        "aws_access_key_id": AWS_ACCESS,
        "aws_secret_access_key": AWS_SECRET,
    }


sqs = boto3.client("sqs", **_aws_kwargs(SQS_ENDPOINT))
dynamodb = boto3.resource("dynamodb", **_aws_kwargs(DYNAMODB_ENDPOINT))
# s3_client: used for all S3 operations (internal endpoint).
# Presigned URLs are generated with this client and then rewritten to the public endpoint.
s3_client = boto3.client(
    "s3",
    config=boto_config,
    **_aws_kwargs(S3_ENDPOINT),
)


async def wait_for_dependencies():
    for _ in range(60):
        try:
            sqs.list_queues()
            dynamodb.meta.client.describe_table(TableName=TABLE_NAME)
            return
        except Exception:
            await asyncio.sleep(2)
    raise RuntimeError("Dependencies (SQS, DynamoDB) not ready")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_for_dependencies()
    yield


app = FastAPI(title="Nest API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs")
def create_job(payload: dict):
    job_id = str(uuid.uuid4())
    table = dynamodb.Table(TABLE_NAME)
    table.put_item(
        Item={
            "job_id": job_id,
            "status": "QUEUED",
            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
    )
    queue_url = SQS_QUEUE_URL or f"{SQS_ENDPOINT.rstrip('/')}/000000000000/{QUEUE_NAME}"
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"job_id": job_id, "payload": payload}),
    )
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    table = dynamodb.Table(TABLE_NAME)
    try:
        r = table.get_item(Key={"job_id": job_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    item = r.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Job not found")
    status = item.get("status", "UNKNOWN")
    if status == "SUCCEEDED":
        s3_key = item.get("s3_key", "")
        if not s3_key:
            raise HTTPException(status_code=500, detail="Missing s3_key")
        # Generate presigned URL using the internal endpoint, then rewrite
        # the base URL to the public endpoint so the browser can reach it.
        # The S3v4 signature is computed against the internal Host (minio:9000)
        # and nginx forwards that same Host header when proxying /s3/ → minio:9000.
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=PRESIGNED_EXPIRY,
        )
        if S3_PUBLIC_ENDPOINT != S3_ENDPOINT:
            url = url.replace(S3_ENDPOINT, S3_PUBLIC_ENDPOINT, 1)
        return {
            "status": "SUCCEEDED",
            "result_url": url,
            "expires_in_sec": PRESIGNED_EXPIRY,
        }
    if status == "FAILED":
        return {"status": "FAILED", "error": item.get("error", "Unknown error")}
    return {"status": status}

