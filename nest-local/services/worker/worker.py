import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3
from botocore.config import Config


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "worker",
        }
        if hasattr(record, "job_id"):
            log_data["job_id"] = record.job_id
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.handlers = [handler]
logger.propagate = False

shutdown_event = threading.Event()
jobs_processed = 0
last_job_time = None
start_time = time.time()


def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            status = {
                "status": "healthy" if not shutdown_event.is_set() else "shutting_down",
                "jobs_processed": jobs_processed,
                "last_job_time": last_job_time,
                "uptime_seconds": int(time.time() - start_time),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_server(port=8081):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server started on port {port}")
    return server

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "http://elasticmq:9324/000000000000/nest-jobs")
USE_REAL_AWS = SQS_QUEUE_URL.startswith("https://sqs.")

DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb:8000")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "nest-results")
TABLE_NAME = os.environ.get("TABLE_NAME", "nest_jobs")
AWS_ACCESS = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ENGINE_PATH = os.environ.get("ENGINE_PATH", "/app/nest_engine")
ENGINE_TIMEOUT = int(os.environ.get("ENGINE_TIMEOUT", "20"))
ERROR_MAX_LEN = int(os.environ.get("ERROR_MAX_LEN", "2000"))

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
    global jobs_processed, last_job_time

    body = json.loads(msg["Body"])
    job_id = body["job_id"]
    payload = body["payload"]
    receipt_handle = msg["ReceiptHandle"]

    logger.info(f"Processing job {job_id}", extra={"job_id": job_id})
    update_job(job_id, status="RUNNING")
    proc = None
    try:
        proc = subprocess.Popen(
            [ENGINE_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = proc.communicate(
                input=json.dumps(payload).encode(),
                timeout=ENGINE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            error_msg = f"Engine timeout ({ENGINE_TIMEOUT}s)"
            logger.error(f"Job {job_id} failed: {error_msg}", extra={"job_id": job_id})
            update_job(job_id, status="FAILED", error=error_msg[:ERROR_MAX_LEN])
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            return
        if proc.returncode != 0:
            err = (stderr or b"").decode("utf-8", errors="replace").strip()[:ERROR_MAX_LEN]
            logger.error(f"Job {job_id} failed: engine error", extra={"job_id": job_id})
            update_job(job_id, status="FAILED", error=err)
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            return
        out = stdout.decode("utf-8", errors="replace")
        key = f"results/{job_id}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=out.encode(),
            ContentType="application/json",
        )
        update_job(job_id, status="SUCCEEDED", s3_key=key)
        logger.info(f"Job {job_id} completed successfully", extra={"job_id": job_id})
        jobs_processed += 1
        last_job_time = datetime.utcnow().isoformat() + "Z"
    except Exception as e:
        if proc is not None:
            try:
                proc.kill()
                proc.communicate()
            except Exception:
                pass
        logger.exception(f"Job {job_id} failed with exception", extra={"job_id": job_id})
        update_job(job_id, status="FAILED", error=str(e)[:ERROR_MAX_LEN])
    sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)


def main():
    health_server = start_health_server()
    logger.info("Worker started, waiting for messages...")

    while not shutdown_event.is_set():
        try:
            r = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=5,
            )
            for msg in r.get("Messages", []):
                if shutdown_event.is_set():
                    logger.info("Shutdown requested, skipping new messages")
                    break
                process_message(msg)
        except Exception as e:
            if not shutdown_event.is_set():
                logger.exception("Error in main loop")
                time.sleep(5)

    logger.info("Worker shutdown complete")


if __name__ == "__main__":
    main()
