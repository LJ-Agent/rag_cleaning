FROM python:3.11-alpine

RUN addgroup -S rag && adduser -S rag -G rag

WORKDIR /app

# Install system dependencies for Pillow and grpcio
RUN apk add --no-cache gcc musl-dev libffi-dev

COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir -e ".[dev]"

COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY proto/ proto/

RUN chown -R rag:rag /app
USER rag

EXPOSE 50056

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
