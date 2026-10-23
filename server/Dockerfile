FROM python:3.13-slim

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY src/ src/
COPY server/ server/

# Run from the data volume so the FastF1 cache and computed replays persist too
ENV F1_DATA_DIR=/data PYTHONPATH=/app
VOLUME ["/data"]
WORKDIR /data
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8000"]
