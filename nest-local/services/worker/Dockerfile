# Use engine image to copy nest_engine binary (build engine first: docker compose build engine)
FROM nest-local-engine AS engine

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnlopt0 \
    libnlopt-cxx0 \
    libpolyclipping22 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=engine /app/nest_engine /app/nest_engine
RUN chmod +x /app/nest_engine

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .

CMD ["python3", "worker.py"]
