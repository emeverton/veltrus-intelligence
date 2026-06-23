FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make wget \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
RUN mkdir -p /kokoro && \
    wget -q -O /kokoro/kokoro-v0_19.onnx \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx && \
    wget -q -O /kokoro/voices.bin \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY --from=builder /kokoro/kokoro-v0_19.onnx /app/kokoro-v0_19.onnx
COPY --from=builder /kokoro/voices.bin /app/voices.bin
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY tests/ ./tests/
COPY pyproject.toml .
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
