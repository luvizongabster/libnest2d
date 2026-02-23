#!/bin/bash
# One-liner to create nest_jobs table in DynamoDB local (run inside nest network)
docker run --rm --network nest-local_default python:3.12-slim bash -c '
pip install -q boto3
python3 << PY
import boto3
c = boto3.client("dynamodb", endpoint_url="http://dynamodb:8000", region_name="us-east-1")
try:
    c.create_table(TableName="nest_jobs", AttributeDefinitions=[{"AttributeName":"job_id","AttributeType":"S"}], KeySchema=[{"AttributeName":"job_id","KeyType":"HASH"}], BillingMode="PAY_PER_REQUEST")
    print("Table created")
except c.exceptions.ResourceInUseException:
    print("Table exists")
except Exception as e:
    print(e)
PY
'
