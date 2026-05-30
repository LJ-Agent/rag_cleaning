FROM python:3.11-slim

LABEL maintainer="RAG Team"
LABEL description="RAG Document Cleaning Service"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libjpeg-dev zlib1g-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy source files first, then install
COPY pyproject.toml .
COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY proto/ proto/

# PyTorch CPU for Alpine compatibility
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir -e ".[dev]"

# Non-root user
RUN groupadd -r rag && useradd -r -g rag rag && chown -R rag:rag /app
USER rag

EXPOSE 50056

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
