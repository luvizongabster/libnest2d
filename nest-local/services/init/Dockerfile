FROM python:3.12-slim
RUN pip install --no-cache-dir boto3
COPY init_infra.py /init_infra.py
ENTRYPOINT ["python3", "/init_infra.py"]
