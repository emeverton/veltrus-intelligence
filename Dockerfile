FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
RUN python -c "from huggingface_hub import hf_hub_download; \
    hf_hub_download('hexgrad/Kokoro-82M', 'kokoro-v0_19.onnx', local_dir='/app'); \
    hf_hub_download('hexgrad/Kokoro-82M', 'voices.bin', local_dir='/app')"
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
